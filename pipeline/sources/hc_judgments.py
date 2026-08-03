"""High Court judgment-portal source (§4a) — the cleanly-open, direct-PDF listings.

This consumes the High Court judgment portals that the 2026-08-03 survey found
**cleanly open**: a robots-permitted HTML page that links judgment PDFs directly, with
**no CAPTCHA** (Delhi, J&K & Ladakh, and Meghalaya share this shape; more courts are
added as config entries, never as code). CAPTCHA-gated portals are never touched — that
is an inviolable rule, not a TODO.

Flow — every step in memory, because a judgment is the highest-PII input the project has
(§1b: a judgment routinely names the victim, their age, family, village, school):

  1. GET the court's HTML listing (the shared PoliteClient: honest UA, robots.txt, one
     request / 2s / host, 429 backoff).
  2. Parse the judgment PDF URLs out of the listing (any ``.pdf`` href, resolved against
     the court's base URL).
  3. For each — capped at ``config.HC_MAX_FETCH_PER_COURT`` newest per court, and
     ``config.HC_MAX_DOCS_PER_RUN`` qualifying total — GET the PDF bytes and run
     ``pdftotext - -`` (**stdin -> stdout: the PDF never touches disk**).
  4. LOCAL statute pre-filter — the cost control. ONLY a document whose text matches the
     sexual-offence statute regex (BNS 63-79 / POCSO / IPC 375-376 family) becomes a
     :class:`RawDocument` bound for Gemini. Everything else is dropped, read by no model.

The judgment text lives ONLY in the returned in-memory ``RawDocument.text``; it is never
written to disk, logged, cached, or placed in an error/cost sample. The publisher is the
court name, so :func:`pipeline.provenance.classify_source_type` classifies the record as
**court-grade (tier 1)** — its value is the judgment's FACTS (CNR/case number, judicial
status, judgment date, offence sections), never its narrative. The per-court walk
statistics (``stats``) are counts only — never a URL of a dropped doc, never any text.
"""

from __future__ import annotations

import html
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin

from pipeline import config
from pipeline.sources.base import RawDocument
from pipeline.sources.http import HttpGetter

__all__ = [
    "HcCourt",
    "HcJudgmentsSource",
    "extract_pdf_urls",
    "pdf_to_text",
    "qualifies",
]

