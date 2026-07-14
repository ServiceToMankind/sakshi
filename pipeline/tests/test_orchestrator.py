"""End-to-end tests for the pipeline orchestrator (offline)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from pipeline import __main__ as orchestrator
from pipeline.extract.gemini import ExtractionResponse
from pipeline.fixtures import fixture_raw_documents
from pipeline.sources.base import RawDocument


class _FakeGemini:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def generate(self, prompt: str) -> ExtractionResponse:
        return ExtractionResponse(text=self._payload, input_tokens=100, output_tokens=50)


@pytest.fixture(autouse=True)
def _default_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real runs are ALWAYS explicitly scoped (the hard scope gate refuses otherwise).

    Default every orchestrator test to all-states, no window so the gate passes and
    date-less payloads stay in scope; scope-specific tests override LAUNCH_STATES /
    LAUNCH_LOOKBACK_DAYS via their own monkeypatch, which wins.
    """
    monkeypatch.setenv("LAUNCH_STATES", "ALL")


def test_dry_run_end_to_end(tmp_path: Path) -> None:
    out = io.StringIO()
    report = orchestrator.run(
        dry_run=True,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=out,
    )
    assert report.published == 1 and report.new == 1 and report.review == 0
    assert report.needs_review == 0  # the fixture case is auto-eligible (non-minor)

    text = out.getvalue()
    assert "ONE RECORD'S JOURNEY" in text
    assert "DRY-RUN RESULT" in text

    records = json.loads((tmp_path / "2026" / "TG.json").read_text())
    assert records[0]["id"] == "SKS-2026-TG-000001"
    assert len(records[0]["sources"]) == 2  # court + media unioned
    assert "victim" not in records[0]

    env = (tmp_path / "logs" / "run_summary.env").read_text()
    assert "NEW=1" in env and "REVIEW=0" in env
    # Heartbeat fields present for the ops-log comment.
    for key in ("FETCHED=", "PROCESSED=", "SKIPPED=", "EXTRACTED=", "COST="):
        assert key in env


def test_real_branch_with_injected_client_merges_sources(tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "cnr": "C-1",
            "fir_ref": {"station": "TESTVILLE PS", "number": "12/2026"},
            "incident_reported_date": "2026-06-14",
            "offence_sections": ["BNS 64"],
            "minor_involved": False,
            "in_scope": True,
            "confidence": 0.94,
        }
    )
    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=fixture_raw_documents(),
        extract_client=_FakeGemini(payload),
    )
    assert report.published == 1
    records = json.loads((tmp_path / "2026" / "TG.json").read_text())
    assert len(records[0]["sources"]) == 2  # both fixture docs cited


def test_main_dry_run_returns_zero(capsys: object) -> None:
    assert orchestrator.main(["--dry-run", "--run-date", "2026-07-09"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Dry-run wrote to:" in captured.out


def test_low_confidence_routes_to_sanitized_review(tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.4,
        }
    )
    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=fixture_raw_documents(),
        extract_client=_FakeGemini(payload),
    )
    assert report.published == 0 and report.review >= 1

    review_files = list((tmp_path / "_review").glob("review-*.json"))
    assert review_files
    entries = json.loads(review_files[0].read_text())
    assert entries[0]["reason"] == "low_confidence"
    assert "victim" not in entries[0]["record"]  # review records are sanitized too


def test_review_records_are_projected_to_schema(tmp_path: Path) -> None:
    # A model-emitted key that is neither forbidden nor value-PII must still be
    # dropped by the schema allow-list before it can reach the review queue.
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "cnr": "C-1",
            "confidence": 0.4,
            "in_scope": True,
            "reporter": "Ms A, the survivor's mother, 4th Cross Rd",
        }
    )
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=fixture_raw_documents(),
        extract_client=_FakeGemini(payload),
    )
    entries = json.loads(next((tmp_path / "_review").glob("review-*.json")).read_text())
    assert "reporter" not in entries[0]["record"]


def test_assert_no_pii_blocks_planted_leak(tmp_path: Path) -> None:
    (tmp_path / "2026").mkdir(parents=True)
    (tmp_path / "2026" / "TG.json").write_text(
        json.dumps([{"victim_name": "SHOULD NOT PERSIST"}]), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="pii_guard blocked"):
        orchestrator._assert_no_pii(tmp_path)


