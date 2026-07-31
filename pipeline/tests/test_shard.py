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
        "title": "Sexual assault case — TESTVILLE (2026)",
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
    assert result.published == 1 and result.new == 1 and result.material == 0

    records = json.loads((tmp_path / "2026" / "TG.json").read_text())
    assert records[0]["id"] == "SKS-2026-TG-000001"
    assert records[0]["first_published"] == "2026-07-09"
    assert "last_status_change" not in records[0]  # brand-new: no change observed yet
    assert "last_verified" not in records[0]  # removed from the model (§1)
    assert records[0]["days_since_reported"] == 25

    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "summary.json").stat().st_size < SUMMARY_MAX_BYTES
    index = json.loads((tmp_path / "index.json").read_text())
    assert index["shards"][0]["path"] == "2026/TG.json"
    assert index["shards"][0]["records"] == 1


def test_summary_accountability_severity_and_jurisdictions(tmp_path: Path) -> None:
    """severity_counts + jurisdiction scorecards are charge/aggregate-derived only."""
    recs = [
        _record(cnr="C-1", offence_sections=["BNS 70(2)"], status="UNDER_TRIAL"),
        _record(cnr="C-2", offence_sections=["IPC 376"], status="CONVICTED", district="OTHERVILLE"),
        _record(cnr="C-3", offence_sections=["IPC 354"], status="ACQUITTED"),
    ]
    write_shards(recs, tmp_path, run_date="2026-07-09")
    summary = json.loads((tmp_path / "summary.json").read_text())

    assert summary["severity_counts"]["Gang rape of a minor"] == 1
    assert summary["severity_counts"]["Rape"] == 1
    assert summary["aggravated_total"] == 1  # only the BNS 70(2) case is aggravated

    juris = {(j["state"], j["district"]): j for j in summary["jurisdictions"]}
    testville = juris[("TG", "TESTVILLE")]  # C-1 (under trial) + C-3 (acquitted)
    assert testville["total"] == 2
    assert testville["under_trial"] == 1 and testville["acquittals"] == 1
    # Non-minor active case C-1 has days_since_reported=25; C-3 is acquitted (not active).
    assert testville["median_pending_days"] == 25
    assert testville["longest_pending"] == {"id": "SKS-2026-TG-000001", "days": 25}
    other = juris[("TG", "OTHERVILLE")]  # C-2 convicted (not active -> no pendency)
    assert other["convictions"] == 1 and other["median_pending_days"] is None


def test_summary_minor_jurisdiction_has_no_day_precise_pendency(tmp_path: Path) -> None:
    """A minor (year-only date, no days_since_reported) never contributes day-precise pendency."""
    minor = _record(
        cnr="C-M",
        minor_involved=True,
        incident_reported_date="2026",
        status="UNDER_TRIAL",
        title="Sexual assault case involving a minor — TESTVILLE (2026)",
        summary=(
            "The case is under trial in TESTVILLE, TG. Reported 2026. "
            "Identifying details are withheld by law (POCSO s.23)."
        ),
    )
    write_shards([minor], tmp_path, run_date="2026-07-09")
    juris = json.loads((tmp_path / "summary.json").read_text())["jurisdictions"][0]
    assert juris["median_pending_days"] is None and juris["longest_pending"] is None


def test_pendency_requires_a_court_anchor(tmp_path: Path) -> None:
    """§ pendency honesty: a non-minor, active, day-precise record with NO court anchor
    (media-only) carries days_since_reported but is EXCLUDED from the pendency leaderboard and
    the jurisdiction median — a 'still pending' claim needs a re-checkable anchor."""
    media_only = _record(status="UNDER_TRIAL", incident_reported_date="2026-06-14")  # no cnr/fir
    media_only.pop("cnr", None)
    write_shards([media_only], tmp_path, run_date="2026-07-09")
    rec = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert rec["days_since_reported"] == 25  # elapsed time IS stored...
    assert summary["top_longest_pending"] == []  # ...but never a pendency claim
    assert summary["jurisdictions"][0]["median_pending_days"] is None

    # The SAME record WITH a CNR is trackable, so pendency returns (fresh tree).
    fresh = tmp_path / "anchored"
    anchored = _record(cnr="CNR-1", status="UNDER_TRIAL", incident_reported_date="2026-06-14")
    write_shards([anchored], fresh, run_date="2026-07-09")
    summary2 = json.loads((fresh / "summary.json").read_text())
    assert [p["id"] for p in summary2["top_longest_pending"]] == ["SKS-2026-TG-000001"]
    assert summary2["jurisdictions"][0]["median_pending_days"] == 25


