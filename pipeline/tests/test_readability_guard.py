"""Tests for the readability CI assertion (scripts/readability_guard.py, §6a)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import readability_guard


def _shard(tmp: Path, records: list[dict[str, Any]]) -> Path:
    (tmp / "2026").mkdir(parents=True, exist_ok=True)
    p = tmp / "2026" / "TG.json"
    p.write_text(json.dumps(records), encoding="utf-8")
    return p


def test_flags_non_minor_legalese(tmp_path: Path) -> None:
    _shard(tmp_path, [{"id": "X", "minor_involved": False, "summary": "The petitioner appealed."}])
    findings = readability_guard.scan_tree([tmp_path])
    assert any("petitioner" in f for f in findings)


def test_minor_summary_is_exempt(tmp_path: Path) -> None:
    _shard(tmp_path, [{"id": "M", "minor_involved": True, "summary": "The petitioner appealed."}])
    assert readability_guard.scan_tree([tmp_path]) == []


def test_clean_non_minor_passes_and_main_exit_codes(tmp_path: Path) -> None:
    _shard(tmp_path, [{"id": "C", "minor_involved": False, "summary": "A man was arrested."}])
    assert readability_guard.scan_tree([tmp_path]) == []
    assert readability_guard.main([str(tmp_path)]) == 0

    _shard(tmp_path, [{"id": "B", "minor_involved": False, "summary": "Booked u/s 376."}])
    assert readability_guard.main([str(tmp_path)]) == 1
