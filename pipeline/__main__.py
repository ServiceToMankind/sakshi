"""Pipeline orchestrator: fetch -> extract -> sanitize -> dedupe -> validate -> shard.

Wires the daily run end to end. EVERY record — and every log line and review
entry — passes through :mod:`pipeline.sanitize` before it can touch disk; nothing
from a source or the model is trusted directly.

Usage::

    python -m pipeline                 # real run against the sources in sources.yml
    python -m pipeline --dry-run       # offline: fixtures only, no network/Gemini

Scope is bounded by ``LAUNCH_STATES`` / ``LAUNCH_LOOKBACK_DAYS`` (env), so a
supervised first run can be limited to a readable window. ``--dry-run`` proves
the whole flow works with synthetic TESTVILLE fixtures without a network or key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, TextIO

from scripts.pii_guard import iter_json_files, scan_json_file

from pipeline import config, fixtures
from pipeline.dedupe import dedupe
from pipeline.extract.gemini import ExtractionClient, extract
from pipeline.ledger import Ledger, load_ledger, save_ledger
from pipeline.sanitize import sanitize_record, sanitize_string
from pipeline.shard import WriteResult, write_shards
from pipeline.sources.base import RawDocument
from pipeline.sources.http import PoliteClient
from pipeline.sources.registry import build_sources
from pipeline.validate import (
    iter_shard_files,
    load_schema,
    project_to_schema,
    withhold_unsourced_accused_names,
)


@dataclass
class RunReport:
    """Everything a caller (or the review PR) needs to know about a run."""

    new: int = 0
    updated: int = 0
    review: int = 0
    published: int = 0
    fetched: int = 0
    processed: int = 0
    skipped_settled: int = 0
    extracted: int = 0
    rejected_out_of_scope: int = 0
    estimated_usd: float = 0.0
    scope: str = ""
    state_counts: dict[str, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    review_reasons: dict[str, int] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


def _log(report: RunReport, message: str) -> None:
    """Append a log line, sanitized — logs never carry PII either."""
    report.logs.append(sanitize_string(message))


async def _fetch_all(client: PoliteClient, fetched_at: str) -> list[RawDocument]:
    """Fetch from every ENABLED source (sources.yml) with one polite client."""
    docs: list[RawDocument] = []
    for source in build_sources(client, fetched_at=fetched_at):
        docs.extend(await source.fetch())
    return docs


def _fetch_documents(fetched_at: str) -> list[RawDocument]:  # pragma: no cover - network I/O
    async def _go() -> list[RawDocument]:
        async with PoliteClient() as client:
            return await _fetch_all(client, fetched_at)

    return asyncio.run(_go())


def _illustrative_cost(docs: list[RawDocument]) -> float:
    """A rough cost estimate for the fixture docs (~4 chars/token) for the dry-run."""
    input_tokens = sum(len(doc.text) for doc in docs) // 4 + 400 * len(docs)
    output_tokens = 200 * len(docs)
    return config.estimate_cost_usd(input_tokens, output_tokens)


def _in_scope(
    record: dict[str, Any], states: frozenset[str] | None, lookback: int | None, run_date: str
) -> bool:
    """True if the record is within the configured state set and lookback window."""
    if states is not None and str(record.get("state", "")).upper() not in states:
        return False
    if lookback is not None:
        try:
            reported = date.fromisoformat(str(record.get("incident_reported_date")))
            run_day = date.fromisoformat(run_date)
        except (ValueError, TypeError):
            return False
        if reported > run_day or (run_day - reported).days > lookback:
            return False
    return True


def _scope_label(states: frozenset[str] | None, lookback: int | None) -> str:
    where = ",".join(sorted(states)) if states else "all states"
    window = f"last {lookback}d" if lookback is not None else "no window"
    return f"{where}; {window}"


def _write_review(review: list[dict[str, Any]], data_dir: Path, run_date: str) -> None:
    if not review:
        return
    review_dir = data_dir / "_review"
    review_dir.mkdir(parents=True, exist_ok=True)
    payload = [
        {"reason": item["reason"], "record": sanitize_record(item["record"])} for item in review
    ]
    (review_dir / f"review-{run_date}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_existing_published(data_dir: Path) -> list[dict[str, Any]]:
    """Load already-published records so a run regenerates the FULL tree.

    The committed shards are the canonical store. Without this, a run that only
    fetched new documents would republish just those and ``_clear_stale_shards``
    would delete all prior cases. Existing records re-enter dedupe so new documents
    merge into them and history is preserved.
    """
    records: list[dict[str, Any]] = []
    for shard in iter_shard_files(data_dir):
        records.extend(json.loads(shard.read_text(encoding="utf-8")))
    return records


def _update_ledger(
    ledger: Ledger,
    doc_outcomes: dict[str, str],
    published: list[dict[str, Any]],
    review: list[dict[str, Any]],
    run_date: str,
    report: RunReport,
    data_dir: Path,
) -> None:
    """Record each processed document's outcome and persist the ledger.

    An ``extracted`` document resolves to one of three fates:
    - its URL reached a ``published`` record (directly or via source-union) -> settle;
    - it is quarantined to the review queue -> NOT settled (``continue``), so it
      re-surfaces every run until a human resolves it ("delay, not loss");
    - it was dropped by the launch scope window (state/lookback) -> ``out_of_window``,
      terminal for coverage accounting under the CURRENT window. (Widening
      LAUNCH_STATES/LOOKBACK later requires deleting data/_meta/processed.json.)
    ``out_of_scope``/``not_a_case``/``failed`` come straight from extraction.
    """
    published_urls = {
        str(source.get("url", "")) for record in published for source in record.get("sources", [])
    }
    review_urls = {
        str(source.get("url", ""))
        for item in review
        for source in item["record"].get("sources", [])
    }
    for url, outcome in doc_outcomes.items():
        if outcome == "extracted":
            if url in published_urls:
                outcome = "published"
            elif url in review_urls:
                continue  # quarantined for human review: NOT settled, re-surface
            else:
                outcome = "out_of_window"  # scope-filtered (state/lookback)
        if ledger.record(url, outcome, run_date) == "failed_permanent":
            _log(report, f"failed_permanent after retries (manual review): {url}")
    save_ledger(data_dir, ledger)


def _assert_no_pii(data_dir: Path) -> None:
    """Run scripts/pii_guard over the written tree; raise on any finding."""
    findings = [f for json_file in iter_json_files([data_dir]) for f in scan_json_file(json_file)]
    if findings:
        raise RuntimeError(
            f"pii_guard blocked the write: {len(findings)} finding(s); first: {findings[0]}"
        )


def _render_report(report: RunReport, run_date: str) -> str:
    def table(title: str, counts: dict[str, int]) -> str:
        if not counts:
            return f"### {title}\n\n_none_\n"
        rows = "\n".join(f"| {k or '—'} | {v} |" for k, v in counts.items())
        return f"### {title}\n\n| key | count |\n|---|---|\n{rows}\n"

    return (
        f"# Data review: {run_date}\n\n"
        f"**Mode:** {config.launch_mode()} · **Scope:** {report.scope}\n\n"
        "| metric | value |\n|---|---|\n"
        f"| Fetched documents | {report.fetched} |\n"
        f"| Processed this run | {report.processed} |\n"
        f"| Skipped (already settled) | {report.skipped_settled} |\n"
        f"| Extracted candidates | {report.extracted} |\n"
        f"| Rejected (out of scope) | {report.rejected_out_of_scope} |\n"
        f"| **Published (whole tree)** | {report.published} |\n"
        f"| New this run | {report.new} |\n"
        f"| Updated | {report.updated} |\n"
        f"| Review queue | {report.review} |\n"
        f"| Est. Gemini cost | ${report.estimated_usd:.4f} |\n\n"
        f"{table('By state', report.state_counts)}\n"
        f"{table('By source', report.source_counts)}\n"
        f"{table('Review queue (reasons)', report.review_reasons)}\n"
        "> Every record is cited to a public source; accused names appear only from "
        "court records. Review the `data/` diff and `data/_review/` before merging. "
        "Nothing publishes until a human merges this PR.\n"
    )


def _write_logs(report: RunReport, logs_dir: Path, run_date: str) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "run.log").write_text("\n".join(report.logs) + "\n", encoding="utf-8")
    (logs_dir / "run_summary.env").write_text(
        f"NEW={report.new}\nUPDATED={report.updated}\nREVIEW={report.review}\n"
        f"PUBLISHED={report.published}\nREJECTED={report.rejected_out_of_scope}\n"
        f"FETCHED={report.fetched}\nPROCESSED={report.processed}\n"
        f"SKIPPED={report.skipped_settled}\nEXTRACTED={report.extracted}\n"
        f"COST={report.estimated_usd:.6f}\n",
        encoding="utf-8",
    )
    (logs_dir / "run_report.md").write_text(_render_report(report, run_date), encoding="utf-8")


def _print_journey(
    out: TextIO,
    raw_docs: list[RawDocument],
    pre_sanitize: dict[str, Any],
    sanitized: dict[str, Any],
    published: dict[str, Any],
    sharded: dict[str, Any] | None,
) -> None:
    def block(title: str, value: Any) -> None:
        out.write(f"\n--- {title} ---\n")
        out.write(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
        out.write("\n")

    out.write("\n=== ONE RECORD'S JOURNEY (synthetic TESTVILLE fixture) ===\n")
    block(
        "1. RAW documents",
        [{"url": d.url, "publisher": d.publisher, "text": d.text} for d in raw_docs],
    )
    block("2. EXTRACTED (pre-sanitize; note the forbidden 'victim' key)", pre_sanitize)
    block("3. SANITIZED (forbidden keys dropped, PII values redacted)", sanitized)
    block("4. DEDUPED / MERGED (sources unioned, court status wins)", published)
    if sharded is not None:
        block("5. SHARDED (deterministic id, last_verified, pending_days assigned)", sharded)


def run(
    *,
    dry_run: bool,
    data_dir: Path,
    logs_dir: Path,
    run_date: str,
    out: TextIO,
    docs: list[RawDocument] | None = None,
    extract_client: ExtractionClient | None = None,
) -> RunReport:
    """Execute one pipeline run and return a :class:`RunReport`."""
    report = RunReport()
    states = config.launch_states()
    lookback = config.launch_lookback_days()
    report.scope = _scope_label(states, lookback)

    ledger: Ledger | None = None
    doc_outcomes: dict[str, str] = {}
    if dry_run:
        raw_docs = fixtures.fixture_raw_documents()
        extractions = fixtures.fixture_extractions()
        report.estimated_usd = _illustrative_cost(raw_docs)
        _log(report, f"dry-run: {len(extractions)} fixture extractions (no network, no Gemini)")
    else:
        raw_docs = docs if docs is not None else _fetch_documents(run_date)
        # Skip documents already settled in prior runs so the budget goes to the
        # backlog TAIL — turns provider degradation into delay, not lost coverage.
        ledger = load_ledger(data_dir)
        to_process = [d for d in raw_docs if ledger.should_process(d.url)]
        report.processed = len(to_process)
        report.skipped_settled = len(raw_docs) - len(to_process)
        _log(
            report,
            f"fetched {len(raw_docs)} documents ({report.processed} to process, "
            f"{report.skipped_settled} already settled)",
        )
        result = extract(
            to_process, client=extract_client, cost_log_path=logs_dir / "gemini_cost.json"
        )
        doc_outcomes = result.doc_outcomes
        extractions = result.records
        report.estimated_usd = result.estimated_usd
        report.rejected_out_of_scope = result.rejected_out_of_scope
        detail = f"{result.failed} failed"
        if result.rejected_out_of_scope:
            detail += f", {result.rejected_out_of_scope} out-of-scope rejected"
        if result.failovers:
            detail += f", {result.failovers} model failover(s)"
        if result.truncated:
            detail += f", TRUNCATED ({result.truncated_reason})"
        if result.aborted:
            detail += ", ABORTED (all models exhausted / provider overload)"
        _log(
            report,
            f"extracted {len(extractions)} candidates ({detail}); est ${result.estimated_usd:.6f}",
        )
        for sample in result.error_samples:
            _log(report, f"provider error: {sample}")

    report.fetched = len(raw_docs)
    report.extracted = len(extractions)

    # Bound this run to the configured states + lookback window FIRST, on the raw
    # extraction. The minor-record projection (in sanitize) truncates
    # incident_reported_date to a year, which a lookback window could not parse — so
    # scoping must read the full date before sanitisation. Only state + date (both
    # non-PII) are read here; nothing is written.
    in_scope = [r for r in extractions if _in_scope(r, states, lookback, run_date)]
    if len(in_scope) != len(extractions):
        _log(report, f"scope: {len(in_scope)}/{len(extractions)} in scope ({report.scope})")

    # LAST GATE BEFORE DISK: sanitize every in-scope candidate (drop forbidden keys,
    # redact PII values, structurally project minor records), then project onto the
    # schema allow-list so no unknown key can survive to a shard OR the review queue.
    case_schema = load_schema()
    sanitized = [
        withhold_unsourced_accused_names(project_to_schema(sanitize_record(record), case_schema))
        for record in in_scope
    ]

    # Fold in already-published records so the run regenerates the whole tree and
    # new documents merge into existing cases rather than replacing history.
    existing = _load_existing_published(data_dir)
    published, review = dedupe(existing + sanitized)
    _log(report, f"deduped: {len(published)} published, {len(review)} to review")

    write_result: WriteResult = write_shards(published, data_dir, run_date=run_date)
    _write_review(review, data_dir, run_date)

    # Update the processed-document ledger (real runs only): a settled document is
    # not re-extracted; a failing one is retried until its budget is spent, then
    # parked as failed_permanent with its URL logged once for manual review.
    if ledger is not None:
        _update_ledger(ledger, doc_outcomes, published, review, run_date, report, data_dir)

    # Independent final assertion over EVERY file just written (shards + review
    # queue). A hit fails the run before any commit — not deferred to post-push CI.
    _assert_no_pii(data_dir)

    report.new = write_result.new
    report.updated = write_result.updated
    report.review = len(review)
    report.published = write_result.published
    report.state_counts = dict(sorted(Counter(str(r.get("state", "")) for r in published).items()))
    report.source_counts = dict(
        sorted(
            Counter(
                str(s.get("publisher", "")) for r in published for s in r.get("sources", [])
            ).items()
        )
    )
    report.review_reasons = dict(sorted(Counter(item["reason"] for item in review).items()))
    _write_logs(report, logs_dir, run_date)

    if dry_run:
        sharded = _first_sharded_record(data_dir)
        _print_journey(
            out,
            raw_docs,
            in_scope[0] if in_scope else {},
            sanitized[0] if sanitized else {},
            published[0] if published else {},
            sharded,
        )
        out.write("\n=== DRY-RUN RESULT ===\n")
        out.write(
            f"published={report.published} new={report.new} updated={report.updated} "
            f"review={report.review}\n"
        )
        out.write(
            f"Gemini: 0 live calls (fixtures). Illustrative cost estimate for these "
            f"documents at {config.gemini_models()[0]} rates: ${report.estimated_usd:.6f}\n"
        )
    return report


def _first_sharded_record(data_dir: Path) -> dict[str, Any] | None:
    index_path = data_dir / "index.json"
    if not index_path.exists():
        return None
    index = json.loads(index_path.read_text(encoding="utf-8"))
    shards = index.get("shards", [])
    if not shards:
        return None
    records = json.loads((data_dir / shards[0]["path"]).read_text(encoding="utf-8"))
    return records[0] if records else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline", description="Sakshi daily pipeline.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run offline against synthetic fixtures; write to a throwaway directory.",
    )
    parser.add_argument("--data-dir", type=Path, default=None, help="Output data directory.")
    parser.add_argument("--run-date", default=None, help="Override run date (YYYY-MM-DD).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    run_date = args.run_date or date.today().isoformat()

    if args.data_dir is not None:
        data_dir = args.data_dir
        logs_dir = config.LOGS_DIR
    elif args.dry_run:
        data_dir = Path(tempfile.mkdtemp(prefix="sakshi-dryrun-"))
        logs_dir = data_dir / "logs"
    else:
        data_dir = config.DATA_DIR
        logs_dir = config.LOGS_DIR

    try:
        run(
            dry_run=args.dry_run,
            data_dir=data_dir,
            logs_dir=logs_dir,
            run_date=run_date,
            out=sys.stdout,
        )
    except Exception as exc:  # pragma: no cover - top-level failure path
        print(f"pipeline run failed: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\nDry-run wrote to: {data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
