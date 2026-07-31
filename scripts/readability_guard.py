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

# BASELINE ALLOWLIST — pre-existing records whose summary predates §6a and cannot be made
# readable without a live re-extraction (no Gemini key locally). Each entry EXEMPTS that id
# from failing the run, but is self-cleaning: once the automation re-extracts the record into
# a compliant summary, the guard reports the entry as STALE so it is removed. The allowlist
# MUST shrink to empty. Never add a new id to keep the run green — fix the summary instead.
BASELINE_ALLOWLIST: dict[str, str] = {
    "SKS-2026-DL-000008": "'petitioners' — pending plain-language re-extraction (added 2026-07-31)",
}


def scan_record(record: dict[str, Any]) -> list[str]:
    """Return readability reasons for a record's summary (empty if minor or clean)."""
    if record.get("minor_involved"):
        return []
    return readability_violations(record.get("summary"))


def scan_tree(paths: list[Path]) -> list[str]:
    """Return ``<file>: <id>: <reason>`` findings across every shard under ``paths``.

    A record in ``BASELINE_ALLOWLIST`` is exempted from its violations; but an allowlisted
    record that is NOW clean yields a STALE-entry finding, forcing the allowlist to shrink.
    """
    findings: list[str] = []
    seen_allowlisted: set[str] = set()
    roots = paths or [Path("data")]
    for root in roots:
        for shard in iter_shard_files(root):
            try:
                records = json.loads(shard.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                findings.append(f"{shard}: <file>: could not read/parse JSON: {exc}")
                continue
            for record in records:
                rid = str(record.get("id", "<no-id>"))
                reasons = scan_record(record)
                if rid in BASELINE_ALLOWLIST:
                    seen_allowlisted.add(rid)
                    if not reasons:
                        findings.append(
                            f"{shard}: {rid}: STALE allowlist entry — record is now readable; "
                            f"remove it from BASELINE_ALLOWLIST"
                        )
                    continue  # exempt: known pre-existing violation, tracked
                for reason in reasons:
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