def test_summary_jurisdictions_are_capped_and_trim_by_status(tmp_path: Path) -> None:
    """jurisdictions is the only unbounded summary section — cap it (worst-first) so
    summary.json can never overflow SUMMARY_MAX_BYTES and abort the run, and drop the
    unused by_status dict to keep cards lean."""
    recs = [
        _record(cnr=f"C-{i}", district=f"DISTRICT-{i:03d}", offence_sections=["IPC 376"])
        for i in range(200)
    ]
    write_shards(recs, tmp_path, run_date="2026-07-09")
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert len(summary["jurisdictions"]) == 120  # _MAX_JURISDICTIONS
    assert "by_status" not in summary["jurisdictions"][0]  # trimmed
    assert (tmp_path / "summary.json").stat().st_size < SUMMARY_MAX_BYTES


def test_summary_scale_accumulates_ingestion_across_runs(tmp_path: Path) -> None:
    """The daily scale histogram counts NEWLY-minted records per run, accumulated."""
    write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")
    write_shards([_record(cnr="C-1"), _record(cnr="C-2")], tmp_path, run_date="2026-07-10")
    scale = json.loads((tmp_path / "summary.json").read_text())["scale"]
    daily = {d["date"]: d["count"] for d in scale["daily"]}
    assert daily["2026-07-09"] == 1  # 1 new on day 1
    assert daily["2026-07-10"] == 1  # only C-2 is new on day 2 (C-1 already existed)
    assert scale["cumulative_total"] == 2 and scale["this_week"] == 2


def test_ids_are_stable_across_runs(tmp_path: Path) -> None:
    write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")
    # A fresh record (no id) for the SAME case reuses the existing id. Its content is
    # identical, so this is a RECHECK (no material change), never a material update (§1).
    result = write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-10")
    records = json.loads((tmp_path / "2026" / "TG.json").read_text())
    assert records[0]["id"] == "SKS-2026-TG-000001"
    assert result.new == 0 and result.material == 0 and result.rechecked == 1
    # first_published stays frozen at the day-1 date; no last_status_change was ever set.
    assert records[0]["first_published"] == "2026-07-09"
    assert "last_status_change" not in records[0]


def test_material_change_bumps_last_status_change_only(tmp_path: Path) -> None:
    """A real status change bumps last_status_change to the run date and counts as
    `material`; first_published stays frozen (§1)."""
    write_shards([_record(cnr="C-1", status="UNDER_TRIAL")], tmp_path, run_date="2026-07-09")
    result = write_shards([_record(cnr="C-1", status="CONVICTED")], tmp_path, run_date="2026-07-20")
    rec = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]
    assert rec["status"] == "CONVICTED"
    assert rec["first_published"] == "2026-07-09"  # immutable
    assert rec["last_status_change"] == "2026-07-20"  # bumped to this run
    assert result.material == 1 and result.rechecked == 0 and result.new == 0

    # A later run that changes nothing material must NOT re-bump last_status_change: it
    # carries the prior 2026-07-20 forward and counts as a recheck.
    convicted = _record(cnr="C-1", status="CONVICTED")
    result2 = write_shards([convicted], tmp_path, run_date="2026-07-25")
    rec2 = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]
    assert rec2["last_status_change"] == "2026-07-20"  # unchanged, not restamped
    assert result2.material == 0 and result2.rechecked == 1


