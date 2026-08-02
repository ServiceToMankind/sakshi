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

from typing import Any, Final

__all__ = [
    "LEGAL_PRESS_PUBLISHERS",
    "OFFICIAL_PUBLISHERS",
    "SOURCE_TIER",
    "SOURCE_TYPES",
    "classify_source_type",
    "has_court_source",
    "is_legal_press_publisher",
    "is_official_publisher",
    "record_tier",
]

# Publishers treated as official/court authorities (case-insensitive substring).
# NOTE: "indian kanoon" is deliberately NOT here — it is a MIRROR, not an authority.
# A record from Indian Kanoon is court-grade only when its underlying docsource is an
# actual court (the IndianKanoonSource sets the publisher to that court name); an
# IK-indexed news item stays media-grade. The court markers below cover DL + TG
# High Courts, district and sessions courts.
OFFICIAL_PUBLISHERS: Final[frozenset[str]] = frozenset(
    {
        "ecourts",
        "njdg",
        "high court",
        "supreme court",
        "district court",
        "sessions court",
        "sessions judge",
        "tribunal",
    }
)

# Legal-press outlets (tier 2, §3): they report COURT PROCEEDINGS and cite the case number,
# so they carry a court citation without being the primary court record. Case-insensitive
# substring. Extend via a reviewed source-suggestion.
LEGAL_PRESS_PUBLISHERS: Final[frozenset[str]] = frozenset(
    {"livelaw", "bar and bench", "bar & bench", "barandbench", "scc online", "scobserver"}
)

# The closed set of provenance classes (mirrors case.schema.json sources.source_type).
SOURCE_TYPES: Final[frozenset[str]] = frozenset(
    {"court", "legal_press", "news_article", "live_blog", "press_release"}
)

# Source epistemic TIER (§3): the record is the strongest (lowest) tier among its sources.
#   1 court        — the record (CNR/status/pendency/names)
#   2 legal_press  — court proceedings reported by a legal outlet, with a court citation
#   3 news_article / press_release — incident/arrest/FIR reports; no court record yet
#   4 live_blog    — rolling coverage (quarantine only)
SOURCE_TIER: Final[dict[str, int]] = {
    "court": 1,
    "legal_press": 2,
    "news_article": 3,
    "press_release": 3,
    "live_blog": 4,
}

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


def is_legal_press_publisher(publisher: str) -> bool:
    """True if ``publisher`` names a legal-press outlet (tier 2, court-citing)."""
    lowered = publisher.lower()
    return any(name in lowered for name in LEGAL_PRESS_PUBLISHERS)


def classify_source_type(url: str, publisher: str) -> str:
    """Classify one source into court | legal_press | live_blog | press_release | news_article.

    Deterministic and order-sensitive: an official publisher is a court record regardless of
    URL; a legal-press outlet is tier-2 next; otherwise a live-blog URL marker wins over a
    press-release marker, which wins over a plain news article.
    """
    if is_official_publisher(publisher):
        return "court"
    if is_legal_press_publisher(publisher):
        return "legal_press"
    haystack = f"{url} {publisher}".lower()
    if any(marker in haystack for marker in _LIVE_BLOG_MARKERS):
        return "live_blog"
    if any(marker in haystack for marker in _PRESS_RELEASE_MARKERS):
        return "press_release"
    return "news_article"


def record_tier(record: dict[str, Any]) -> int:
    """The record's epistemic tier (§3): the STRONGEST (lowest) tier among its sources, or 3
    (media-grade) when a source's type is unknown/absent. A court source makes it tier 1."""
    sources = record.get("sources") or []
    tiers = [SOURCE_TIER.get(str(s.get("source_type", "")), 3) for s in sources]
    return min(tiers) if tiers else 3


def has_court_source(record: dict[str, Any]) -> bool:
    """True if any of the record's sources is a court record (tier 1) — i.e. the case has been
    traced to the judicial record."""
    return any(str(s.get("source_type", "")) == "court" for s in (record.get("sources") or []))