def test_existing_records_preserved_across_runs(tmp_path: Path) -> None:
    def _doc(slug: str) -> list[RawDocument]:
        # Distinct URLs so the processed-document ledger does not skip run 2's doc.
        return [
            RawDocument(
                url=f"https://example.invalid/{slug}",
                publisher="eCourts",
                fetched_at="2026-07-09",
                text="A TESTVILLE case.",
            )
        ]

    def _payload(cnr: str) -> str:
        return json.dumps(
            {
                "category": "rape",
                "state": "TG",
                "district": "TESTVILLE",
                "status": "FIR_FILED",
                "minor_involved": False,
                "cnr": cnr,
                "in_scope": True,
                "confidence": 0.9,
            }
        )

    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=_doc("a"),
        extract_client=_FakeGemini(_payload("CASE-A")),
    )
    # A second run that fetches only CASE-B must NOT wipe CASE-A from the tree.
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=_doc("b"),
        extract_client=_FakeGemini(_payload("CASE-B")),
    )
    cnrs = {r["cnr"] for r in json.loads((tmp_path / "2026" / "TG.json").read_text())}
    assert cnrs == {"CASE-A", "CASE-B"}


def test_ledger_skips_settled_documents_across_runs(tmp_path: Path) -> None:
    """A document settled in run 1 is not re-extracted in run 2 (budget goes to the tail)."""
    doc = [
        RawDocument(
            url="https://example.invalid/settled",
            publisher="eCourts",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "minor_involved": False,
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.9,
        }
    )
    logs = tmp_path / "logs"
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert (tmp_path / "_meta" / "processed.json").exists()

    # Run 2: same doc, and the record from run 1 is on "main" (this data_dir). A
    # poisoned client raises if called; confirm_published promotes the staged_pending
    # entry to published (it is on disk), so the doc is skipped and never re-extracted.
    class _Poison:
        def generate(self, prompt: str) -> ExtractionResponse:
            raise AssertionError("record confirmed on main must not be re-extracted")

    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=doc,
        extract_client=_Poison(),
    )
    assert report.published == 1  # CASE-1 preserved from run 1, not re-extracted


def test_staged_record_resurfaces_until_merged_to_main(tmp_path: Path) -> None:
    """The exact 4-day scenario: a staged record NOT merged to main is never lost.

    Each run re-extracts and re-stages it (staged_pending), instead of settling it
    "published" and skipping it (which force-pushed the only copy away before).
    """
    doc = [
        RawDocument(
            url="https://example.invalid/staged",
            publisher="The Hindu",
            fetched_at="2026-07-09",
            text="A DL case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "rape",
            "state": "DL",
            "district": "Delhi",
            "status": "UNDER_TRIAL",
            "minor_involved": False,
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.9,
        }
    )
    logs = tmp_path / "logs"
    for day in range(3):  # 3 consecutive runs, the record never reaches main
        shard = tmp_path / "2026" / "DL.json"
        if shard.exists():
            shard.unlink()  # simulate: staging PR not merged, so main lacks the record
        report = orchestrator.run(
            dry_run=False,
            data_dir=tmp_path,
            logs_dir=logs,
            run_date=f"2026-07-1{day}",
            out=io.StringIO(),
            docs=doc,
            extract_client=_FakeGemini(payload),
        )
        assert report.published == 1  # re-extracted + re-staged every run — never lost
        assert report.skipped_settled == 0  # staged_pending is never skipped


