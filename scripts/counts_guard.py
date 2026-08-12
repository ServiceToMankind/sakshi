#!/usr/bin/env python3
"""Count-invariant guard — one number, everywhere (Phase 9 §1).

A published record must be counted in EVERY aggregate the site renders, or the build fails.
This asserts, over the committed ``data/`` tree:

  summary.total == sum(shard records) == index record total == recent-feed universe
                == scorecard universe (summary.jurisdictions) == coverage record total

plus the per-state and per-status breakdowns, that every state with published records is
COVERED (never shown as a gap just because its records arrived via a national source such as
Indian Kanoon rather than a per-state feed), and that summary.json + index.json carry a
non-empty ``generated_at`` so the "Last updated" footer always populates.

The map tiles, state tables, scorecards and footer all read these aggregates; if one of them
disagrees with the shards, a real published record is invisible somewhere. That is a
correctness bug, so it fails CI here rather than being caught by eyeball.

Exit 0 = every count agrees; non-zero = at least one disagreement, printed.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_counts(data_dir: Path) -> list[str]:
    """Return a list of disagreements (empty = every count agrees)."""
    findings: list[str] = []

    # The shards are the source of truth for "what is published".
    shard_records: list[dict[str, Any]] = []
    for shard in sorted(data_dir.glob("20*/??.json")):
        shard_records.extend(_load(shard))
    shard_total = len(shard_records)
    shard_states = Counter(str(r.get("state", "")) for r in shard_records)
    shard_status = Counter(str(r.get("status", "")) for r in shard_records)
    shard_ids = {str(r.get("id", "")) for r in shard_records}

    summary = _load(data_dir / "summary.json")
    index = _load(data_dir / "index.json")

    # 1. totals across summary, index, shards.
    if summary.get("total") != shard_total:
        findings.append(f"summary.total={summary.get('total')} != shard records={shard_total}")
    index_total = sum(int(s.get("records", 0)) for s in index.get("shards", []))
    if index_total != shard_total:
        findings.append(f"index record total={index_total} != shard records={shard_total}")

    # 2. per-state + per-status breakdowns.
    for state, n in shard_states.items():
        got = int((summary.get("state_counts") or {}).get(state, 0))
        if got != n:
            findings.append(f"summary.state_counts[{state}]={got} != shard count={n}")
    for status, n in shard_status.items():
        got = int((summary.get("status_counts") or {}).get(status, 0))
        if got != n:
            findings.append(f"summary.status_counts[{status}]={got} != shard count={n}")

    # 3. recent-feed universe ⊆ shards (a card the feed shows must exist in the counted tree).
    try:
        recent = _load(data_dir / "recent.json")
        orphan = {str(r.get("id", "")) for r in recent} - shard_ids
        if orphan:
            findings.append(
                f"recent.json has {len(orphan)} record(s) not in any shard: {sorted(orphan)[:5]}"
            )
    except FileNotFoundError:
        pass

    # 4. scorecard universe: every state with records has a jurisdiction row (else the
    #    scorecard silently drops that state's cases).
    jur_states = {str(j.get("state", "")) for j in (summary.get("jurisdictions") or [])}
    missing_jur = {s for s in shard_states if s and s not in jur_states}
    if missing_jur:
        findings.append(f"scorecard missing state(s) that have records: {sorted(missing_jur)}")

    # 5. coverage: a state with published records is COVERED by definition (records OR a source),
    #    and its record count matches the shards — never hidden because it lacked a per-state feed.
    try:
        coverage = _load(data_dir / "coverage.json")
        cov_states = coverage.get("states") or {}
        for state, n in shard_states.items():
            if not state:
                continue
            info = cov_states.get(state)
            if info is None:
                findings.append(f"coverage.json has NO entry for state {state} (has {n} records)")
                continue
            if int(info.get("records", -1)) != n:
                findings.append(
                    f"coverage.states[{state}].records={info.get('records')} != shard count={n}"
                )
            covered = int(info.get("active_sources", 0)) > 0 or int(info.get("records", 0)) > 0
            if not covered:
                findings.append(
                    f"coverage.states[{state}] not covered despite {n} published records"
                )
    except FileNotFoundError:
        pass

    # 6. "Last updated" footer: summary + index must carry a non-empty generated_at.
    for name, blob in (("summary.json", summary), ("index.json", index)):
        if not str(blob.get("generated_at") or "").strip():
            findings.append(
                f"{name} has no generated_at — the 'Last updated' footer would be empty"
            )

    return findings


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    data_dir = Path(argv[0]) if argv else _REPO / "data"
    findings = check_counts(data_dir)
    if findings:
        print("COUNT GUARD FAILED — a published record is uncounted somewhere:", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("Count guard clean: one number everywhere (summary/index/recent/scorecard/coverage).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
