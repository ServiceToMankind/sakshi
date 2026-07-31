"""Tests for coverage + trackability reporting (§3)."""

from __future__ import annotations

from typing import Any

from pipeline.coverage import build_coverage, is_court_anchored
from pipeline.states import CANONICAL_STATES


def _rec(rid: str, state: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"id": rid, "state": state}
    base.update(over)
    return base


def test_is_court_anchored_cnr_or_fir() -> None:
    assert is_court_anchored({"cnr": "DLHC01-000123-2026"}) is True
    fir = {
        "fir_ref": {"station": "X PS", "number": "45/2026"},
        "incident_reported_date": "2026-01-01",
    }
    assert is_court_anchored(fir) is True
    assert is_court_anchored({"state": "DL"}) is False  # media-only, not re-checkable


def test_build_coverage_trackability_rate() -> None:
    records = [
        _rec("A", "DL", cnr="C-1"),  # anchored
        _rec("B", "DL"),  # not anchored
        _rec("C", "TG", cnr="C-2"),  # anchored
        _rec("D", "TG"),  # not anchored
    ]
    configs = [
        {"state": "national", "type": "ecourts", "enabled": True},
        {"state": "DL", "type": "rss", "enabled": True},
        {"state": "TG", "type": "rss", "enabled": False},  # disabled -> not counted
    ]
    cov = build_coverage(configs, records, "2026-07-31")
    assert cov["trackability"] == {"total": 4, "court_anchored": 2, "rate": 0.5}
    assert cov["national_sources"] == 1
    assert cov["states"]["DL"] == {"active_sources": 1, "records": 2, "declared_gap": False}
    # TG has records but no ACTIVE source -> still covered (not a declared gap).
    assert cov["states"]["TG"] == {"active_sources": 0, "records": 2, "declared_gap": False}


def test_build_coverage_declares_gaps_for_every_state() -> None:
    cov = build_coverage([], [], "2026-07-31")
    assert cov["trackability"] == {"total": 0, "court_anchored": 0, "rate": 0.0}
    assert set(cov["states"]) == set(CANONICAL_STATES)  # every state/UT is a block
    assert cov["states_total"] == len(CANONICAL_STATES)
    assert cov["states_covered"] == 0
    assert all(s["declared_gap"] for s in cov["states"].values())  # all gaps when empty
