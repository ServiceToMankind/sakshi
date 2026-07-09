#!/usr/bin/env python3
"""PII guardrail scanner -- the final assertion that no PII reaches disk or git.

DO NOT weaken without a human-approved issue. This CLI is a legally mandated
Phase 0 guardrail (BNS 2023 s.72; POCSO 2012 s.23). It imports its rules from
``pipeline.pii_constants`` -- the single source of truth shared with
``pipeline.sanitize`` -- so the sanitizer and this check can never drift apart.

What it flags:
  1. Any object KEY that equals a forbidden field name, or contains a forbidden
     substring ("victim"/"survivor"), case-insensitively.
  2. Any string VALUE matching a canonical PII value-pattern (Aadhaar, Indian
     mobile, email, PAN).

Usage:
    pii_guard.py [PATH ...]        Scan the given JSON files/dirs
                                   (default: all data/**/*.json).
    pii_guard.py --diff            Scan the STAGED git diff added-line text.

Exit code 0 means clean; non-zero means at least one finding was printed as
``<file>: <json-path>: <reason>``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

# Ensure the repo root is importable when run as a bare script (e.g. from a hook).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:  # pragma: no cover - import-time path shim
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline.pii_constants import (  # noqa: E402
    is_forbidden_key,
    matched_value_patterns,
)


class Finding:
    """A single guardrail violation, ready to print."""

    __slots__ = ("location", "path", "reason")

    def __init__(self, location: str, path: str, reason: str) -> None:
        self.location = location
        self.path = path
        self.reason = reason

    def __str__(self) -> str:
        return f"{self.location}: {self.path}: {self.reason}"


def _pattern_reason(pattern_name: str) -> str:
    """Human-readable reason string for a matched PII value-pattern."""
    return f"value matches {pattern_name} pattern"


def scan_value(value: Any, path: str) -> Iterator[Finding]:
    """Recursively yield findings for keys and string values under ``value``.

    ``path`` is a JSON-pointer-ish breadcrumb used for human-readable output.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if is_forbidden_key(str(key)):
                yield Finding(path or "<root>", child_path, f"forbidden field name '{key}'")
            yield from scan_value(child, child_path)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from scan_value(item, f"{path}[{idx}]")
    elif isinstance(value, str):
        loc = path or "<root>"
        for pattern_name in matched_value_patterns(value):
            yield Finding(loc, loc, _pattern_reason(pattern_name))


def scan_json_file(file_path: Path) -> list[Finding]:
    """Parse ``file_path`` as JSON and return every finding within it."""
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [Finding(str(file_path), "<file>", f"could not read/parse JSON: {exc}")]
    return [Finding(str(file_path), f.path, f.reason) for f in scan_value(data, "")]


def scan_diff_text(diff_text: str) -> list[Finding]:
    """Scan added lines of a unified git diff for PII value-patterns.

    Only string VALUES are checked here (added lines are raw text, not parsed
    JSON), which is enough to catch a PII value slipping into any staged file.
    """
    findings: list[Finding] = []
    line_no = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if not raw.startswith("+"):
            continue
        line_no += 1
        added = raw[1:]
        for pattern_name in matched_value_patterns(added):
            findings.append(
                Finding("<staged diff>", f"added-line {line_no}", _pattern_reason(pattern_name))
            )
    return findings


def iter_json_files(paths: Iterable[Path]) -> Iterator[Path]:
    """Yield every ``*.json`` file under the given files or directories."""
    for p in paths:
        if p.is_dir():
            yield from sorted(p.rglob("*.json"))
        elif p.suffix == ".json":
            yield p


def _staged_diff() -> str:
    """Return the staged git diff text (added/removed lines)."""
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
        check=False,
        cwd=_REPO_ROOT,
    )
    return result.stdout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pii_guard",
        description="Scan JSON data (or the staged git diff) for forbidden fields and PII values.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="JSON files or directories to scan (default: data/).",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Scan the staged git diff text instead of (or in addition to) files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the scan. Returns 0 when clean, 1 when any finding is reported."""
    args = build_parser().parse_args(argv)
    findings: list[Finding] = []

    if args.diff:
        findings.extend(scan_diff_text(_staged_diff()))

    if not args.diff or args.paths:
        scan_roots = args.paths if args.paths else [_REPO_ROOT / "data"]
        for json_file in iter_json_files(scan_roots):
            findings.extend(scan_json_file(json_file))

    if findings:
        print("PII guard FAILED -- guardrail violation(s) found:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    print("PII guard clean: no forbidden fields or PII-shaped values found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
