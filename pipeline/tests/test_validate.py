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
from pipeline.sanitize import MINOR_SUMMARY_TEMPLATE
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


# --- minor conditional subschema (issue #7) ----------------------------------


def _minor_projected_record() -> dict[str, Any]:
    """A minor record at the exact granularity sanitize.project_minor_record emits."""
    return {
        "id": "SKS-2026-TG-000001",
        "state": "TG",
        "district": "TESTVILLE",
        "category": "pocso",
        "status": "UNDER_TRIAL",
        "minor_involved": True,
        "incident_reported_date": "2026",
        "pending_days": None,
        "summary": MINOR_SUMMARY_TEMPLATE,
        "court": {"name": "Special POCSO Court, TESTVILLE", "next_hearing": None},
        "status_history": [{"status": "FIR_FILED", "date": "2026-06", "source": 0}],
        "sources": [
            {"url": "https://example.invalid/x", "publisher": "eCourts", "retrieved": "2026-07-09"}
        ],
        "confidence": 0.9,
        "last_verified": "2026-07-09",
    }


def test_projected_minor_record_validates() -> None:
    schema = validate.load_schema()
    validate.validate_record(_minor_projected_record(), schema)  # does not raise


def test_unprojected_minor_record_is_rejected() -> None:
    """A minor record still carrying a full date / integer pending_days / narrative fails."""
    schema = validate.load_schema()
    bad = _minor_projected_record()
    bad["incident_reported_date"] = "2026-07-05"
    bad["pending_days"] = 5
    bad["summary"] = "Police rescued a 17-year-old."
    bad["court"]["next_hearing"] = "2026-08-02"
    with pytest.raises(ValidationError):
        validate.validate_record(bad, schema)


def test_non_minor_requires_full_precision_dates() -> None:
    """The else-branch keeps non-minor cases at full YYYY-MM-DD precision."""
    schema = validate.load_schema()
    rec = _minor_projected_record()
    rec["minor_involved"] = False
    rec["pending_days"] = 5
    rec["summary"] = "A neutral non-graphic summary."
    # A year-only date is invalid for a non-minor case.
    with pytest.raises(ValidationError):
        validate.validate_record(rec, schema)


def test_schema_summary_const_matches_template() -> None:
    """The schema's minor summary const cannot drift from the sanitizer's template."""
    schema = validate.load_schema()
    then = schema["allOf"][0]["then"]["properties"]
    assert then["summary"]["const"] == MINOR_SUMMARY_TEMPLATE


def test_schema_examples_all_validate() -> None:
    schema = validate.load_schema()
    for example in schema.get("examples", []):
        validate.validate_record(example, schema)


def test_has_qualifying_offence_section() -> None:
    """POCSO/BNS-Ch.V/IPC sexual sections qualify; non-sexual and empty do not."""
    assert validate.has_qualifying_offence_section(["BNS 64"])  # rape
    assert validate.has_qualifying_offence_section(["POCSO 6"])
    assert validate.has_qualifying_offence_section(["BNS 78"])  # stalking (Ch. V)
    assert validate.has_qualifying_offence_section(["IPC 302", "IPC 376"])  # any qualifying
    assert not validate.has_qualifying_offence_section(["NI Act 138"])  # cheque bounce
    assert not validate.has_qualifying_offence_section(["IPC 420"])  # cheating
    assert not validate.has_qualifying_offence_section(["BNS 103"])  # murder, not Ch. V sexual
    assert not validate.has_qualifying_offence_section([])


def test_withhold_unsourced_accused_names() -> None:
    """An accused name stands only with court name + a case anchor; else it is withheld."""
    named = {
        "label": "Accused #1",
        "name_public_court_record": "A. Realname",
        "status": "CONVICTED",
    }
    corroborated = {"court": {"name": "Delhi HC"}, "cnr": "C-1", "accused": [dict(named)]}
    kept = validate.withhold_unsourced_accused_names(corroborated)
    assert kept["accused"][0]["name_public_court_record"] == "A. Realname"

    # Court name present but no case anchor -> withheld.
    no_anchor = {"court": {"name": "Delhi HC"}, "accused": [dict(named)]}
    assert (
        validate.withhold_unsourced_accused_names(no_anchor)["accused"][0][
            "name_public_court_record"
        ]
        is None
    )

    # No court context at all (e.g. a media / bare-index record) -> withheld.
    media = {"fir_ref": {}, "accused": [dict(named)]}
    assert (
        validate.withhold_unsourced_accused_names(media)["accused"][0]["name_public_court_record"]
        is None
    )

    # No accused list -> record returned unchanged.
    assert validate.withhold_unsourced_accused_names({"state": "TG"}) == {"state": "TG"}


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