def test_staged_record_survives_aging_past_lookback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staged-but-unmerged record that ages past the rolling lookback is NOT dropped."""
    monkeypatch.setenv("LAUNCH_LOOKBACK_DAYS", "7")
    doc = [
        RawDocument(
            url="https://example.invalid/aging",
            publisher="The Hindu",
            fetched_at="2026-07-05",
            text="A DL case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "rape",
            "state": "DL",
            "district": "Delhi",
            "status": "UNDER_TRIAL",
            "minor_involved": False,
            "cnr": "C-1",
            "incident_reported_date": "2026-07-05",
            "in_scope": True,
            "confidence": 0.9,
        }
    )
    logs = tmp_path / "logs"
    r1 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r1.published == 1  # 5 days old <= 7: in window, staged
    # Not merged (clear the shard) and now 8 days old > 7: without the staged bypass
    # _in_scope would drop it and the force-push would lose its only copy.
    (tmp_path / "2026" / "DL.json").unlink()
    r2 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-13",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r2.published == 1  # aged out of the window but the staged bypass kept it


def test_staged_carryover_persists_without_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staged record persists even if its source rolls off the feed (no re-fetch)."""
    doc = [
        RawDocument(
            url="https://example.invalid/carry",
            publisher="The Hindu",
            fetched_at="2026-07-09",
            text="A DL case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "rape",
            "state": "DL",
            "district": "Delhi",
            "status": "UNDER_TRIAL",
            "minor_involved": False,
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.9,
        }
    )
    logs = tmp_path / "logs"
    r1 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r1.published == 1
    # The workflow archives the staging shards to STAGED_DIR; then main lacks the
    # record (not merged) and the source doc has rolled off the feed (no docs fetched).
    staged = tmp_path / "staged" / "2026"
    staged.mkdir(parents=True)
    (staged / "DL.json").write_text((tmp_path / "2026" / "DL.json").read_text())
    (tmp_path / "2026" / "DL.json").unlink()
    monkeypatch.setenv("STAGED_DIR", str(tmp_path / "staged"))
    r2 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=[],
        extract_client=_FakeGemini(payload),
    )
    assert r2.published == 1  # carried over from the staging branch, never re-fetched


def test_merged_record_in_both_main_and_carryover_is_not_double_fed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once a staged record reaches main it must resolve to ONE record, not double-fed.

    The staging branch is a superset of main (main + staged), so after a merge the
    same record lives on BOTH main and in the carryover archive. It must be folded in
    exactly once (carryover copies already on main are dropped by id) — never a second
    copy that inflates the tree or spams the review queue.
    """
    doc = [
        RawDocument(
            url="https://example.invalid/merged",
            publisher="The Hindu",
            fetched_at="2026-07-09",
            text="A DL case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "rape",
            "state": "DL",
            "district": "Delhi",
            "status": "UNDER_TRIAL",
            "minor_involved": False,
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.9,
        }
    )
    logs = tmp_path / "logs"
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    # Simulate the merge: the record is now on main (data_dir keeps it) AND the staging
    # archive (carryover) still holds its own copy from before the merge.
    staged = tmp_path / "staged" / "2026"
    staged.mkdir(parents=True)
    (staged / "DL.json").write_text((tmp_path / "2026" / "DL.json").read_text())
    monkeypatch.setenv("STAGED_DIR", str(tmp_path / "staged"))
    r2 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r2.published == 1 and r2.review == 0
    records = json.loads((tmp_path / "2026" / "DL.json").read_text())
    assert len(records) == 1  # no duplicate shard entry from the double feed


def test_pii_url_review_doc_resurfaces_not_settled(tmp_path: Path) -> None:
    """A low-confidence doc with a PII-shaped URL must re-surface, never settle+vanish.

    The doc url embeds a 10-digit run (Indian-mobile shape) so its STORED record url is
    sanitised to '[redacted]'. The ledger keys on the RAW url (injective) but classifies
    membership in the SANITISED url space — so this review doc is recognised as quarantined
    (NOT mis-settled to out_of_window) and re-surfaces until a human resolves it. The
    carryover restores year shards only, never _review, so a mis-settle here is true loss.
    """
    doc = [
        RawDocument(
            url="https://indiankanoon.org/doc/9876543210/",  # 10-digit run -> sanitised
            publisher="The Example Herald",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "minor_involved": False,
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.5,  # below the review threshold -> quarantined, NOT settled
        }
    )
    logs = tmp_path / "logs"
    r1 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r1.published == 0 and r1.review >= 1
    r2 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r2.skipped_settled == 0  # NOT settled out_of_window despite the PII-shaped url
    assert r2.review >= 1  # re-surfaced for human review


def test_staged_enrichment_of_on_main_case_survives_source_rolloff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staged status-progression to an on-main case is NOT lost if its source rolls off.

    Merging carryover into main by id (not dropping it) preserves the enrichment (further
    status + extra source) staged but not yet merged, even when the source doc is gone.
    """
    d1 = [
        RawDocument(
            url="https://example.invalid/d1",
            publisher="The Hindu",
            fetched_at="2026-07-08",
            text="A DL case.",
        )
    ]
    p1 = json.dumps(
        {
            "category": "rape",
            "state": "DL",
            "district": "Delhi",
            "status": "UNDER_TRIAL",
            "minor_involved": False,
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.9,
        }
    )
    logs = tmp_path / "logs"
    # Run 1: the case is on MAIN at UNDER_TRIAL (media source D1).
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-08",
        out=io.StringIO(),
        docs=d1,
        extract_client=_FakeGemini(p1),
    )
    main_v1 = (tmp_path / "2026" / "DL.json").read_text()

    # Run 2: a court order D2 progresses the SAME case to APPEAL_PENDING. The enriched
    # record is force-pushed to the staging archive but NOT merged to main.
    d2 = [
        RawDocument(
            url="https://example.invalid/d2",
            publisher="eCourts",
            fetched_at="2026-07-10",
            text="A DL appeal.",
        )
    ]
    p2 = json.dumps(
        {
            "category": "rape",
            "state": "DL",
            "district": "Delhi",
            "status": "APPEAL_PENDING",
            "minor_involved": False,
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.9,
        }
    )
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=d2,
        extract_client=_FakeGemini(p2),
    )
    staged = tmp_path / "staged" / "2026"
    staged.mkdir(parents=True)
    (staged / "DL.json").write_text((tmp_path / "2026" / "DL.json").read_text())  # -> staging
    (tmp_path / "2026" / "DL.json").write_text(main_v1)  # main reverts (PR not merged)
    monkeypatch.setenv("STAGED_DIR", str(tmp_path / "staged"))

    # Run 3: D2 has rolled off the feed (no docs fetched). The enrichment must survive.
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-12",
        out=io.StringIO(),
        docs=[],
        extract_client=_FakeGemini(p2),
    )
    records = json.loads((tmp_path / "2026" / "DL.json").read_text())
    assert len(records) == 1
    assert records[0]["status"] == "APPEAL_PENDING"  # progression preserved, not reverted
    assert len(records[0]["sources"]) == 2  # D1 + D2 both retained


