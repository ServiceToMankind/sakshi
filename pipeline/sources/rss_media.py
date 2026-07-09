"""Established-outlet RSS media source (STUB).

Fetches article text from the RSS feeds of established outlets ONLY (e.g. The
Hindu, Indian Express, PTI). NO social-media scraping. Media is a lower-priority
source than official court records: names of the accused are NEVER taken from
media alone -- a media-only record carries
``name_public_court_record: null``.

Conduct obligations (enforced when implemented): robots.txt, honest User-Agent
naming the project + repo URL, <= 1 request / 2s per host, ETag/Last-Modified
caching, exponential backoff on 429/5xx.

Full implementation lands in the pipeline phase.
"""

from __future__ import annotations

from collections.abc import Sequence

from pipeline.sources.base import RawDocument, Source

__all__ = ["RssMediaSource"]


class RssMediaSource(Source):
    """Source drawing from the RSS feeds of established news outlets."""

    def __init__(self, feed_urls: Sequence[str]) -> None:
        """Store the allow-listed feed URLs to poll.

        Args:
            feed_urls: RSS feed URLs of established outlets only.
        """
        self._feed_urls: tuple[str, ...] = tuple(feed_urls)

    def fetch(self) -> list[RawDocument]:
        """Return already-public article documents from the configured feeds.

        TODO(pipeline-phase): implement polite RSS polling with conditional
        requests and per-host rate limiting.
        """
        raise NotImplementedError("RssMediaSource.fetch is implemented in the pipeline phase")
