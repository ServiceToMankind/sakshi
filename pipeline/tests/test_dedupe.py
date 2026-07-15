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


def test_merge_preserves_verified_flag_from_either_copy() -> None:
    """A case is verified if ANY copy in its cluster was verified — a fresh verified copy
    that merges (as secondary) into a carried-over UNVERIFIED copy must keep `verified`,
    else the verifier-live publish gate would wrongly hold/quarantine a confirmed case."""
    carried = _record(cnr="C-1", minor_involved=False)  # no `verified` key (carryover)
    fresh = _record(cnr="C-1", minor_involved=False, verified=True, verification_note="ok")
    merged = merge_records(carried, fresh)
    assert merged["verified"] is True
    assert merged.get("verification_note") == "ok"
    # And a merge of two unverified copies stays unverified (no key invented).
    both = merge_records(_record(cnr="C-2"), _record(cnr="C-2"))
    assert both.get("verified") is None


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


def test_fir_year_distinguishes_same_number_across_years() -> None:
    a = _record(fir_ref={"station": "X PS", "number": "45"}, incident_reported_date="2020-01-01")
    b = _record(fir_ref={"station": "X PS", "number": "45"}, incident_reported_date="2023-01-01")
    assert match_strength(a, b) == "none"  # same station+number, different year -> distinct
    published, _ = dedupe([a, b])
    assert len(published) == 2


def test_cnr_only_and_fir_only_merge_via_fuzzy() -> None:
    a = _record(cnr="C-1", court={"name": "Special POCSO Court, TESTVILLE", "next_hearing": None})
    b = _record(
        fir_ref={"station": "TESTVILLE PS", "number": "9/2026"},
        court={"name": "Special POCSO Court, TESTVILLE", "next_hearing": None},
    )
    # Disjoint anchor types (CNR-only vs FIR-only) fall through to fuzzy signals.
    assert match_strength(a, b) == "strong"
    published, _ = dedupe([a, b])
    assert len(published) == 1


def test_age_bearing_record_is_quarantined() -> None:
    """A non-minor record whose summary states an age routes to review, not a shard."""
    rec = _record(
        cnr="C-1",
        minor_involved=False,
        summary="Police rescued a 17-year-old; the accused was arrested.",
    )
    published, review = dedupe([rec])
    assert published == []
    assert review[0]["reason"] == "age_detail_present"


def test_projected_minor_summary_is_not_quarantined() -> None:
    """The fixed minor template carries no age token, so a projected minor publishes."""
    from pipeline.sanitize import MINOR_SUMMARY_TEMPLATE

    rec = _record(cnr="C-2", minor_involved=True, summary=MINOR_SUMMARY_TEMPLATE)
    published, review = dedupe([rec])
    assert len(published) == 1 and review == []


def test_out_of_scope_offence_is_quarantined() -> None:
    """Layer (b): sections present but wholly non-sexual (cheque bounce) -> scope_review."""
    rec = _record(
        cnr="C-1",
        category="other",
        minor_involved=False,
        offence_sections=["NI Act 138"],
        summary="Synthetic: a cheque-bounce conviction, no sexual component.",
    )
    published, review = dedupe([rec])
    assert published == []
    assert review[0]["reason"] == "scope_review"


def test_qualifying_sexual_offence_still_publishes() -> None:
    rec = _record(cnr="C-2", offence_sections=["BNS 64"])
    published, review = dedupe([rec])
    assert len(published) == 1 and review == []


def test_merge_drops_out_of_range_status_source() -> None:
    a = _record(cnr="C-1", status="UNDER_TRIAL")
    b = _record(
        cnr="C-1",
        status="FIR_FILED",
        sources=[{"url": "u2", "publisher": "eCourts", "retrieved": "2026-07-09"}],
        status_history=[{"status": "FIR_FILED", "date": "2026-06-15", "source": 5}],  # bad index
    )
    merged = merge_records(a, b)
    history = merged.get("status_history", [])
    assert all(h["source"] < len(merged["sources"]) for h in history)
    assert not any(h["status"] == "FIR_FILED" for h in history)  # dropped, not misattributed
