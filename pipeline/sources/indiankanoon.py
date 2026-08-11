"""Indian Kanoon source — court judgments via the documented API (search + doc fetch).

Indian Kanoon (https://api.indiankanoon.org) mirrors Indian judgments and orders. Its API is
the ONE legitimate, ToS-covered way to pull court records programmatically without touching a
CAPTCHA. Access is token-authenticated and PAID: set ``INDIANKANOON_API_TOKEN``. Without the
token this source fetches nothing (never fabricates).

Flow (per query):
  1. POST ``/search/`` → judgment HITS (tid, title, headline, docsource, publishdate).
  2. LOCAL statute pre-filter on the HIT (title + headline) — only a hit that cites a
     sexual-offence statute or names the offence is fetched, so a non-qualifying document is
     NEVER billed. Report the qualifying rate.
  3. POST ``/doc/{tid}/`` for each qualifying hit → the full JUDGMENT, which becomes the
     RawDocument text (so extraction reads the whole judgment, not a metadata snippet — the
     defect this fixes). Doc fetches count against ``config.IK_MAX_DOCS_PER_RUN`` (the bill).

**The judgment body is the highest-PII input the project has (§1b).** It lives ONLY in the
in-memory ``RawDocument.text``; it is never written to disk, logged, cached, or placed in an
error/cost sample. Extraction emits schema-constrained fields only (CNR, case number, court,
status, judgment date, offence sections, accused_count/repeat/weapon/institutional_actions/
sentence — plus court-recorded accused names, §5); the sanitizer + identity_scan + pii_guard
strip any victim identity a model nonetheless emits. The publisher is the ``docsource`` (the
court), so the record classifies court-grade (tier 1).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import date

from pipeline import config
from pipeline.sources.base import RawDocument
from pipeline.sources.hc_judgments import qualifies as _statute_qualifies
from pipeline.sources.http import HttpPoster

__all__ = [
    "IndianKanoonSource",
    "hit_qualifies",
    "parse_search_hits",
    "render_judgment_text",
]

_SEARCH_URL = "https://api.indiankanoon.org/search/"
_DOC_URL = "https://api.indiankanoon.org/doc/{tid}/"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
# Offence keywords the IK search targets. A hit is billed only if it cites a qualifying statute
# (hc_judgments.qualifies) OR names the offence — so an off-topic hit that slipped into the
# result set is dropped BEFORE the paid doc fetch, while a real case whose snippet says only
# "rape"/"POCSO" (no section number) is still fetched.
_OFFENCE_KEYWORDS_RE = re.compile(
    r"\b(?:rape|pocso|sexual\s+assault|sexual\s+offence|molest\w*|gang[\s-]?rape|"
    r"outrag\w+\s+\w*\s*modesty)\b",
    re.IGNORECASE,
)


def _api_token() -> str | None:
    token = os.environ.get("INDIANKANOON_API_TOKEN", "").strip()
    return token or None


def hit_qualifies(text: str) -> bool:
    """True if a search HIT's text warrants the paid doc fetch (the pre-filter that gates
    billing). Qualifying statute OR a named sexual offence; empty text never qualifies."""
    if not text:
        return False
    return _statute_qualifies(text) or _OFFENCE_KEYWORDS_RE.search(text) is not None


def parse_search_hits(payload: str) -> list[dict[str, str]]:
    """Parse an Indian Kanoon ``/search/`` JSON payload into hit dicts (tid/title/headline/
    docsource/publishdate). Malformed JSON, or a hit without an id, is skipped rather than
    raising, so one bad response never breaks a run."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    docs_in = data.get("docs", []) if isinstance(data, dict) else []
    hits: list[dict[str, str]] = []
    for hit in docs_in:
        if not isinstance(hit, dict):
            continue
        tid = hit.get("tid")
        if tid in (None, ""):
            continue
        hits.append(
            {
                "tid": str(tid),
                "title": str(hit.get("title", "")),
                "headline": str(hit.get("headline", "")),
                "docsource": str(hit.get("docsource", "")),
                "publishdate": str(hit.get("publishdate", "")),
            }
        )
    return hits


