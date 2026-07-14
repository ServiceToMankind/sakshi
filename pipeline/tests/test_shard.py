"""Tests for the sharded output writer (synthetic TESTVILLE data)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline import shard
from pipeline.shard import SUMMARY_MAX_BYTES, write_shards


def test_summary_budget_constant_is_50kb() -> None:
    assert SUMMARY_MAX_BYTES == 50 * 1024


def _record(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "state": "TG",
        "district": "TESTVILLE",
        "category": "sexual_assault",
        "status": "UNDER_TRIAL",
        "minor_involved": False,
        "incident_reported_date": "2026-06-14",
        "sources": [
            {"url": "https://example.invalid/x", "publisher": "eCourts", "retrieved": "2026-07-09"}
        ],
        "confidence": 0.95,
    }
    base.update(overrides)
    return base


def test_write_emits_shard_summary_index_and_assigns_id(tmp_path: Path) -> None:
    result = write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")
    assert result.published == 1 and result.new == 1 and result.updated == 0

    records = json.loads((tmp_path / "2026" / "TG.json").read_text())
    assert records[0]["id"] == "SKS-2026-TG-000001"
    assert records[0]["last_verified"] == "2026-07-09"
    assert records[0]["pending_days"] == 25

    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "summary.json").stat().st_size < SUMMARY_MAX_BYTES
    index = json.loads((tmp_path / "index.json").read_text())
    assert index["shards"][0]["path"] == "2026/TG.json"
    assert index["shards"][0]["records"] == 1


def test_ids_are_stable_across_runs(tmp_path: Path) -> None:
    write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")
    # A fresh record (no id) for the SAME case reuses the existing id -> "updated".
    result = write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-10")
    records = json.loads((tmp_path / "2026" / "TG.json").read_text())
    assert records[0]["id"] == "SKS-2026-TG-000001"
    assert result.new == 0 and result.updated == 1


def test_existing_id_is_preserved_and_new_serial_continues(tmp_path: Path) -> None:
    write_shards([_record(cnr="C-1", id="SKS-2026-TG-000005")], tmp_path, run_date="2026-07-09")
    write_shards(
        [_record(cnr="C-1", id="SKS-2026-TG-000005"), _record(cnr="C-2")],
        tmp_path,
        run_date="2026-07-09",
    )
    ids = sorted(r["id"] for r in json.loads((tmp_path / "2026" / "TG.json").read_text()))
    assert ids == ["SKS-2026-TG-000005", "SKS-2026-TG-000006"]


def test_carryover_id_reserves_serial_against_fresh_mint(tmp_path: Path) -> None:
    # Staging carryover: a record minted in a prior run (id present) is NOT yet on
    # main (empty data_dir), passed in-memory alongside a brand-new case in the same
    # (year,state) slot. The new case must NOT re-mint the carried-over serial.
    write_shards(
        [_record(cnr="C-1", id="SKS-2026-TG-000001"), _record(cnr="C-2")],
        tmp_path,
        run_date="2026-07-09",
    )
    ids = sorted(r["id"] for r in json.loads((tmp_path / "2026" / "TG.json").read_text()))
    assert ids == ["SKS-2026-TG-000001", "SKS-2026-TG-000002"]
    # Order-independence: the fresh case appearing BEFORE the carried-over id (whose
    # serial the fresh mint would otherwise claim) must still not collide, because the
    # pre-scan reserves every retained serial before any mint runs.
    fresh_dir = tmp_path / "empty_main"
    result2 = write_shards(
        [_record(cnr="C-4"), _record(cnr="C-3", id="SKS-2026-TG-000001")],
        fresh_dir,
        run_date="2026-07-10",
    )
    assert result2.published == 2
    ids2 = sorted(r["id"] for r in json.loads((fresh_dir / "2026" / "TG.json").read_text()))
    assert ids2 == ["SKS-2026-TG-000001", "SKS-2026-TG-000002"]


def test_summary_contents(tmp_path: Path) -> None:
    write_shards(
        [_record(cnr="C-1", status="UNDER_TRIAL"), _record(cnr="C-2", status="CONVICTED")],
        tmp_path,
        run_date="2026-07-09",
    )
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["total"] == 2
    assert summary["state_counts"] == {"TG": 2}
    assert summary["status_counts"] == {"CONVICTED": 1, "UNDER_TRIAL": 1}
    assert len(summary["monthly_trend"]) == 24
    # Only the active (UNDER_TRIAL) case is in the longest-pending list.
    assert [p["id"] for p in summary["top_longest_pending"]] == ["SKS-2026-TG-000001"]


def test_invalid_record_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="validation failed"):
        write_shards([_record(cnr="C-1", state="TOOLONG")], tmp_path, run_date="2026-07-09")


def test_summary_budget_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shard, "SUMMARY_MAX_BYTES", 10)
    with pytest.raises(ValueError, match="summary"):
        write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")


def test_large_shard_splits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shard, "SHARD_SPLIT_BYTES", 400)
    records = [_record(cnr=f"C-{i}") for i in range(6)]
    result = write_shards(records, tmp_path, run_date="2026-07-09")
    paths = [s for s in result.shards if s.startswith("2026/TG")]
    assert any(p.endswith("-p2.json") for p in paths)


def test_stale_shard_removed(tmp_path: Path) -> None:
    write_shards([_record(cnr="C-1", state="TG")], tmp_path, run_date="2026-07-09")
    assert (tmp_path / "2026" / "TG.json").exists()
    # A later run with only AP records must drop the now-empty TG shard.
    write_shards([_record(cnr="C-2", state="AP")], tmp_path, run_date="2026-07-09")
    assert not (tmp_path / "2026" / "TG.json").exists()
    assert (tmp_path / "2026" / "AP.json").exists()


def test_id_reused_when_cnr_discovered_later(tmp_path: Path) -> None:
    # Run 1: media-only record, keyed on FIR.
    write_shards(
        [_record(fir_ref={"station": "X PS", "number": "9/2026"})], tmp_path, run_date="2026-07-09"
    )
    first = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]["id"]
    # Run 2: the same case now also carries a CNR -> must reuse the FIR-era id.
    result = write_shards(
        [_record(fir_ref={"station": "X PS", "number": "9/2026"}, cnr="TSHC01-000009-2026")],
        tmp_path,
        run_date="2026-07-10",
    )
    second = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]["id"]
    assert first == second and result.updated == 1 and result.new == 0


def test_distinct_courts_get_distinct_ids(tmp_path: Path) -> None:
    r1 = _record(court={"name": "Court A", "next_hearing": None})
    r2 = _record(court={"name": "Court B", "next_hearing": None})
    write_shards([r1, r2], tmp_path, run_date="2026-07-09")
    ids = {r["id"] for r in json.loads((tmp_path / "2026" / "TG.json").read_text())}
    assert len(ids) == 2  # anon key includes court -> no collision


def test_duplicate_explicit_ids_raise(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate ids"):
        write_shards(
            [
                _record(cnr="C-1", id="SKS-2026-TG-000001"),
                _record(cnr="C-2", id="SKS-2026-TG-000001"),
            ],
            tmp_path,
            run_date="2026-07-09",
        )


def test_read_existing_raises_on_corrupt_shard(tmp_path: Path) -> None:
    write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")
    (tmp_path / "2026" / "TG.json").write_text("{corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read existing shard"):
        write_shards([_record(cnr="C-2")], tmp_path, run_date="2026-07-09")
