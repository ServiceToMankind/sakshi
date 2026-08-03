"""Established-outlet RSS/Atom media source.

Polls the public syndication feeds of established outlets (The Hindu, The Indian
Express, PTI, ...) and returns one :class:`RawDocument` per entry. By default it carries
the title and summary text only. When article-body fetching is enabled
(``config.article_body_enabled``, the amnesiac-discovery fix), the daily ``discover`` run
ALSO fetches the linked article and folds its body into the same in-memory
``RawDocument.text`` — never to disk.

**The article body is a HIGH-PII input (§1b).** Like a court judgment, it may contain a
victim's name, age, family, village, or school. It therefore lives ONLY in the in-memory
``RawDocument.text``; it is never written to disk, logged, cached, or placed in an error or
cost sample. A body is fetched only when the outlet's robots.txt allows it (the polite
client returns ``None`` on disallow), and only in ``discover`` (``court_only`` refresh skips
media entirely). Downstream stages (extract -> sanitize) still guarantee victim identity
never survives to disk.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

from pipeline import config
from pipeline.sources.base import RawDocument
from pipeline.sources.http import HttpGetter

_ATOM = "{http://www.w3.org/2005/Atom}"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# <script>/<style> blocks carry no article text — drop their CONTENT before stripping tags.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)

__all__ = ["DEFAULT_FEEDS", "Feed", "RssMediaSource", "extract_article_text", "parse_feed"]


def extract_article_text(html: str) -> str:
    """Strip an HTML page to plain body text, bounded to ``config.ARTICLE_BODY_CHARS``.

    A deliberately dependency-free strip (drop script/style content, remove tags, collapse
    whitespace). Coarse by design — the extractor's schema-constrained fields, not this
    text, are what ship; the text itself is HIGH-PII and never leaves memory.
    """
    if not html:
        return ""
    stripped = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", stripped)).strip()
    return text[: config.ARTICLE_BODY_CHARS]


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
        fetch_body: bool = False,
    ) -> None:
        self._client = client
        self._feeds = feeds
        self._fetched_at = fetched_at or date.today().isoformat()
        self._fetch_body = fetch_body
        # Outlets whose robots.txt disallowed the article fetch this run (publisher names
        # only — never a body). Read after fetch() for the operator report.
        self.disallowed_outlets: set[str] = set()

    async def fetch(self) -> list[RawDocument]:
        docs: list[RawDocument] = []
        for feed in self._feeds:
            response = await self._client.get(feed.url)
            # None -> robots-disallowed; non-200 (incl. 304 unchanged) -> skip.
            if response is None or response.status_code != 200:
                continue
            docs.extend(parse_feed(response.text, feed.publisher, self._fetched_at))
        if self._fetch_body:
            docs = [await self._augment_with_body(doc) for doc in docs]
        return docs

    async def _augment_with_body(self, doc: RawDocument) -> RawDocument:
        """Fold the linked article's body into ``doc.text`` (in memory only), or return
        ``doc`` unchanged if robots disallows it, the fetch fails, or the body is empty.

        The body NEVER touches disk, a log, or an error/cost sample — only this returned
        RawDocument.text, which downstream treats as untrusted in-memory source text (§1b).
        A failed body fetch degrades to the syndicated blurb; it never breaks the run.
        """
        try:
            response = await self._client.get(doc.url)
        except Exception:
            return doc  # a body-fetch error never aborts discovery — keep the blurb
        if response is None:
            # robots.txt disallowed this host — record the outlet (no body), keep the blurb.
            self.disallowed_outlets.add(doc.publisher)
            return doc
        if response.status_code != 200:
            return doc
        body = extract_article_text(response.text)
        if not body:
            return doc
        combined = f"{doc.text} {body}".strip()[: config.ARTICLE_BODY_CHARS]
        return RawDocument(
            url=doc.url, publisher=doc.publisher, fetched_at=doc.fetched_at, text=combined
        )
