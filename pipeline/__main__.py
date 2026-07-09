"""Pipeline orchestrator: fetch -> extract -> sanitize -> dedupe -> validate -> shard.

Wires the daily run end to end. EVERY record — and every log line and review
entry — passes through :mod:`pipeline.sanitize` before it can touch disk; nothing
from a source or the model is trusted directly.

Usage::

    python -m pipeline                 # real run against configured sources
    python -m pipeline --dry-run       # offline: fixtures only, no network/Gemini

``--dry-run`` proves the whole flow works with synthetic TESTVILLE fixtures,
writing to a throwaway directory and printing a transcript, one record's full
journey (raw -> extracted -> sanitized -> deduped -> sharded), and an illustrative
Gemini cost estimate. CI uses it to gate the pipeline without a network or key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, TextIO

from scripts.pii_guard import iter_json_files, scan_json_file

from pipeline import config, fixtures
from pipeline.dedupe import dedupe
from pipeline.extract.gemini import ExtractionClient, extract
from pipeline.sanitize import sanitize_record, sanitize_string
from pipeline.shard import WriteResult, write_shards
from pipeline.sources.base import RawDocument, Source
from pipeline.sources.ecourts import EcourtsSource
from pipeline.sources.http import PoliteClient
from pipeline.sources.rss_media import RssMediaSource
from pipeline.validate import load_schema, project_to_schema


@dataclass
class RunReport:
    """Everything a caller (or the CI transcript) needs to know about a run."""

    new: int = 0
    updated: int = 0
    review: int = 0
    published: int = 0
    estimated_usd: float = 0.0
    logs: list[str] = field(default_factory=list)


def _log(report: RunReport, message: str) -> None:
    """Append a log line, sanitized — logs never carry PII either."""
    report.logs.append(sanitize_string(message))


async def _fetch_all(client: PoliteClient) -> list[RawDocument]:
    """Fetch from every configured source with one polite client."""
    sources: list[Source] = [EcourtsSource(client), RssMediaSource(client)]
    docs: list[RawDocument] = []
    for source in sources:
        docs.extend(await source.fetch())
    return docs


def _fetch_documents() -> list[RawDocument]:  # pragma: no cover - real network I/O
    async def _go() -> list[RawDocument]:
        async with PoliteClient() as client:
            return await _fetch_all(client)

    return asyncio.run(_go())


def _illustrative_cost(docs: list[RawDocument]) -> float:
    """A rough cost estimate for the fixture docs (~4 chars/token) for the dry-run."""
    input_tokens = sum(len(doc.text) for doc in docs) // 4 + 400 * len(docs)
    output_tokens = 200 * len(docs)
    return config.estimate_cost_usd(input_tokens, output_tokens)


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


def _assert_no_pii(data_dir: Path) -> None:
    """Run scripts/pii_guard over the written tree; raise on any finding."""
    findings = [f for json_file in iter_json_files([data_dir]) for f in scan_json_file(json_file)]
    if findings:
        raise RuntimeError(
            f"pii_guard blocked the write: {len(findings)} finding(s); first: {findings[0]}"
        )


def _write_logs(report: RunReport, logs_dir: Path, run_date: str) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "run.log").write_text("\n".join(report.logs) + "\n", encoding="utf-8")
    (logs_dir / "run_summary.env").write_text(
        f"NEW={report.new}\nUPDATED={report.updated}\nREVIEW={report.review}\n",
        encoding="utf-8",
    )


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

    if dry_run:
        raw_docs = fixtures.fixture_raw_documents()
        extractions = fixtures.fixture_extractions()
        report.estimated_usd = _illustrative_cost(raw_docs)
        _log(report, f"dry-run: {len(extractions)} fixture extractions (no network, no Gemini)")
    else:
        raw_docs = docs if docs is not None else _fetch_documents()
        _log(report, f"fetched {len(raw_docs)} documents")
        result = extract(
            raw_docs, client=extract_client, cost_log_path=logs_dir / "gemini_cost.json"
        )
        extractions = result.records
        report.estimated_usd = result.estimated_usd
        _log(report, f"extracted {len(extractions)} candidates; est ${result.estimated_usd:.6f}")

    # LAST GATE BEFORE DISK: sanitize every candidate, then project onto the schema
    # allow-list so no unknown (possibly PII-bearing) key can survive to a published
    # shard OR the review queue.
    case_schema = load_schema()
    sanitized = [project_to_schema(sanitize_record(record), case_schema) for record in extractions]
    published, review = dedupe(sanitized)
    _log(report, f"deduped: {len(published)} published, {len(review)} to review")

    write_result: WriteResult = write_shards(published, data_dir, run_date=run_date)
    _write_review(review, data_dir, run_date)

    # Independent final assertion over EVERY file just written (shards + review
    # queue). A hit fails the run before any commit — the guard is not deferred to
    # a post-push CI job.
    _assert_no_pii(data_dir)

    report.new = write_result.new
    report.updated = write_result.updated
    report.review = len(review)
    report.published = write_result.published
    _write_logs(report, logs_dir, run_date)

    if dry_run:
        sharded = _first_sharded_record(data_dir)
        _print_journey(
            out,
            raw_docs,
            extractions[0] if extractions else {},
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
            f"documents at {config.GEMINI_MODEL} rates: ${report.estimated_usd:.6f}\n"
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
