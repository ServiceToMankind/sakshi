"""Unit tests for the graduated auto-publish gate."""

from __future__ import annotations

from typing import Any

from pipeline.gates import auto_publish_eligible


def _record(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "minor_involved": False,
        "confidence": 0.95,
        "accused": [
            {"label": "Accused #1", "name_public_court_record": None, "status": "UNDER_TRIAL"}
        ],
        "sources": [
            {"url": "https://example.invalid/x", "publisher": "eCourts", "source_type": "court"}
        ],
    }
    base.update(overrides)
    return base


def test_clean_non_minor_court_record_is_eligible() -> None:
    ok, reasons = auto_publish_eligible(_record())
    assert ok is True and reasons == []


def test_minor_is_held() -> None:
    ok, reasons = auto_publish_eligible(_record(minor_involved=True))
    assert ok is False and "minor_involved" in reasons


def test_named_accused_is_held() -> None:
    rec = _record(
        accused=[
            {"label": "Accused #1", "name_public_court_record": "A. Person", "status": "CONVICTED"}
        ]
    )
    ok, reasons = auto_publish_eligible(rec)
    assert ok is False and "named_accused" in reasons


def test_live_blog_only_is_held() -> None:
    rec = _record(
        sources=[
            {"url": "https://example.invalid/lb", "publisher": "X", "source_type": "live_blog"}
        ]
    )
    ok, reasons = auto_publish_eligible(rec)
    assert ok is False and "live_blog_only" in reasons


def test_a_single_durable_source_among_live_blogs_is_eligible() -> None:
    rec = _record(
        sources=[
            {"url": "https://example.invalid/lb", "publisher": "X", "source_type": "live_blog"},
            {
                "url": "https://example.invalid/n",
                "publisher": "The Hindu",
                "source_type": "news_article",
            },
        ]
    )
    ok, reasons = auto_publish_eligible(rec)
    assert ok is True and reasons == []


def test_confidence_below_auto_threshold_is_held() -> None:
    ok, reasons = auto_publish_eligible(_record(confidence=0.84))
    assert ok is False and "confidence_below_auto" in reasons
    # Exactly at the threshold is eligible.
    ok2, _ = auto_publish_eligible(_record(confidence=0.85))
    assert ok2 is True


def test_press_release_is_durable() -> None:
    rec = _record(
        sources=[
            {
                "url": "https://example.invalid/pr",
                "publisher": "PIB",
                "source_type": "press_release",
            }
        ]
    )
    ok, _ = auto_publish_eligible(rec)
    assert ok is True


def test_pocso_category_non_minor_is_held() -> None:
    # POCSO applies only to minors, so a POCSO signal flagged non-minor is suspect.
    ok, reasons = auto_publish_eligible(_record(category="pocso", minor_involved=False))
    assert ok is False and "pocso_minor_mismatch" in reasons


def test_pocso_offence_section_non_minor_is_held() -> None:
    ok, reasons = auto_publish_eligible(
        _record(offence_sections=["BNS 64", "POCSO 6"], minor_involved=False)
    )
    assert ok is False and "pocso_minor_mismatch" in reasons


def test_non_pocso_non_minor_is_eligible() -> None:
    ok, reasons = auto_publish_eligible(
        _record(category="rape", offence_sections=["BNS 64"], minor_involved=False)
    )
    assert ok is True and reasons == []


def test_multiple_reasons_accumulate() -> None:
    rec = _record(
        minor_involved=True,
        confidence=0.5,
        sources=[
            {"url": "https://example.invalid/lb", "publisher": "X", "source_type": "live_blog"}
        ],
    )
    ok, reasons = auto_publish_eligible(rec)
    assert ok is False
    assert {"minor_involved", "live_blog_only", "confidence_below_auto"} <= set(reasons)
