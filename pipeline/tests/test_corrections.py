"""Tests for human-authored corrections / quarantine (pipeline/corrections.py)."""

from __future__ import annotations

from pathlib import Path

from pipeline import corrections


def test_load_and_quarantined_ids(tmp_path: Path) -> None:
    (tmp_path / "A.yml").write_text("record_id: SKS-1\nquarantine: true\nreason: over-merge\n")
    (tmp_path / "B.yml").write_text("record_id: SKS-2\nquarantine: false\n")  # not quarantined
    (tmp_path / "C.yml").write_text("note: no record_id here\n")  # ignored
    (tmp_path / "junk.yml").write_text("::: not yaml :::\n{\n")  # unparseable -> skipped
    loaded = corrections.load_corrections(tmp_path)
    assert set(loaded) == {"SKS-1", "SKS-2"}
    assert corrections.quarantined_ids(loaded) == {"SKS-1"}


def test_missing_directory_is_empty(tmp_path: Path) -> None:
    assert corrections.load_corrections(tmp_path / "nope") == {}


def test_repo_corrections_quarantine_dl_000003() -> None:
    """The committed correction for the over-merged DL-000003 marks it quarantined."""
    loaded = corrections.load_corrections()
    assert "SKS-2026-DL-000003" in corrections.quarantined_ids(loaded)
