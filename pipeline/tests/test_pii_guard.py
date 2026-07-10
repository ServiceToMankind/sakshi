"""Synthetic tests for the ship-time PII guard (``scripts/pii_guard.py``).

The guard is a legally mandated Phase 0 safety gate held to 100% BRANCH coverage
in ``make check``. All fixtures are obviously synthetic (district "TESTVILLE",
fake Aadhaar/email).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import pii_guard


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- scan_value / scan_json_file ---------------------------------------------


def test_scan_value_flags_forbidden_key_and_pii_value() -> None:
    """A forbidden key name and a PII-shaped string value are both reported."""
    data = {
        "district": "TESTVILLE",
        "victim_name": "SHOULD NOT PERSIST",
        "note": "reach test@testville.example",
        "pending_days": 25,  # non-string scalar: walked but never flagged
        "accused": [{"label": "Accused #1"}],
    }
    reasons = [f.reason for f in pii_guard.scan_value(data, "")]
    assert any("forbidden field name 'victim_name'" in r for r in reasons)
    assert any("email pattern" in r for r in reasons)


def test_scan_value_flags_age_in_summary_when_enabled() -> None:
    """With age scanning on, a concrete age in the free-text summary is reported."""
    data = {"summary": "Police rescued a 17-year-old.", "district": "TESTVILLE"}
    reasons = [f.reason for f in pii_guard.scan_value(data, "", scan_ages=True)]
    assert any("age-expression pattern" in r for r in reasons)


def test_scan_value_age_scan_ignores_non_free_text_fields() -> None:
    """An age-shaped slug in a URL (not a free-text field) is NOT flagged."""
    data = {
        "summary": "A neutral summary before the Special POCSO Court, TESTVILLE.",
        "sources": [{"url": "https://example.invalid/a-17-year-old-case"}],
    }
    reasons = [f.reason for f in pii_guard.scan_value(data, "", scan_ages=True)]
    assert not any("age-expression" in r for r in reasons)


def test_scan_value_no_age_findings_when_disabled() -> None:
    """With age scanning off, even an age in the summary is not flagged."""
    data = {"summary": "Police rescued a 17-year-old."}
    reasons = [f.reason for f in pii_guard.scan_value(data, "", scan_ages=False)]
    assert not any("age-expression" in r for r in reasons)


def test_scans_ages_public_shard_yes_review_no() -> None:
    """Published shards are age-scanned; the _review quarantine is not."""
    assert pii_guard._scans_ages(Path("data/2026/TG.json")) is True
    assert pii_guard._scans_ages(Path("data/_review/review-2026-07-10.json")) is False


def test_scan_json_file_age_in_public_shard_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "2026").mkdir()
    shard = _write_json(
        tmp_path / "2026" / "TG.json",
        [{"summary": "Police rescued a 17-year-old.", "district": "TESTVILLE"}],
    )
    findings = pii_guard.scan_json_file(shard)
    assert any("age-expression" in f.reason for f in findings)


def test_scan_json_file_age_in_review_is_not_flagged(tmp_path: Path) -> None:
    """The quarantine may hold an age-flagged non-minor record pending confirmation."""
    (tmp_path / "_review").mkdir()
    quarantined = _write_json(
        tmp_path / "_review" / "review-x.json",
        [{"summary": "Police rescued a 17-year-old."}],
    )
    findings = pii_guard.scan_json_file(quarantined)
    assert not any("age-expression" in f.reason for f in findings)


def test_scan_json_file_clean_and_parse_error(tmp_path: Path) -> None:
    """A clean file yields no findings; unparseable JSON yields a read/parse finding."""
    clean = _write_json(tmp_path / "clean.json", {"district": "TESTVILLE"})
    assert pii_guard.scan_json_file(clean) == []

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    findings = pii_guard.scan_json_file(broken)
    assert len(findings) == 1
    assert "could not read/parse JSON" in findings[0].reason


def test_finding_str_is_human_readable() -> None:
    """Finding renders as '<location>: <path>: <reason>'."""
    finding = pii_guard.Finding("file.json", "root.victim_name", "forbidden field name")
    assert str(finding) == "file.json: root.victim_name: forbidden field name"


# --- scan_diff_text ----------------------------------------------------------


def test_scan_diff_text_only_flags_added_content_lines() -> None:
    """Added lines with PII are flagged; headers and context/removed lines are ignored."""
    diff = "\n".join(
        [
            "+++ b/data/2026/TG.json",
            "--- a/data/2026/TG.json",
            " context line with test@testville.example",  # context: ignored
            "-removed test@testville.example",  # removed: ignored
            "+added clean line",  # added, clean
            "+contact test@testville.example",  # added, PII
        ]
    )
    findings = pii_guard.scan_diff_text(diff)
    assert len(findings) == 1
    assert "email pattern" in findings[0].reason


def test_staged_diff_runs_git_without_raising() -> None:
    """_staged_diff shells out to git and returns text (empty is fine outside a repo)."""
    assert isinstance(pii_guard._staged_diff(), str)


# --- iter_json_files ---------------------------------------------------------


def test_iter_json_files_walks_dirs_and_files(tmp_path: Path) -> None:
    """Directories are walked recursively; explicit .json files are yielded."""
    nested = tmp_path / "2026"
    nested.mkdir()
    _write_json(nested / "TG.json", [])
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    direct = _write_json(tmp_path / "summary.json", {})

    from_dir = list(pii_guard.iter_json_files([tmp_path]))
    assert nested / "TG.json" in from_dir
    assert tmp_path / "summary.json" in from_dir
    assert all(p.suffix == ".json" for p in from_dir)

    from_file = list(pii_guard.iter_json_files([direct]))
    assert from_file == [direct]

    # A non-JSON path passed directly is skipped.
    assert list(pii_guard.iter_json_files([tmp_path / "notes.txt"])) == []


# --- main --------------------------------------------------------------------


def test_main_clean_directory_returns_zero(tmp_path: Path) -> None:
    _write_json(tmp_path / "ok.json", {"district": "TESTVILLE"})
    assert pii_guard.main([str(tmp_path)]) == 0


def test_main_dirty_file_returns_one(tmp_path: Path) -> None:
    _write_json(tmp_path / "bad.json", {"victim_name": "SHOULD NOT PERSIST"})
    assert pii_guard.main([str(tmp_path)]) == 1


def test_main_diff_mode_uses_staged_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    """--diff scans the staged diff; a PII add fails, a clean add passes."""
    monkeypatch.setattr(pii_guard, "_staged_diff", lambda: "+contact test@testville.example")
    assert pii_guard.main(["--diff"]) == 1

    monkeypatch.setattr(pii_guard, "_staged_diff", lambda: "+all clean here")
    assert pii_guard.main(["--diff"]) == 0


def test_main_diff_with_explicit_paths_scans_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When both --diff and paths are given, files are scanned in addition to the diff."""
    monkeypatch.setattr(pii_guard, "_staged_diff", lambda: "+clean")
    _write_json(tmp_path / "bad.json", {"victim_name": "SHOULD NOT PERSIST"})
    assert pii_guard.main(["--diff", str(tmp_path)]) == 1