def test_offence_section_reformat_is_not_a_material_change(tmp_path: Path) -> None:
    """§4b: re-expressing the same charges in a different string form ("POCSO Act" vs the
    canonical "POCSO") must NOT bump last_status_change — the material signature compares
    NORMALISED sections."""
    write_shards(
        [_record(cnr="C-1", offence_sections=["POCSO", "IPC 376"])], tmp_path, run_date="2026-07-09"
    )
    result = write_shards(
        [_record(cnr="C-1", offence_sections=["POCSO Act", "Section 376 IPC"])],
        tmp_path,
        run_date="2026-07-20",
    )
    rec = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]
    assert result.material == 0 and result.rechecked == 1
    assert "last_status_change" not in rec


def test_new_source_alone_is_not_a_material_change(tmp_path: Path) -> None:
    """Adding a corroborating source is NOT material — no last_status_change bump (§1)."""
    write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")
    two_sources = _record(
        cnr="C-1",
        sources=[
            {"url": "https://example.invalid/x", "publisher": "eCourts", "retrieved": "2026-07-09"},
            {"url": "https://example.invalid/y", "publisher": "PTI", "retrieved": "2026-07-15"},
        ],
    )
    result = write_shards([two_sources], tmp_path, run_date="2026-07-15")
    rec = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]
    assert len(rec["sources"]) == 2  # the new source is recorded...
    assert "last_status_change" not in rec  # ...but it is not a material change
    assert result.material == 0 and result.rechecked == 1


def test_identical_reprocess_is_byte_identical_except_last_checked(tmp_path: Path) -> None:
    """The §1 guarantee: a record re-processed with identical content on the SAME run
    date is byte-identical to its prior self. The only per-run signal is last_checked,
    which lives in data/_meta/ and is NEVER in the public record."""
    write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")
    shard_bytes_1 = (tmp_path / "2026" / "TG.json").read_bytes()

    write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-09")
    shard_bytes_2 = (tmp_path / "2026" / "TG.json").read_bytes()

    assert shard_bytes_1 == shard_bytes_2  # the public record does not change

    rec = json.loads(shard_bytes_2)[0]
    assert "last_checked" not in rec  # never in the public record
    checked = json.loads((tmp_path / "_meta" / "last_checked.json").read_text())
    assert checked[rec["id"]] == "2026-07-09"  # the internal signal lives only here


def test_migration_derives_first_published_from_earliest_source(tmp_path: Path) -> None:
    """A record already in the tree from BEFORE first_published existed (it still carries
    the retired last_verified) keeps its truest entered-the-tree date — its earliest source
    date — on migration, not today's run date (§1)."""
    # Hand-write a pre-migration shard: last_verified present, first_published absent.
    legacy = _record(
        cnr="C-1",
        id="SKS-2026-TG-000001",
        sources=[
            {"url": "https://example.invalid/x", "publisher": "eCourts", "retrieved": "2026-06-20"},
            {"url": "https://example.invalid/y", "publisher": "PTI", "retrieved": "2026-07-09"},
        ],
    )
    legacy["last_verified"] = "2026-07-25"  # the retired field, restamped daily
    (tmp_path / "2026").mkdir(parents=True)
    (tmp_path / "2026" / "TG.json").write_text(json.dumps([legacy]), encoding="utf-8")

    # Re-run the writer well after those source dates.
    write_shards([_record(cnr="C-1")], tmp_path, run_date="2026-07-29")
    rec = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]
    assert rec["id"] == "SKS-2026-TG-000001"
    assert rec["first_published"] == "2026-06-20"  # earliest source, NOT the 2026-07-29 run
    assert "last_verified" not in rec  # retired field dropped


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
    # Discovering a CNR enriches provenance but is NOT a material change (CNR is not a
    # material field), so this counts as a recheck, not an update (§1).
    assert first == second and result.rechecked == 1 and result.new == 0 and result.material == 0


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