# --- The local statute pre-filter (the cost control) ----------------------------------------
# Only a document whose text matches a SEXUAL-OFFENCE charge statute reaches Gemini. The
# filter is section-anchored (a charged case always cites its section) plus a few
# unambiguous offence phrases; it is deliberately conservative on precision but must not
# MISS a charged case, so both "IPC 376" and "376 IPC" orderings are covered. Scope mirrors
# the directive: BNS 63-79 (the sexual-offences chapter), POCSO, and the IPC 375/376/354
# family. Charge codes are PUBLIC and non-identifying (CLAUDE.md §1a).
_STATUTE_PREFILTER_RE = re.compile(
    r"""
      \bPOCSO\b
    | \bBNS\b[^\n]{0,20}?\b(?:6[3-9]|7[0-9])\b            # BNS 63-79 (e.g. "BNS Section 64")
    | \b(?:6[3-9]|7[0-9])\b[^\n]{0,8}?\bBNS\b             # "64 BNS"
    | \bIPC\b[^\n]{0,20}?\b(?:37[56][A-E]?|354[A-D]?)\b   # IPC 375/376/376A-E/354/354A-D
    | \b(?:37[56][A-E]?|354[A-D]?)\b[^\n]{0,8}?\bIPC\b    # "376 IPC"
    | \b(?:u/s\.?|under\s+section[s]?|section[s]?)\s*(?:37[56][A-E]?|354[A-D]?)\b
    | \bgang[\s-]?rape\b
    | \b(?:penetrative|aggravated)\s+sexual\s+assault\b
    | \boutrag(?:e|ing)\s+(?:the|her)\s+modesty\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Extract each href value, then keep it only if it names a PDF. Splitting in two steps lets
# a comma-concatenated multi-file href (a Meghalaya data quirk) resolve to its FIRST document
# instead of a broken URL, while a normal ``?query`` on a single PDF href is preserved.
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_FIRST_PDF_RE = re.compile(r"(.*?\.pdf)(\?[^,\s]*)?", re.IGNORECASE)

# pdftotext is a fast local process, but a malformed PDF can hang it — bound the wait.
_PDFTOTEXT_TIMEOUT_S = 20.0


def qualifies(text: str) -> bool:
    """True if ``text`` cites a sexual-offence charge statute — the LOCAL pre-filter gate.

    Runs on the extracted judgment text BEFORE any model sees it, so a non-qualifying
    judgment (the vast majority of a court's mixed listing) is dropped for free.
    """
    return bool(text) and _STATUTE_PREFILTER_RE.search(text) is not None


def extract_pdf_urls(listing_html: str, base_url: str) -> list[str]:
    """Absolute, de-duplicated judgment PDF URLs found in a listing page (order preserved).

    Relative hrefs are resolved against ``base_url``. This is intentionally generic — a
    direct-PDF listing links its documents as ``.pdf`` hrefs regardless of the portal's
    templating (Delhi's ``showFileJudgment/<id>.pdf``, J&K's filename-embedded case number,
    Meghalaya's ``/sites/default/files/<date>.pdf`` all match).
    """
    if not listing_html:
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for match in _HREF_RE.finditer(listing_html):
        value = html.unescape(match.group(1)).strip()
        pdf = _FIRST_PDF_RE.match(value)
        if pdf is None:
            continue  # href does not point at a PDF
        absolute = urljoin(base_url, pdf.group(1) + (pdf.group(2) or ""))
        if absolute not in seen:
            seen.add(absolute)
            urls.append(absolute)
    return urls


_Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


def pdf_to_text(pdf_bytes: bytes, *, run: _Runner | None = None) -> str:
    """Extract text from PDF bytes via ``pdftotext - -`` (stdin -> stdout, NEVER a temp file).

    The PDF is a HIGH-PII payload; piping it through stdin keeps it out of the filesystem
    entirely. Returns ``""`` when pdftotext is absent, times out, errors, or the PDF has no
    extractable text — a source that yields no text simply produces no RawDocument. ``run``
    is injectable for tests (defaults to :func:`subprocess.run`).
    """
    if not pdf_bytes:
        return ""
    runner: _Runner = subprocess.run if run is None else run
    try:
        result = runner(
            ["pdftotext", "-", "-"],
            input=pdf_bytes,
            capture_output=True,
            timeout=_PDFTOTEXT_TIMEOUT_S,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return ""
    stdout = result.stdout or b""
    if result.returncode != 0 and not stdout:
        return ""
    return stdout.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class HcCourt:
    """One open High Court judgment portal.

    Attributes:
        court: The court name — becomes ``RawDocument.publisher`` and MUST classify as a
            court authority (e.g. contains "High Court") so the record is court-grade.
        listing_url: The HTML page that links judgment PDFs directly.
        base_url: Base URL for resolving relative PDF hrefs (usually the site origin).
    """

    court: str
    listing_url: str
    base_url: str


class HcJudgmentsSource:
    """A :class:`~pipeline.sources.base.Source` over cleanly-open HC judgment portals."""

    def __init__(
        self,
        client: HttpGetter,
        courts: tuple[HcCourt, ...],
        *,
        fetched_at: str | None = None,
        pdf_to_text_fn: Callable[[bytes], str] | None = None,
        max_fetch_per_court: int | None = None,
        max_docs: int | None = None,
    ) -> None:
        self._client = client
        self._courts = courts
        self._fetched_at = fetched_at or date.today().isoformat()
        self._pdf_to_text: Callable[[bytes], str] = (
            pdf_to_text if pdf_to_text_fn is None else pdf_to_text_fn
        )
        self._max_fetch = (
            config.HC_MAX_FETCH_PER_COURT if max_fetch_per_court is None else max_fetch_per_court
        )
        self._max_docs = config.HC_MAX_DOCS_PER_RUN if max_docs is None else max_docs
        # Per-court walk statistics — COUNTS ONLY (listed / fetched / qualifying), for the
        # operator report. Never a URL of a dropped document, never any text.
        self.stats: dict[str, dict[str, int]] = {}

    async def fetch(self) -> list[RawDocument]:
        docs: list[RawDocument] = []
        for court in self._courts:
            self.stats[court.court] = await self._walk_court(court, docs)
        return docs

    async def _walk_court(self, court: HcCourt, docs: list[RawDocument]) -> dict[str, int]:
        """Walk one court's listing, appending qualifying docs to ``docs`` (shared budget)."""
        stat = {"listed": 0, "fetched": 0, "qualifying": 0}
        response = await self._client.get(court.listing_url)
        # None -> robots-disallowed; non-200 (incl. 304 unchanged) -> nothing this run.
        if response is None or response.status_code != 200:
            return stat
        urls = extract_pdf_urls(response.text, court.base_url)
        stat["listed"] = len(urls)
        for url in urls[: self._max_fetch]:
            if len(docs) >= self._max_docs:
                break  # global per-run extraction budget reached
            pdf = await self._client.get(url)
            if pdf is None or pdf.status_code != 200:
                continue
            stat["fetched"] += 1
            text = self._pdf_to_text(pdf.content)
            if not qualifies(text):
                continue  # dropped by the local statute pre-filter — no model ever sees it
            stat["qualifying"] += 1
            docs.append(
                RawDocument(
                    url=url,
                    publisher=court.court,
                    fetched_at=self._fetched_at,
                    text=text,
                )
            )
        return stat
