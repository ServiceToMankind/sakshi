"""Tests for the human-authored corrections mechanism (pipeline.corrections)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from pipeline.corrections import (
    apply_correction,
    load_corrections,
    override_is_allowed,
    quarantined_ids,
)

_CORRECTION_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "correction.schema.json").read_text()
)


def _write(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(body, encoding="utf-8")


def test_load_and_quarantined_ids(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "SKS-2026-DL-000003.yml",
        "record_id: SKS-2026-DL-000003\nquarantine: true\nauthor: op\n"
        "date: '2026-08-01'\nreason: over-merge\n",
    )
    _write(
        tmp_path,
        "SKS-2026-TG-000009.yml",
        "record_id: SKS-2026-TG-000009\noverrides:\n  district: Warangal\n"
        "author: op\ndate: '2026-08-01'\nreason: wrong district\n",
    )
    corrections = load_corrections(tmp_path)
    assert set(corrections) == {"SKS-2026-DL-000003", "SKS-2026-TG-000009"}
    assert quarantined_ids(corrections) == {"SKS-2026-DL-000003"}


def test_load_empty_and_corrupt(tmp_path: Path) -> None:
    assert load_corrections(tmp_path / "absent") == {}
    _write(tmp_path, "bad.yml", "{ not: valid: yaml:")
    _write(tmp_path, "no_id.yml", "quarantine: true\n")  # missing record_id -> skipped
    assert load_corrections(tmp_path) == {}


def test_override_is_allowed_blocks_forbidden_and_identity_fields() -> None:
    assert override_is_allowed("district") is True
    assert override_is_allowed("status") is True
    # identity / projection anchors
    assert override_is_allowed("id") is False
    assert override_is_allowed("minor_involved") is False
    # forbidden PII field names + substrings
    assert override_is_allowed("victim_name") is False
    assert override_is_allowed("address") is False
    assert override_is_allowed("survivor") is False


def test_apply_correction_applies_overrides_and_marks_corrected() -> None:
    corrections = {
        "SKS-2026-TG-000009": {
            "record_id": "SKS-2026-TG-000009",
            "overrides": {"district": "Warangal", "status": "CHARGESHEETED"},
        }
    }
    record = {"id": "SKS-2026-TG-000009", "district": "Warngl", "status": "FIR_FILED"}
    fixed = apply_correction(record, corrections)
    assert fixed["district"] == "Warangal"
    assert fixed["status"] == "CHARGESHEETED"
    assert fixed["corrected"] is True
    assert record.get("corrected") is None  # original untouched (new dict)


def test_apply_correction_drops_forbidden_override_keys() -> None:
    corrections = {
        "R1": {"record_id": "R1", "overrides": {"district": "Pune", "victim_name": "leak"}}
    }
    fixed = apply_correction({"id": "R1", "district": "X"}, corrections)
    assert fixed["district"] == "Pune"
    assert "victim_name" not in fixed  # forbidden key dropped before it is applied


def test_apply_correction_no_match_or_no_overrides_is_a_noop() -> None:
    record = {"id": "R1", "district": "X"}
    assert apply_correction(record, {}) is record  # no correction at all
    # a quarantine-only correction has no overrides -> record returned unchanged
    assert apply_correction(record, {"R1": {"record_id": "R1", "quarantine": True}}) is record


def test_correction_schema_accepts_valid_and_rejects_malformed() -> None:
    valid = {
        "record_id": "SKS-2026-DL-000003",
        "quarantine": True,
        "author": "operator",
        "date": "2026-08-01",
        "reason": "unresolved over-merge",
        "evidence": ["https://indiankanoon.org/doc/1/"],
    }
    jsonschema.validate(valid, _CORRECTION_SCHEMA)  # does not raise
    for bad in (
        {**valid, "record_id": "not-an-id"},  # id pattern
        {"quarantine": True, "author": "op", "date": "2026-08-01", "reason": "x"},  # no record_id
        {**valid, "unknown_field": 1},  # additionalProperties:false
    ):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, _CORRECTION_SCHEMA)


def test_no_correction_files_apply_nothing() -> None:
    """The committed corrections/ directory carries NO *.yml (only docs), so a normal run
    applies zero corrections — the mechanism ships inert until an operator authors one."""
    repo_corrections = Path(__file__).resolve().parents[2] / "corrections"
    yml = list(repo_corrections.glob("*.yml")) if repo_corrections.exists() else []
    assert yml == [], f"unexpected committed correction(s): {yml}"
