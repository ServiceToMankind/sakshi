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
    assert not is_official_publisher("The Example Herald")


def test_every_classification_is_a_known_source_type() -> None:
    results = {
        classify_source_type("https://x/live-updates", "Media"),
        classify_source_type("https://pib.gov.in/x", "PIB"),
        classify_source_type("https://x/report", "Media"),
        classify_source_type("https://x", "eCourts"),
    }
    assert results <= SOURCE_TYPES