def test_minor_is_held_not_published(tmp_path: Path) -> None:
    """A minor's case passes dedupe but is HELD by the graduated gate — never on site."""
    doc = [
        RawDocument(
            url="https://example.invalid/minor",
            publisher="eCourts",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "minor_involved": True,
            "cnr": "C-MINOR",
            "in_scope": True,
            "confidence": 0.95,
        }
    )
    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert report.published == 0 and report.needs_review == 1
    assert not (tmp_path / "2026" / "TG.json").exists()  # NOT on the public site
    queue = json.loads((tmp_path / "_needs_review" / "queue.json").read_text())
    assert queue[0]["record"]["cnr"] == "C-MINOR" and "minor_involved" in queue[0]["reasons"]
    assert (
        "minor_involved" not in queue[0]["record"] or queue[0]["record"]["minor_involved"] is True
    )


def test_named_accused_is_held_not_published(tmp_path: Path) -> None:
    """A court-sourced record naming an accused is held for review (presumption of innocence)."""
    doc = [
        RawDocument(
            url="https://example.invalid/named",
            publisher="Delhi High Court",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "rape",
            "state": "DL",
            "district": "Delhi",
            "status": "CONVICTED",
            "minor_involved": False,
            "cnr": "C-NAMED",
            "court": {"name": "Delhi High Court"},
            "in_scope": True,
            "confidence": 0.95,
            "accused": [
                {
                    "label": "Accused #1",
                    "name_public_court_record": "A. Person",
                    "status": "CONVICTED",
                }
            ],
        }
    )
    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert report.published == 0 and report.needs_review == 1
    queue = json.loads((tmp_path / "_needs_review" / "queue.json").read_text())
    assert "named_accused" in queue[0]["reasons"]


