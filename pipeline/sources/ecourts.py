"""eCourts / NJDG source (STUB).

Fetches ALREADY-PUBLIC judicial records from the eCourts services and the
National Judicial Data Grid: cause lists, case status (CNR), and judgment/order
metadata. This is an official/structured source and therefore takes priority
over media when the dedupe stage merges records.

Conduct obligations (enforced when implemented):
- Respect robots.txt.
- Honest User-Agent naming the project + repo URL.
- Rate-limit to <= 1 request / 2s per host; ETag/Last-Modified caching;
  exponential backoff on 429/5xx.

Full implementation lands in the pipeline phase.
"""

from __future__ import annotations

from pipeline.sources.base import RawDocument, Source

__all__ = ["ECourtsSource"]


class ECourtsSource(Source):
    """Source drawing from eCourts services and the NJDG."""

    def fetch(self) -> list[RawDocument]:
        """Return already-public eCourts/NJDG documents.

        TODO(pipeline-phase): implement polite httpx+asyncio fetching with
        per-host rate limiting and conditional-request caching.
        """
        raise NotImplementedError("ECourtsSource.fetch is implemented in the pipeline phase")
