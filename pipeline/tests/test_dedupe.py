"""Tests for case-anchored deduplication and merging (synthetic TESTVILLE data)."""

from __future__ import annotations

from typing import Any

from pipeline.dedupe import dedupe, is_court_record, match_strength, merge_records


def _record(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "state": "TG",
        "district": "TESTVILLE",
        "category": "pocso",
        "status": "FIR_FILED",
        "minor_involved": True,
        "incident_reported_date": "2026-06-14",
        "offence_sections": ["BNS 64"],
        "sources": [
            {"url": "https://example.invalid/x", "publisher": "eCourts", "retrieved": "2026-07-09"}
        ],
        "confidence": 0.95,
    }
    base.update(overrides)
    return base


def test_exact_cnr_merges() -> None:
    published, review = dedupe(
        [_record(cnr="C-1", status="FIR_FILED"), _record(cnr="C-1", status="UNDER_TRIAL")]
    )
    assert len(published) == 1 and review == []
    assert published[0]["status"] == "UNDER_TRIAL"  # further-along status wins


def test_cnr_and_fir_records_merge_on_shared_fir() -> None:
    court = _record(cnr="C-9", fir_ref={"station": "TESTVILLE PS", "number": "12/2026"})
    media = _record(fir_ref={"station": "TESTVILLE PS", "number": "12/2026"})
    published, _ = dedupe([court, media])
    assert len(published) == 1  # matched on the shared FIR even though CNR differs in presence


def test_distinct_cases_stay_separate() -> None:
    published, _ = dedupe([_record(cnr="C-1"), _record(cnr="C-2")])
    assert len(published) == 2


def test_fuzzy_strong_match_merges() -> None:
    a = _record(court={"name": "Special POCSO Court, TESTVILLE", "next_hearing": None})
    b = _record(court={"name": "Special POCSO Court TESTVILLE", "next_hearing": None})
    assert match_strength(a, b) == "strong"
    published, review = dedupe([a, b])
    assert len(published) == 1 and review == []


def test_fuzzy_weak_match_goes_to_review() -> None:
    a = _record(offence_sections=[], court={})
    b = _record(offence_sections=[], court={})
    assert match_strength(a, b) == "weak"
    published, review = dedupe([a, b])
    assert len(published) == 1
    assert len(review) == 1 and review[0]["reason"] == "ambiguous_match"


def test_low_confidence_goes_to_review() -> None:
    published, review = dedupe([_record(cnr="C-1", confidence=0.5)])
    assert published == []
    assert review[0]["reason"] == "low_confidence"


def test_is_court_record() -> None:
    assert is_court_record(_record())  # eCourts publisher
    media = _record(
        sources=[{"url": "u", "publisher": "The Example Herald", "retrieved": "2026-07-09"}]
    )
    assert not is_court_record(media)


def test_merge_unions_sources_and_remaps_status_history() -> None:
    court = _record(
        cnr="C-1",
        status="UNDER_TRIAL",
        sources=[{"url": "u-court", "publisher": "eCourts", "retrieved": "2026-07-09"}],
        status_history=[{"status": "UNDER_TRIAL", "date": "2026-06-20", "source": 0}],
    )
    media = _record(
        cnr="C-1",
        status="FIR_FILED",
        confidence=0.99,  # higher, but court still wins authority
        sources=[{"url": "u-media", "publisher": "The Example Herald", "retrieved": "2026-07-09"}],
        status_history=[{"status": "FIR_FILED", "date": "2026-06-15", "source": 0}],
    )
    merged = merge_records(court, media)

    urls = [s["url"] for s in merged["sources"]]
    assert urls == ["u-court", "u-media"]  # court primary, union preserved
    assert merged["status"] == "UNDER_TRIAL"
    assert merged["confidence"] == 0.99  # confidence takes the max

    # The media status-history entry must point at u-media's NEW index (1), not 0.
    fir_entries = [h for h in merged["status_history"] if h["status"] == "FIR_FILED"]
    assert fir_entries and merged["sources"][fir_entries[0]["source"]]["url"] == "u-media"
