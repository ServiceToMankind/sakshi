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

    text = out.getvalue()
    assert "ONE RECORD'S JOURNEY" in text
    assert "DRY-RUN RESULT" in text

    records = json.loads((tmp_path / "2026" / "TG.json").read_text())
    assert records[0]["id"] == "SKS-2026-TG-000001"
    assert len(records[0]["sources"]) == 2  # court + media unioned
    assert "victim" not in records[0]

    env = (tmp_path / "logs" / "run_summary.env").read_text()
    assert "NEW=1" in env and "REVIEW=0" in env


def test_real_branch_with_injected_client_merges_sources(tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "UNDER_TRIAL",
            "cnr": "C-1",
            "fir_ref": {"station": "TESTVILLE PS", "number": "12/2026"},
            "incident_reported_date": "2026-06-14",
            "offence_sections": ["BNS 64"],
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
                "category": "pocso",
                "state": "TG",
                "district": "TESTVILLE",
                "status": "FIR_FILED",
                "minor_involved": True,
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
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "minor_involved": True,
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

    # Run 2: same doc. A poisoned client raises if called; the ledger must skip the
    # settled document so it is never invoked.
    class _Poison:
        def generate(self, prompt: str) -> ExtractionResponse:
            raise AssertionError("settled document must not be re-extracted")

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
            "category": "pocso",
            "state": "TG",
            "district": "TESTVILLE",
            "status": "FIR_FILED",
            "minor_involved": True,
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
    assert "Data review: 2026-07-10" in report_md and "By state" in report_md
