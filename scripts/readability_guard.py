#!/usr/bin/env python3
"""Readability assertion over PUBLISHED non-minor summaries (§6a).

A prompt instruction is not a gate — this is the deterministic check that stands behind it,
run over the written tree so an unreadable summary fails the run rather than shipping. It
imports its rules from ``pipeline.readability`` (shared with the pipeline gate), scans every
published ``data/{YYYY}/{STATE}.json`` shard, and flags any NON-minor summary that carries
legalese, a bare section-number citation, or a sentence over the word limit. A MINOR's
summary is deterministic (fixed vocabulary) and is exempt.

Usage:
    readability_guard.py [PATH ...]   # default: data/
Exit 0 = clean; non-zero = at least one finding printed as ``<file>: <id>: <reason>``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:  # pragma: no cover - import-time path shim
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline.readability import readability_violations  # noqa: E402
from pipeline.validate import iter_shard_files  # noqa: E402


def scan_record(record: dict[str, Any]) -> list[str]:
    """Return readability reasons for a record's summary (empty if minor or clean)."""
    if record.get("minor_involved"):
        return []
    return readability_violations(record.get("summary"))


def scan_tree(paths: list[Path]) -> list[str]:
    """Return ``<file>: <id>: <reason>`` findings across every shard under ``paths``."""
    findings: list[str] = []
    roots = paths or [Path("data")]
    for root in roots:
        for shard in iter_shard_files(root):
            try:
                records = json.loads(shard.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                findings.append(f"{shard}: <file>: could not read/parse JSON: {exc}")
                continue
            for record in records:
                rid = record.get("id", "<no-id>")
                for reason in scan_record(record):
                    findings.append(f"{shard}: {rid}: {reason}")
    return findings


def main(argv: list[str] | None = None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    findings = scan_tree(paths)
    for finding in findings:
        print(finding)
    if findings:
        print(f"\nreadability_guard: {len(findings)} non-minor summary issue(s).", file=sys.stderr)
        return 1
    print("Readability guard clean: every published non-minor summary is plain.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
