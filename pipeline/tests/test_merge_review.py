"""Tests for national-scale candidate-match detection (§8)."""

from __future__ import annotations

from typing import Any

from pipeline.merge_review import find_candidate_matches


def _rec(rid: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": rid,
        "state": "DL",
        "district": "Delhi",
        "category": "rape",
        "incident_reported_date": "2026-05-01",
        "offence_sections": ["IPC 376"],
    }
    base.update(over)
    return base


def test_close_dates_shared_section_is_a_candidate() -> None:
    a = _rec("SKS-2026-DL-000010")
    b = _rec("SKS-2026-DL-000011", incident_reported_date="2026-05-03")
    clusters = find_candidate_matches([a, b])
    assert len(clusters) == 1
    assert clusters[0]["ids"] == ["SKS-2026-DL-000010", "SKS-2026-DL-000011"]
    assert clusters[0]["signals"][0]["shared_sections"] == ["ipc 376"]
    assert clusters[0]["signals"][0]["days_apart"] == 2


def test_shared_accused_name_is_a_candidate_even_without_section_overlap() -> None:
    a = _rec(
        "SKS-2026-DL-000010",
        offence_sections=["IPC 376"],
        accused=[{"name_public_court_record": "John Doe"}],
    )
    b = _rec(
        "SKS-2026-DL-000011",
        offence_sections=["IPC 354"],
        accused=[{"name_public_court_record": "John Doe"}],
    )
    clusters = find_candidate_matches([a, b])
    assert len(clusters) == 1
    assert clusters[0]["signals"][0]["shared_accused"] == ["john doe"]


def test_far_apart_dates_are_not_candidates() -> None:
    a = _rec("SKS-2026-DL-000010", incident_reported_date="2026-05-01")
    b = _rec("SKS-2026-DL-000011", incident_reported_date="2026-06-30")
    assert find_candidate_matches([a, b]) == []


def test_year_only_minors_are_excluded() -> None:
    """Year-only dates never resolve to a day, so minor projections cannot match here."""
    a = _rec(
        "SKS-2026-TG-000020",
        state="TG",
        district="Hyderabad",
        category="pocso",
        incident_reported_date="2026",
        offence_sections=["POCSO 6"],
        minor_involved=True,
    )
    b = _rec(
        "SKS-2026-TG-000021",
        state="TG",
        district="Hyderabad",
        category="pocso",
        incident_reported_date="2026",
        offence_sections=["POCSO 6"],
        minor_involved=True,
    )
    assert find_candidate_matches([a, b]) == []


def test_different_district_or_category_not_candidates() -> None:
    a = _rec("SKS-2026-DL-000010", district="Delhi")
    b = _rec("SKS-2026-DL-000011", district="New Delhi")
    assert find_candidate_matches([a, b]) == []
    c = _rec("SKS-2026-DL-000012", category="harassment")
    assert find_candidate_matches([a, c]) == []


def test_shared_exact_anchor_pair_is_not_a_candidate() -> None:
    """Two records sharing a CNR would already be auto-merged by dedupe, so they are not a
    review candidate here."""
    a = _rec("SKS-2026-DL-000010", cnr="C-1")
    b = _rec("SKS-2026-DL-000011", cnr="C-1", incident_reported_date="2026-05-02")
    assert find_candidate_matches([a, b]) == []


def test_no_date_or_no_overlap_not_candidates() -> None:
    # No overlap at all (different sections, no accused) -> not a candidate.
    a = _rec("SKS-2026-DL-000010", offence_sections=["IPC 376"])
    b = _rec("SKS-2026-DL-000011", offence_sections=["IPC 354"])
    assert find_candidate_matches([a, b]) == []
    # A record without an id is ignored.
    assert find_candidate_matches([_rec(""), _rec("")]) == []
