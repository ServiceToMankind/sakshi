"""Tests for the month-to-date Gemini spend ledger (pipeline.spend)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline import spend


def test_month_to_date_absent_is_zero(tmp_path: Path) -> None:
    assert spend.month_to_date(tmp_path, "2026-07-31") == 0.0


def test_record_accumulates_within_a_month(tmp_path: Path) -> None:
    assert spend.record_spend(tmp_path, "2026-07-05", 0.10) == 0.10
    assert spend.record_spend(tmp_path, "2026-07-20", 0.05) == 0.15
    assert spend.month_to_date(tmp_path, "2026-07-31") == 0.15


def test_months_are_independent_buckets(tmp_path: Path) -> None:
    spend.record_spend(tmp_path, "2026-07-31", 9.99)
    # A new calendar month starts fresh — the cap resets.
    assert spend.month_to_date(tmp_path, "2026-08-01") == 0.0
    spend.record_spend(tmp_path, "2026-08-01", 0.02)
    assert spend.month_to_date(tmp_path, "2026-08-15") == 0.02
    assert spend.month_to_date(tmp_path, "2026-07-15") == 9.99


def test_negative_delta_is_a_noop_add(tmp_path: Path) -> None:
    spend.record_spend(tmp_path, "2026-07-10", 0.20)
    assert spend.record_spend(tmp_path, "2026-07-11", -5.0) == 0.20


def test_ledger_persists_in_meta_and_is_aggregate_only(tmp_path: Path) -> None:
    spend.record_spend(tmp_path, "2026-07-10", 0.20)
    path = tmp_path / "_meta" / "spend.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Only month keys and float totals — no case content can live here.
    assert set(payload) == {"months"}
    assert payload["months"] == {"2026-07": 0.2}


def test_corrupt_ledger_reads_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "_meta" / "spend.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")
    assert spend.load_spend(tmp_path) == {}
    assert spend.month_to_date(tmp_path, "2026-07-01") == 0.0
