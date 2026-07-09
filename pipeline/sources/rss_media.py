"""Established-outlet RSS/Atom media source.

Polls the public syndication feeds of established outlets (The Hindu, The Indian
Express, PTI, ...) and returns one :class:`RawDocument` per entry, carrying the
title and summary text only. This is deliberately narrow: no social media, no
full-article scraping — only what each outlet already syndicates. Media is a
lower-priority source than official court records; names of the accused are never
taken from media alone (a media-only record carries ``name_public_court_record:
null``). Downstream stages (extract -> sanitize) remain responsible for ensuring
victim identity never survives to disk.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

from pipeline.sources.base import RawDocument
from pipeline.sources.http import HttpGetter

_ATOM = "{http://www.w3.org/2005/Atom}"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

__all__ = ["DEFAULT_FEEDS", "Feed", "RssMediaSource", "parse_feed"]


@dataclass(frozen=True)
class Feed:
    """An RSS/Atom feed and the publisher it belongs to."""

    url: str
    publisher: str


# Established outlets only (Phase 0.3). Extend via a reviewed source-suggestion PR.
DEFAULT_FEEDS: tuple[Feed, ...] = (
    Feed("https://www.thehindu.com/news/national/feeder/default.rss", "The Hindu"),
    Feed("https://indianexpress.com/section/india/feed/", "The Indian Express"),
)


def _clean(text: str | None) -> str:
    """Strip HTML tags and collapse whitespace from a feed text node."""
    if not text:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def _text(node: ET.Element | None) -> str:
    return _clean(node.text if node is not None else None)


def parse_feed(xml_text: str, publisher: str, fetched_at: str) -> list[RawDocument]:
    """Parse RSS or Atom ``xml_text`` into RawDocuments (one per item/entry).

    Malformed XML yields an empty list rather than raising, so one bad feed never
    breaks a run.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    docs: list[RawDocument] = []

    # RSS 2.0: <rss><channel><item><title/><description/><link/></item></channel>
    for item in root.iter("item"):
        title = _text(item.find("title"))
        summary = _text(item.find("description"))
        link = _text(item.find("link"))
        doc = _build(title, summary, link, publisher, fetched_at)
        if doc is not None:
            docs.append(doc)

    # Atom: <feed><entry><title/><summary|content/><link href=.../></entry></feed>
    for entry in root.iter(f"{_ATOM}entry"):
        title = _text(entry.find(f"{_ATOM}title"))
        summary = _text(entry.find(f"{_ATOM}summary")) or _text(entry.find(f"{_ATOM}content"))
        link_el = entry.find(f"{_ATOM}link")
        link = link_el.get("href", "") if link_el is not None else ""
        doc = _build(title, summary, link, publisher, fetched_at)
        if doc is not None:
            docs.append(doc)

    return docs


def _build(
    title: str, summary: str, link: str, publisher: str, fetched_at: str
) -> RawDocument | None:
    if not link or not (title or summary):
        return None
    text = f"{title}. {summary}".strip(". ").strip()
    return RawDocument(url=link, publisher=publisher, fetched_at=fetched_at, text=text)


class RssMediaSource:
    """A :class:`~pipeline.sources.base.Source` over established-outlet feeds."""

    def __init__(
        self,
        client: HttpGetter,
        feeds: tuple[Feed, ...] = DEFAULT_FEEDS,
        fetched_at: str | None = None,
    ) -> None:
        self._client = client
        self._feeds = feeds
        self._fetched_at = fetched_at or date.today().isoformat()

    async def fetch(self) -> list[RawDocument]:
        docs: list[RawDocument] = []
        for feed in self._feeds:
            response = await self._client.get(feed.url)
            # None -> robots-disallowed; non-200 (incl. 304 unchanged) -> skip.
            if response is None or response.status_code != 200:
                continue
            docs.extend(parse_feed(response.text, feed.publisher, self._fetched_at))
        return docs