def render_judgment_text(
    doc_json: Mapping[str, object], *, max_chars: int = config.IK_DOC_MAX_CHARS
) -> str:
    """Render a ``/doc/{tid}/`` JSON response into plain judgment text for extraction.

    A compact public-metadata header (court, title, date) precedes the HTML-stripped judgment
    body, bounded to ``max_chars`` (a HIGH-PII + cost cap). Returns ``""`` if the body is empty.
    The returned text is HIGH-PII and must never leave the in-memory RawDocument.
    """
    raw = doc_json.get("doc")
    if not isinstance(raw, str) or not raw:
        return ""
    stripped = _SCRIPT_STYLE_RE.sub(" ", raw)
    body = _WS_RE.sub(" ", _TAG_RE.sub(" ", stripped)).strip()
    if not body:
        return ""
    header_parts = []
    for key, label in (("docsource", "Court"), ("title", "Title"), ("publishdate", "Date")):
        value = doc_json.get(key)
        if isinstance(value, str) and value.strip():
            header_parts.append(f"{label}: {value.strip()}")
    header = ". ".join(header_parts)
    combined = f"{header}. {body}" if header else body
    return combined[:max_chars]


def _doc_publisher(docsource: str, fallback: str) -> str:
    """The docsource IS the provenance authority: a judgment's docsource is its court (e.g.
    "Delhi High Court"), which downstream classifies as court-grade; a missing docsource stays
    media-grade so accused names are withheld."""
    return docsource.strip() or fallback


class IndianKanoonSource:
    """A :class:`~pipeline.sources.base.Source` over the Indian Kanoon search + doc API.

    ``stats`` (counts only — never a URL or any text) records, per run: ``hits`` seen,
    ``qualifying`` after the pre-filter, and ``fetched`` doc bodies (the billed count).
    """

    SOURCE_LABEL = "Indian Kanoon"

    def __init__(
        self,
        client: HttpPoster,
        queries: tuple[str, ...],
        *,
        publisher: str = "Indian Kanoon",
        fetched_at: str | None = None,
        token: str | None = None,
    ) -> None:
        self._client = client
        self._queries = queries
        self._publisher = publisher
        self._fetched_at = fetched_at or date.today().isoformat()
        self._token = token if token is not None else _api_token()
        self.stats: dict[str, int] = {"hits": 0, "qualifying": 0, "fetched": 0}

    async def fetch(self) -> list[RawDocument]:
        """Search each query, statute-pre-filter each hit, then fetch the judgment body for
        the qualifying ones (capped at ``config.IK_MAX_DOCS_PER_RUN`` billed doc fetches).

        No token => fetch nothing (safe). The judgment body is HIGH-PII and never leaves the
        returned in-memory RawDocument.
        """
        if not self._token:
            return []
        headers = {"Authorization": f"Token {self._token}"}
        docs: list[RawDocument] = []
        for query in self._queries:
            if len(docs) >= config.IK_MAX_DOCS_PER_RUN:
                break
            response = await self._client.post(
                _SEARCH_URL, data={"formInput": query, "pagenum": "0"}, headers=headers
            )
            if response is None or response.status_code != 200:
                continue
            for hit in parse_search_hits(response.text):
                if len(docs) >= config.IK_MAX_DOCS_PER_RUN:
                    break
                self.stats["hits"] += 1
                if not hit_qualifies(f"{hit['title']} {hit['headline']}"):
                    continue  # pre-filter: skip the paid doc fetch for an off-topic hit
                self.stats["qualifying"] += 1
                doc = await self._client.post(_DOC_URL.format(tid=hit["tid"]), headers=headers)
                if doc is None or doc.status_code != 200:
                    continue
                self.stats["fetched"] += 1  # a billed doc fetch
                text = self._judgment_text(doc.text, hit)
                if not text:
                    continue
                docs.append(
                    RawDocument(
                        url=f"https://indiankanoon.org/doc/{hit['tid']}/",
                        publisher=_doc_publisher(hit["docsource"], self._publisher),
                        fetched_at=self._fetched_at,
                        text=text,
                    )
                )
        return docs[: config.IK_MAX_DOCS_PER_RUN]

    def _judgment_text(self, payload: str, hit: dict[str, str]) -> str:
        """Parse a /doc/ payload to judgment text, falling back to the hit's docsource/date
        header if the payload lacks them. Malformed JSON => empty (skip, never raise)."""
        try:
            doc_json = json.loads(payload)
        except json.JSONDecodeError:
            return ""
        if not isinstance(doc_json, dict):
            return ""
        doc_json.setdefault("docsource", hit["docsource"])
        doc_json.setdefault("publishdate", hit["publishdate"])
        doc_json.setdefault("title", hit["title"])
        return render_judgment_text(doc_json)
