"""Source-provenance classification (issue #7).

A single source's provenance drives two decisions: dedupe AUTHORITY (an official
court record beats media) and PUBLISH policy (a record backed only by a rolling
"live updates" page is not durable enough to auto-publish — its URL decays and its
content mutates, so it is quarantined for human confirmation instead).

Kept in one module so the publisher lists and markers cannot drift between the
extractor (which stamps each source's ``source_type``), the dedupe merge (which
asks "is this a court record?"), and the confidence policy.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "OFFICIAL_PUBLISHERS",
    "SOURCE_TYPES",
    "classify_source_type",
    "is_official_publisher",
]

# Publishers treated as official/court authorities (case-insensitive substring).
OFFICIAL_PUBLISHERS: Final[frozenset[str]] = frozenset(
    {"ecourts", "njdg", "high court", "supreme court", "indian kanoon", "district court"}
)

# The closed set of provenance classes (mirrors case.schema.json sources.source_type).
SOURCE_TYPES: Final[frozenset[str]] = frozenset(
    {"court", "news_article", "live_blog", "press_release"}
)

# URL/publisher markers of a rolling "live updates" page. Its content mutates and
# its URL decays, so a single such citation is not durable provenance for a
# permanent public claim (issue #7).
_LIVE_BLOG_MARKERS: Final[tuple[str, ...]] = (
    "live-updates",
    "live-update",
    "live-blog",
    "liveblog",
    "/live/",
    "-live-news",
    "live-news",
    "as-it-happened",
)

# Markers of an official press release (a primary but non-adjudicative source).
_PRESS_RELEASE_MARKERS: Final[tuple[str, ...]] = (
    "pib.gov.in",
    "press-release",
    "pressrelease",
    "press-information-bureau",
    "/pib/",
)


def is_official_publisher(publisher: str) -> bool:
    """True if ``publisher`` names an official/court authority."""
    lowered = publisher.lower()
    return any(name in lowered for name in OFFICIAL_PUBLISHERS)


def classify_source_type(url: str, publisher: str) -> str:
    """Classify one source into court | live_blog | press_release | news_article.

    Deterministic and order-sensitive: an official publisher is a court record
    regardless of URL; otherwise a live-blog URL marker wins over a press-release
    marker, which wins over a plain news article.
    """
    if is_official_publisher(publisher):
        return "court"
    haystack = f"{url} {publisher}".lower()
    if any(marker in haystack for marker in _LIVE_BLOG_MARKERS):
        return "live_blog"
    if any(marker in haystack for marker in _PRESS_RELEASE_MARKERS):
        return "press_release"
    return "news_article"
