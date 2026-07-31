#!/usr/bin/env python3
"""Secret guard — fail the run if a credential reached a TRACKED file.

.gitignore only covers filenames we can name; this is the durable, deterministic backstop
(same shape as pii_guard): it scans every git-TRACKED file for a live credential and exits
non-zero if one is found. Untracked local key files (e.g. an operator's pasted
``gemini_api.txt``) are intentionally NOT scanned — the point is to stop a secret from being
COMMITTED, not to police the working tree.

What it flags in a tracked file:
  1. A Google API key: ``AIza`` followed by 35 key characters.
  2. A ``GEMINI_API_KEY=`` (or INDIANKANOON token) assignment whose value looks like a real
     credential — long and non-placeholder. ``your-key-here`` / ``${VAR}`` / empty are fine.

The guard prints ``<file>:<line>: <reason>`` and returns 1 if any finding; 0 when clean. It
never prints the offending value.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
_ASSIGNMENT = re.compile(
    r"(?:GEMINI_API_KEY|INDIANKANOON_API_TOKEN|GOOGLE_API_KEY)\s*[:=]\s*"
    r"['\"]?(?P<value>[^\s'\"]+)",
    re.I,
)
# A value is a PLACEHOLDER (safe) if empty, a shell/CI variable reference, or it contains any
# of these obvious non-secret markers.
_PLACEHOLDER = re.compile(
    r"^\$|^\<|your[-_]|here|changeme|change[-_]me|example|placeholder|redacted|dummy|fake|"
    r"xxx|todo|none|null|test[-_]|sample",
    re.I,
)
# Files whose bytes are not worth scanning as text.
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".pdf"}


def _tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [Path(line) for line in out.splitlines() if line.strip()]


def _looks_like_secret_value(value: str) -> bool:
    """True if an assignment value looks like a real credential, not a placeholder."""
    if _PLACEHOLDER.search(value):
        return False
    return len(value) >= 20 and bool(re.fullmatch(r"[A-Za-z0-9_\-\.]+", value))


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_no, reason)`` for every credential-shaped hit in ``text``."""
    findings: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _GOOGLE_KEY.search(line):
            findings.append((line_no, "Google API key (AIza…) in a tracked file"))
        for match in _ASSIGNMENT.finditer(line):
            if _looks_like_secret_value(match.group("value")):
                findings.append((line_no, "API-key/token assignment with a real value"))
    return findings


def scan_tracked() -> list[str]:
    findings: list[str] = []
    for path in _tracked_files():
        if path.suffix.lower() in _SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, reason in scan_text(text):
            findings.append(f"{path}:{line_no}: {reason}")
    return findings


def main(argv: list[str] | None = None) -> int:
    findings = scan_tracked()
    for finding in findings:
        print(finding)
    if findings:
        print(f"\nsecret_guard: {len(findings)} credential(s) in tracked files.", file=sys.stderr)
        return 1
    print("Secret guard clean: no credentials in tracked files.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
