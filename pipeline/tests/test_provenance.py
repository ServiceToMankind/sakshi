"""Tests for source-provenance classification (issue #7)."""

from __future__ import annotations

from pipeline.provenance import SOURCE_TYPES, classify_source_type, is_official_publisher


def test_official_publisher_is_a_court_record() -> None:
    assert classify_source_type("https://services.ecourts.gov.in/x", "eCourts") == "court"
    assert classify_source_type("https://x.invalid/a", "High Court of Telangana") == "court"


def test_live_blog_url_marker_wins() -> None:
    url = "https://example.invalid/india/today-live-updates-delhi-fire-10772012"
    assert classify_source_type(url, "The Example Herald") == "live_blog"


def test_press_release_marker() -> None:
    assert (
        classify_source_type("https://pib.gov.in/PressReleasePage.aspx", "PIB") == "press_release"
    )


def test_plain_news_article_is_the_default() -> None:
    url = "https://example.invalid/india/some-reported-case"
    assert classify_source_type(url, "The Example Herald") == "news_article"


def test_is_official_publisher() -> None:
    assert is_official_publisher("eCourts")
    assert is_official_publisher("XYZ Sessions Court")  # DL/TG district & sessions courts
    assert not is_official_publisher("The Example Herald")


def test_indian_kanoon_is_not_a_blanket_court_authority() -> None:
    """IK is a MIRROR: the docsource (a court) confers court-grade, not the IK name."""
    assert not is_official_publisher("Indian Kanoon")
    assert (
        classify_source_type("https://indiankanoon.org/doc/1/", "Indian Kanoon") == "news_article"
    )
    assert classify_source_type("https://indiankanoon.org/doc/1/", "Delhi High Court") == "court"
    assert classify_source_type("https://indiankanoon.org/doc/1/", "XYZ Sessions Court") == "court"


def test_every_classification_is_a_known_source_type() -> None:
    results = {
        classify_source_type("https://x/live-updates", "Media"),
        classify_source_type("https://pib.gov.in/x", "PIB"),
        classify_source_type("https://x/report", "Media"),
        classify_source_type("https://x", "eCourts"),
    }
    assert results <= SOURCE_TYPES


def test_legal_press_is_tier_two() -> None:
    from pipeline.provenance import classify_source_type

    assert classify_source_type("https://livelaw.in/x", "LiveLaw") == "legal_press"
    assert classify_source_type("https://barandbench.com/x", "Bar and Bench") == "legal_press"


def test_record_tier_is_the_strongest_source() -> None:
    from pipeline.provenance import has_court_source, record_tier

    court = {"sources": [{"source_type": "news_article"}, {"source_type": "court"}]}
    legal = {"sources": [{"source_type": "legal_press"}, {"source_type": "news_article"}]}
    media = {"sources": [{"source_type": "news_article"}]}
    assert record_tier(court) == 1 and has_court_source(court) is True
    assert record_tier(legal) == 2 and has_court_source(legal) is False
    assert record_tier(media) == 3 and has_court_source(media) is False
    assert record_tier({"sources": []}) == 3  # no sources -> media-grade default


def test_source_tier_parity_with_frontend() -> None:
    """SOURCE_TIER must match site/src/tier.js so a tier reads the same both sides (§3)."""
    import re
    from pathlib import Path

    from pipeline.provenance import SOURCE_TIER

    js = (Path(__file__).resolve().parents[2] / "site" / "src" / "tier.js").read_text()
    block = re.search(r"export const SOURCE_TIER = \{(.*?)\};", js, re.S)
    assert block is not None
    frontend = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", block.group(1))}
    assert frontend == SOURCE_TIER