def test_needs_review_hold_persists_via_carryover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A held record whose source rolls off the feed persists in the needs-review queue."""
    doc = [
        RawDocument(
            url="https://example.invalid/held",
            publisher="eCourts",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "minor_involved": True,
            "cnr": "C-HELD",
            "in_scope": True,
            "confidence": 0.95,
        }
    )
    logs = tmp_path / "logs"
    r1 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r1.needs_review == 1
    # Archive the staging tree (incl. _needs_review) into STAGED_DIR; the source doc
    # rolls off the feed (no docs). The hold must persist, not vanish.
    staged = tmp_path / "staged"
    (staged / "_needs_review").mkdir(parents=True)
    (staged / "_needs_review" / "queue.json").write_text(
        (tmp_path / "_needs_review" / "queue.json").read_text()
    )
    monkeypatch.setenv("STAGED_DIR", str(staged))
    r2 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=[],
        extract_client=_FakeGemini(payload),
    )
    assert r2.needs_review == 1  # carried over, never re-fetched
    queue = json.loads((tmp_path / "_needs_review" / "queue.json").read_text())
    assert queue[0]["record"]["cnr"] == "C-HELD"


def test_pocso_non_minor_is_held_not_published(tmp_path: Path) -> None:
    """A POCSO case the model flags non-minor is HELD (POCSO implies a minor)."""
    doc = [
        RawDocument(
            url="https://example.invalid/pocsomismatch",
            publisher="eCourts",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "minor_involved": False,  # model false-negative on a POCSO case
            "offence_sections": ["POCSO 6"],
            "incident_reported_date": "2026-06-14",
            "cnr": "C-MISMATCH",
            "in_scope": True,
            "confidence": 0.95,
        }
    )
    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert report.published == 0 and report.needs_review == 1
    assert not (tmp_path / "2026" / "TG.json").exists()  # never on the public site
    rec = json.loads((tmp_path / "_needs_review" / "queue.json").read_text())[0]["record"]
    # A POCSO signal forces minor treatment: the record is held AND age-projected, so
    # no day-precise date reaches even the committed queue (POCSO s.23).
    assert rec["minor_involved"] is True
    assert rec["incident_reported_date"] == "2026"


def test_non_bool_minor_is_projected_and_held(tmp_path: Path) -> None:
    """A truthy non-bool minor flag is coerced, so it is BOTH held AND age-projected."""
    doc = [
        RawDocument(
            url="https://example.invalid/truthy",
            publisher="eCourts",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "minor_involved": "true",  # truthy non-bool
            "incident_reported_date": "2026-06-14",
            "cnr": "C-TRUTHY",
            "in_scope": True,
            "confidence": 0.95,
        }
    )
    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert report.published == 0 and report.needs_review == 1
    rec = json.loads((tmp_path / "_needs_review" / "queue.json").read_text())[0]["record"]
    assert rec["minor_involved"] is True  # coerced to a strict bool
    assert rec["incident_reported_date"] == "2026"  # age-projected to year only (POCSO s.23)


def test_held_id_not_reused_by_new_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A published record that becomes held keeps its id reserved — no id is re-minted."""
    logs = tmp_path / "logs"

    def _run(rd: str, docs: list[RawDocument], payload: str) -> object:
        return orchestrator.run(
            dry_run=False,
            data_dir=tmp_path,
            logs_dir=logs,
            run_date=rd,
            out=io.StringIO(),
            docs=docs,
            extract_client=_FakeGemini(payload),
        )

    # Run 1: a MEDIA report (news_article) auto-publishes CNR-A as ...000001. Media so
    # run 2's COURT order becomes dedupe-primary (court beats media) and would DROP the
    # id but for the id-preserving merge fill — the real fusion path.
    a_doc = [
        RawDocument(
            url="https://ex.invalid/a",
            publisher="The Hindu",
            fetched_at="2026-07-09",
            text="x",
        )
    ]
    a_clean = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "minor_involved": False,
            "cnr": "CNR-A",
            "in_scope": True,
            "confidence": 0.90,
        }
    )
    _run("2026-07-09", a_doc, a_clean)
    first_id = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]["id"]

    # Run 2: a NEW court order (distinct url, same case) NAMES an accused -> CNR-A
    # becomes held; archive staging. A distinct url so the ledger does not skip it.
    a_doc2 = [
        RawDocument(
            url="https://ex.invalid/a2",
            publisher="Delhi High Court",
            fetched_at="2026-07-10",
            text="x",
        )
    ]
    a_named = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "CONVICTED",
            "minor_involved": False,
            "cnr": "CNR-A",
            "court": {"name": "Delhi High Court"},
            "in_scope": True,
            "confidence": 0.95,
            "accused": [
                {"label": "Accused #1", "name_public_court_record": "P", "status": "CONVICTED"}
            ],
        }
    )
    _run("2026-07-10", a_doc2, a_named)
    staged = tmp_path / "staged"
    staged.mkdir()
    import shutil

    shutil.copytree(tmp_path / "_needs_review", staged / "_needs_review")
    if (tmp_path / "2026").exists():
        shutil.copytree(tmp_path / "2026", staged / "2026")
    monkeypatch.setenv("STAGED_DIR", str(staged))

    # Run 3: an unrelated NEW case must NOT get CNR-A's freed id.
    c_doc = [
        RawDocument(
            url="https://ex.invalid/c", publisher="eCourts", fetched_at="2026-07-11", text="x"
        )
    ]
    c_payload = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "minor_involved": False,
            "cnr": "CNR-C",
            "in_scope": True,
            "confidence": 0.95,
        }
    )
    _run("2026-07-11", c_doc, c_payload)
    c_id = json.loads((tmp_path / "2026" / "TG.json").read_text())[0]["id"]
    assert c_id != first_id  # the held record's id was reserved, not fused


