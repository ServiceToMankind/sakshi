"""Tests for the Phase 9 §1 count-invariant guard (scripts/counts_guard)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.counts_guard import check_counts


def _write(dir_: Path, rel: str, obj: Any) -> None:
    p = dir_ / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _consistent_tree(root: Path) -> None:
    """A minimal, fully-consistent data tree: 2 records (TG under_trial, MP convicted)."""
    recs = [
        {
            "id": "SKS-2026-TG-000001",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
        },
        {"id": "SKS-2026-MP-000001", "state": "MP", "district": "TESTVILLE", "status": "CONVICTED"},
    ]
    _write(root, "2026/TG.json", [recs[0]])
    _write(root, "2026/MP.json", [recs[1]])
    _write(
        root,
        "summary.json",
        {
            "total": 2,
            "generated_at": "2026-08-12T00:00:00Z",
            "state_counts": {"TG": 1, "MP": 1},
            "status_counts": {"UNDER_TRIAL": 1, "CONVICTED": 1},
        },
    )
    _write(
        root,
        "jurisdictions.json",
        {
            "generated_at": "2026-08-12T00:00:00Z",
            "jurisdictions": [
                {"state": "TG", "district": "TESTVILLE", "total": 1},
                {"state": "MP", "district": "TESTVILLE", "total": 1},
            ],
        },
    )
    _write(
        root,
        "index.json",
        {"generated_at": "2026-08-12T00:00:00Z", "shards": [{"records": 1}, {"records": 1}]},
    )
    _write(root, "recent.json", [{"id": "SKS-2026-TG-000001"}])
    # MP arrived via the national IK source -> active_sources 0 but records 1 => covered.
    _write(
        root,
        "coverage.json",
        {
            "generated": "2026-08-12",
            "states": {
                "TG": {"active_sources": 2, "records": 1},
                "MP": {"active_sources": 0, "records": 1},
            },
        },
    )


def test_consistent_tree_passes(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    assert check_counts(tmp_path) == []


def test_summary_total_mismatch_is_caught(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    s = json.loads((tmp_path / "summary.json").read_text())
    s["total"] = 1  # wrong
    (tmp_path / "summary.json").write_text(json.dumps(s))
    assert any("summary.total" in f for f in check_counts(tmp_path))


def test_state_count_mismatch_is_caught(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    s = json.loads((tmp_path / "summary.json").read_text())
    s["state_counts"]["MP"] = 0  # MP records hidden
    (tmp_path / "summary.json").write_text(json.dumps(s))
    assert any("state_counts[MP]" in f for f in check_counts(tmp_path))


def _set_scorecard(root: Path, rows: list[dict[str, Any]]) -> None:
    _write(
        root, "jurisdictions.json", {"generated_at": "2026-08-12T00:00:00Z", "jurisdictions": rows}
    )


def test_state_with_records_missing_from_scorecard_is_caught(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    _set_scorecard(tmp_path, [{"state": "TG", "district": "TESTVILLE", "total": 1}])  # MP dropped
    findings = check_counts(tmp_path)
    assert any("scorecard missing" in f and "MP" in f for f in findings)
    assert any("scorecard total=1" in f for f in findings)


def test_district_missing_from_scorecard_is_caught_even_when_its_state_is_present(
    tmp_path: Path,
) -> None:
    """The 2026-10 failure class: a capped scorecard kept every STATE but dropped a district's
    records. A per-state check passes that; the per-district + total invariant must not."""
    _consistent_tree(tmp_path)
    _write(
        tmp_path,
        "2026/TG.json",
        [
            {
                "id": "SKS-2026-TG-000001",
                "state": "TG",
                "district": "TESTVILLE",
                "status": "UNDER_TRIAL",
            },
            {
                "id": "SKS-2026-TG-000002",
                "state": "TG",
                "district": "FAKEPUR",
                "status": "UNDER_TRIAL",
            },
        ],
    )
    findings = check_counts(tmp_path)
    assert any("scorecard missing 1 district" in f and "FAKEPUR" in f for f in findings)


def test_scorecard_row_total_mismatch_is_caught(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    _set_scorecard(
        tmp_path,
        [
            {"state": "TG", "district": "TESTVILLE", "total": 2},  # over-counts
            {"state": "MP", "district": "TESTVILLE", "total": 1},
        ],
    )
    findings = check_counts(tmp_path)
    assert any("('TG', 'TESTVILLE') total=2" in f for f in findings)


def test_duplicate_scorecard_row_is_caught(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    row = {"state": "TG", "district": "TESTVILLE", "total": 1}
    _set_scorecard(tmp_path, [row, row, {"state": "MP", "district": "TESTVILLE", "total": 1}])
    assert any("duplicate row" in f for f in check_counts(tmp_path))


def test_missing_scorecard_file_is_caught_when_records_exist(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    (tmp_path / "jurisdictions.json").unlink()
    assert any("jurisdictions.json is missing" in f for f in check_counts(tmp_path))


def test_state_shown_as_uncovered_despite_records_is_caught(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    c = json.loads((tmp_path / "coverage.json").read_text())
    c["states"]["MP"] = {"active_sources": 0, "records": 0}  # hides MP's real record
    (tmp_path / "coverage.json").write_text(json.dumps(c))
    findings = check_counts(tmp_path)
    assert any("MP" in f for f in findings)


def test_missing_generated_at_fails_the_footer(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    s = json.loads((tmp_path / "summary.json").read_text())
    s["generated_at"] = ""
    (tmp_path / "summary.json").write_text(json.dumps(s))
    assert any("generated_at" in f for f in check_counts(tmp_path))


def test_orphan_recent_record_is_caught(tmp_path: Path) -> None:
    _consistent_tree(tmp_path)
    _write(tmp_path, "recent.json", [{"id": "SKS-2026-TG-000001"}, {"id": "SKS-9999-XX-000000"}])
    assert any("recent.json" in f for f in check_counts(tmp_path))
