"""A discover-only source over community case submissions (§6).

Fetches each submitted public URL (robots-respecting, via the polite client) and yields it
as a :class:`RawDocument` so the submission enters the normal extract -> sanitize -> verify
-> pii_guard path — a LEAD, never a record. The fetched page text is a HIGH-PII input (like
any source, §1b): it lives ONLY in the in-memory RawDocument, never written to disk, logged,
or cached. A robots-disallowed or unfetchable URL yields nothing (no fabrication).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from pipeline.sources.base import RawDocument
from pipeline.sources.http import HttpGetter
from pipeline.submissions import Submission

__all__ = ["SubmissionsSource", "extract_page_text"]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
# Max chars of fetched page text kept in memory (HIGH-PII bound + extraction cost cap).
_MAX_PAGE_CHARS = 20000


def extract_page_text(html: str) -> str:
    """Strip a submitted page to bounded plain text (drop script/style content, remove tags,
    collapse whitespace). Coarse by design — the extractor's schema-constrained fields, not
    this text, are what ship; the text itself is HIGH-PII and never leaves memory."""
    if not html:
        return ""
    stripped = _SCRIPT_STYLE_RE.sub(" ", html)
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", stripped)).strip()[:_MAX_PAGE_CHARS]


class SubmissionsSource:
    """A :class:`~pipeline.sources.base.Source` over parsed community submissions."""

    def __init__(
        self,
        client: HttpGetter,
        submissions: Sequence[Submission],
        fetched_at: str | None = None,
    ) -> None:
        self._client = client
        self._submissions = list(submissions)
        self._fetched_at = fetched_at or date.today().isoformat()
        # URLs whose robots.txt disallowed the fetch this run (for the ops report; no body).
        self.disallowed: set[str] = set()

    async def fetch(self) -> list[RawDocument]:
        docs: list[RawDocument] = []
        for sub in self._submissions:
            try:
                response = await self._client.get(sub.url)
            except Exception:
                continue  # a submission we cannot fetch yields nothing; never breaks the run
            if response is None:
                self.disallowed.add(sub.url)  # robots-disallowed
                continue
            if response.status_code != 200:
                continue
            text = extract_page_text(response.text)
            if not text:
                continue
            docs.append(
                RawDocument(
                    url=sub.url,
                    publisher="Community submission",
                    fetched_at=self._fetched_at,
                    text=text,
                )
            )
        return docs
