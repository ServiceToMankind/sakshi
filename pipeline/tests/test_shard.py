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
