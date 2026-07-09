"""Synthetic tests for schema validation and the summary-size gate.

Fixtures are obviously synthetic (district "TESTVILLE"). These exercise the
``python -m pipeline.validate --all`` gate that CI runs over the published tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import ValidationError

from pipeline import validate
from pipeline.shard import SUMMARY_MAX_BYTES


def _valid_record() -> dict[str, Any]:
    return {
        "id": "SKS-2026-TG-000001",
        "state": "TG",
        "district": "TESTVILLE",
        "category": "sexual_assault",
        "status": "UNDER_TRIAL",
        "minor_involved": False,
        "sources": [
            {"url": "https://example.invalid/x", "publisher": "eCourts", "retrieved": "2026-07-09"}
        ],
        "confidence": 0.9,
        "last_verified": "2026-07-09",
    }


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# --- validate_record ---------------------------------------------------------


def test_validate_record_accepts_valid_and_rejects_invalid() -> None:
    schema = validate.load_schema()
    validate.validate_record(_valid_record(), schema)  # does not raise

    bad = _valid_record()
    bad["id"] = "not-an-sks-id"
    with pytest.raises(ValidationError):
        validate.validate_record(bad, schema)


# --- iter_shard_files --------------------------------------------------------


def test_iter_shard_files_skips_top_level_and_review(tmp_path: Path) -> None:
    _write(tmp_path / "2026" / "TG.json", [_valid_record()])
    _write(tmp_path / "summary.json", {})  # top-level: not a shard
    _write(tmp_path / "_review" / "queue.json", [{}])  # quarantine: excluded

    shards = list(validate.iter_shard_files(tmp_path))
    assert shards == [tmp_path / "2026" / "TG.json"]


# --- validate_all_shards -----------------------------------------------------


def test_validate_all_shards_reports_each_problem(tmp_path: Path) -> None:
    _write(tmp_path / "2026" / "TG.json", [_valid_record()])  # clean
    _write(tmp_path / "2026" / "AP.json", [{"id": "bad", "state": "AP"}])  # schema-invalid
    _write(tmp_path / "2026" / "MH.json", {"not": "a list"})  # wrong top-level type
    broken = tmp_path / "2026" / "KA.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{not json", encoding="utf-8")  # unparseable

    errors = validate.validate_all_shards(tmp_path)
    joined = "\n".join(errors)
    assert "AP.json" in joined
    assert "expected a JSON array" in joined
    assert "could not read/parse JSON" in joined
    assert "TG.json" not in joined  # the clean shard produced no error


def test_validate_all_shards_clean_tree_has_no_errors(tmp_path: Path) -> None:
    _write(tmp_path / "2026" / "TG.json", [_valid_record()])
    assert validate.validate_all_shards(tmp_path) == []


# --- check_summary_size ------------------------------------------------------


def test_check_summary_size_missing_within_and_over_budget(tmp_path: Path) -> None:
    missing = tmp_path / "summary.json"
    assert validate.check_summary_size(missing) is None

    missing.write_text("{}", encoding="utf-8")
    assert validate.check_summary_size(missing) is None

    big = tmp_path / "big.json"
    big.write_text(" " * (SUMMARY_MAX_BYTES + 1), encoding="utf-8")
    assert validate.check_summary_size(big) is not None


# --- main --------------------------------------------------------------------


def test_main_clean_tree_returns_zero(tmp_path: Path) -> None:
    _write(tmp_path / "2026" / "TG.json", [_valid_record()])
    _write(tmp_path / "summary.json", {"total": 0})
    assert validate.main(["--all", "--data-dir", str(tmp_path)]) == 0


def test_main_reports_failures_returns_one(tmp_path: Path) -> None:
    _write(tmp_path / "2026" / "AP.json", [{"id": "bad"}])
    _write(tmp_path / "summary.json", " " * (SUMMARY_MAX_BYTES + 1))
    assert validate.main(["--all", "--data-dir", str(tmp_path)]) == 1


def test_project_to_schema_drops_unknown_keys() -> None:
    schema = validate.load_schema()
    dirty = {
        "state": "TG",
        "district": "TESTVILLE",
        "reporter": "Ms A, the survivor's mother, 4th Cross Rd",  # unknown -> must be dropped
        "sources": [
            {"url": "u", "publisher": "eCourts", "retrieved": "2026-07-09", "leak": "x"},
        ],
    }
    clean = validate.project_to_schema(dirty, schema)
    assert "reporter" not in clean
    assert "leak" not in clean["sources"][0]  # nested unknown key dropped too
    assert clean["state"] == "TG" and clean["district"] == "TESTVILLE"