def test_held_record_persists_in_auto_mode_without_staged_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In auto mode (no STAGED_DIR) a held record persists via the committed queue."""
    monkeypatch.delenv("STAGED_DIR", raising=False)
    doc = [
        RawDocument(
            url="https://ex.invalid/held", publisher="eCourts", fetched_at="2026-07-09", text="x"
        )
    ]
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "minor_involved": True,
            "cnr": "C-HELD",
            "in_scope": True,
            "confidence": 0.95,
        }
    )
    logs = tmp_path / "logs"
    r1 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r1.needs_review == 1
    # Run 2: source rolled off (no docs); the committed queue on data_dir must persist it.
    r2 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=[],
        extract_client=_FakeGemini(payload),
    )
    assert r2.needs_review == 1
    assert (
        json.loads((tmp_path / "_needs_review" / "queue.json").read_text())[0]["record"]["cnr"]
        == "C-HELD"
    )


def test_review_doc_not_settled_by_collision_with_published(tmp_path: Path) -> None:
    """A quarantined review doc whose sanitised url collides with an on-main published
    record must still re-surface, not settle 'published' and vanish."""
    logs = tmp_path / "logs"
    # Run 1: publish case A from a PII-shaped url (sanitises to .../[redacted]/).
    a_doc = [
        RawDocument(
            url="https://indiankanoon.org/doc/9876543210/",
            publisher="The Hindu",
            fetched_at="2026-07-09",
            text="x",
        )
    ]
    a_payload = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "minor_involved": False,
            "cnr": "CNR-A",
            "in_scope": True,
            "confidence": 0.95,
        }
    )
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=a_doc,
        extract_client=_FakeGemini(a_payload),
    )
    # Run 2: a DISTINCT low-confidence case B from a different PII-shaped url that
    # sanitises to the SAME .../[redacted]/ string -> quarantined to _review.
    b_doc = [
        RawDocument(
            url="https://indiankanoon.org/doc/9123456780/",
            publisher="The Hindu",
            fetched_at="2026-07-10",
            text="x",
        )
    ]
    b_payload = json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "minor_involved": False,
            "cnr": "CNR-B",
            "in_scope": True,
            "confidence": 0.5,
        }
    )
    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=b_doc,
        extract_client=_FakeGemini(b_payload),
    )
    # Run 3: B must NOT have been settled by the canon collision — it re-surfaces.
    r3 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-11",
        out=io.StringIO(),
        docs=b_doc,
        extract_client=_FakeGemini(b_payload),
    )
    assert r3.skipped_settled == 0 and r3.review >= 1


def test_run_refuses_when_scope_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real run with LAUNCH_STATES unset refuses — never silently unscoped."""
    monkeypatch.delenv("LAUNCH_STATES", raising=False)
    with pytest.raises(RuntimeError, match="scope unresolved"):
        orchestrator.run(
            dry_run=False,
            data_dir=tmp_path,
            logs_dir=tmp_path / "logs",
            run_date="2026-07-09",
            out=io.StringIO(),
            docs=[],
            extract_client=_FakeGemini("{}"),
        )


def test_quarantined_doc_is_not_settled_and_resurfaces(tmp_path: Path) -> None:
    """A doc quarantined to the (ephemeral) review queue must be re-examined next run."""
    doc = [
        RawDocument(
            url="https://example.invalid/q",
            publisher="The Example Herald",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.4,  # below the publish threshold -> quarantined, not settled
        }
    )
    logs = tmp_path / "logs"
    r1 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r1.published == 0 and r1.review >= 1
    # Run 2: the quarantined doc is NOT settled, so it is re-processed and re-surfaced
    # (never silently lost from the ephemeral review queue).
    r2 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r2.skipped_settled == 0  # the quarantined doc was NOT skipped
    assert r2.review >= 1  # it re-surfaced for human review


