#!/usr/bin/env python3
"""``make backfill`` — a LOCAL historical backfill runner.

Runs the full pipeline (fetch → extract → **the same sanitize/gates/pii_guard** as the
scheduled job) on your machine, with a **hard USD cost cap** and a **printed estimate**, and
leaves the result on a git BRANCH for a normal review PR — it never commits to ``main``. This
removes GitHub Actions minutes (and the 2-runs/day cap) as a constraint on historical backfill.

The hard cap is enforced by translating ``--max-usd`` into a per-run Gemini token cap: once the
run's estimated spend reaches it, extraction stops and the run stages whatever it has (a LOUD
budget-exhausted message, never a silent truncation). Keys are read from ``gemini_api.txt`` /
``kanoon_api.txt`` (gitignored) if the env vars are unset.

Usage:
    python scripts/backfill.py --lookback-days 365 --max-usd 5 [--states ALL] [--yes]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from pipeline import config  # noqa: E402


def _load_key(filename: str, env: str) -> None:
    path = _REPO / filename
    if path.exists() and not os.environ.get(env):
        os.environ[env] = path.read_text(encoding="utf-8").strip()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backfill", description=__doc__)
    p.add_argument("--lookback-days", type=int, required=True, help="How far back to backfill.")
    p.add_argument("--max-usd", type=float, default=5.0, help="HARD cost ceiling (default $5).")
    p.add_argument("--states", default="ALL", help="Comma list or ALL (default ALL).")
    p.add_argument("--branch", default=None, help="Output branch (default backfill-<N>d).")
    p.add_argument("--run-date", default=None, help="Run date (default today).")
    p.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _load_key("gemini_api.txt", "GEMINI_API_KEY")
    _load_key("kanoon_api.txt", "INDIANKANOON_API_TOKEN")
    if not os.environ.get("GEMINI_API_KEY"):
        print(
            "No GEMINI_API_KEY (set it or create gemini_api.txt) — cannot backfill.",
            file=sys.stderr,
        )
        return 2

    # Translate the hard USD cap into a per-run Gemini token cap (conservative: the higher
    # output rate). Extraction stops at the cap; the run stages what it has, loudly.
    token_cap = max(1, int(args.max_usd / config.GEMINI_OUTPUT_USD_PER_MTOK * 1_000_000))
    branch = args.branch or f"backfill-{args.lookback_days}d"

    print("BACKFILL PLAN")
    print(f"  states           : {args.states}")
    print(f"  lookback         : {args.lookback_days} days")
    print(f"  HARD cost cap    : ${args.max_usd:.2f}  (~{token_cap:,} Gemini tokens)")
    print(f"  output branch    : {branch}   (open a review PR — NEVER main)")
    print("  gates            : sanitize + identity_scan + pii_guard + graduated auto-publish")
    print(
        "  Indian Kanoon    : "
        + ("token set" if os.environ.get("INDIANKANOON_API_TOKEN") else "off")
    )
    if not args.yes and input("proceed? [y/N] ").strip().lower() != "y":
        print("aborted.")
        return 1

    env = {
        **os.environ,
        "LAUNCH_STATES": args.states,
        "LAUNCH_LOOKBACK_DAYS": str(args.lookback_days),
        "GEMINI_DAILY_TOKEN_CAP": str(token_cap),
        "VERIFY_ENABLED": "",  # verifier off for a bulk backfill (cost); discover gates still apply
        "LAUNCH_MODE": "staged",
    }
    subprocess.run(["git", "checkout", "-B", branch], cwd=_REPO, check=True)
    cmd = [sys.executable, "-m", "pipeline", "--mode", "discover"]
    if args.run_date:
        cmd += ["--run-date", args.run_date]
    result = subprocess.run(cmd, cwd=_REPO, env=env)
    if result.returncode != 0:
        print(
            f"\npipeline exited {result.returncode} — NOT committing. See logs/.", file=sys.stderr
        )
        return result.returncode

    summary = _REPO / "logs" / "run_summary.env"
    cost = "?"
    if summary.exists():
        for line in summary.read_text().splitlines():
            if line.startswith("COST="):
                cost = f"${float(line.split('=', 1)[1]):.4f}"
    subprocess.run(["git", "add", "data/"], cwd=_REPO, check=True)
    print(f"\nBackfill complete. Estimated spend this run: {cost} (cap ${args.max_usd:.2f}).")
    print("Review the data/ diff, then:")
    print(f"  git commit -m 'data: backfill {args.lookback_days}d'")
    print(f"  git push -u origin {branch} && gh pr create   # normal reviewed merge, never --admin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