def test_scope_filtered_doc_is_settled_out_of_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sexual-offence case outside the launch window settles (out_of_window) + is skipped."""
    monkeypatch.setenv("LAUNCH_STATES", "DL")  # a TG case is filtered out
    doc = [
        RawDocument(
            url="https://example.invalid/tgcase",
            publisher="eCourts",
            fetched_at="2026-07-09",
            text="A TESTVILLE case.",
        )
    ]
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "cnr": "C-1",
            "in_scope": True,
            "confidence": 0.9,
        }
    )
    logs = tmp_path / "logs"
    r1 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=doc,
        extract_client=_FakeGemini(payload),
    )
    assert r1.published == 0  # TG is outside LAUNCH_STATES=DL

    class _Poison:
        def generate(self, prompt: str) -> ExtractionResponse:
            raise AssertionError("out_of_window doc must not be re-extracted (same window)")

    r2 = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=logs,
        run_date="2026-07-11",
        out=io.StringIO(),
        docs=doc,
        extract_client=_Poison(),
    )
    assert r2.skipped_settled == 1  # settled as out_of_window under the fixed window


def test_in_scope_helper() -> None:
    record = {"state": "TG", "incident_reported_date": "2026-07-01"}
    assert orchestrator._in_scope(record, frozenset({"TG"}), 30, "2026-07-10")
    assert not orchestrator._in_scope(record, frozenset({"DL"}), None, "2026-07-10")
    old = {"state": "TG", "incident_reported_date": "2020-01-01"}
    assert not orchestrator._in_scope(old, None, 30, "2026-07-10")  # outside lookback
    assert orchestrator._in_scope(record, None, None, "2026-07-10")  # unbounded


def _tg_payload() -> str:
    return json.dumps(
        {
            "category": "rape",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "minor_involved": False,
            "cnr": "C-SCOPE",
            "in_scope": True,
            "confidence": 0.9,
        }
    )


def test_scope_filters_out_of_state_and_writes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LAUNCH_STATES", "DL")  # the candidate is TG -> filtered out
    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=fixture_raw_documents(),
        extract_client=_FakeGemini(_tg_payload()),
    )
    assert report.published == 0
    assert "DL" in report.scope
    assert (tmp_path / "logs" / "run_report.md").exists()


def test_in_scope_publishes_with_report_stats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LAUNCH_STATES", "TG")
    report = orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-10",
        out=io.StringIO(),
        docs=fixture_raw_documents(),
        extract_client=_FakeGemini(_tg_payload()),
    )
    assert report.published == 1
    assert report.state_counts.get("TG") == 1
    assert "eCourts" in report.source_counts
    report_md = (tmp_path / "logs" / "run_report.md").read_text()
    assert "Data review: 2026-07-10" in report_md and "Auto-eligible by state" in report_md


def test_offence_relevant_docs_extracted_first(tmp_path: Path) -> None:
    """A truncation-bounded run reaches likely-case docs first (relevance ordering)."""
    docs = [
        RawDocument(
            url="https://ex.invalid/weather",
            publisher="The Hindu",
            fetched_at="2026-07-09",
            text="City weather update: light rain expected.",
        ),
        RawDocument(
            url="https://ex.invalid/traffic",
            publisher="The Hindu",
            fetched_at="2026-07-09",
            text="Traffic diversions near the metro station.",
        ),
        RawDocument(
            url="https://ex.invalid/case",
            publisher="The Hindu",
            fetched_at="2026-07-09",
            text="A man was arrested on rape charges under BNS 64.",
        ),
    ]
    seen_order: list[str] = []

    class _RecordingGemini:
        def generate(self, prompt: str) -> ExtractionResponse:
            # The article body is embedded in the prompt; capture which doc came first.
            for tag in ("weather", "traffic", "rape charges"):
                if tag in prompt:
                    seen_order.append(tag)
                    break
            return ExtractionResponse(text="{}", input_tokens=10, output_tokens=5)

    orchestrator.run(
        dry_run=False,
        data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        run_date="2026-07-09",
        out=io.StringIO(),
        docs=docs,
        extract_client=_RecordingGemini(),
    )
    assert seen_order[0] == "rape charges"  # the likely-case doc is extracted first
