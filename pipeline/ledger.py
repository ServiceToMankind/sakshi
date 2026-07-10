"""Processed-document ledger — turns provider degradation into delay, not loss.

A committed record of which source documents have already been SETTLED, so a run
that truncates under a slow provider spends its next budget on the backlog TAIL
instead of re-processing the same head of the queue every time.

Privacy: the ledger stores only a URL HASH (as the object key) plus outcome +
dates — never the URL itself, never any PII. It lives under ``data/`` so
``scripts/pii_guard`` scans it like everything else. The URL of a newly
``failed_permanent`` document is written to the (ephemeral, uncommitted) run log
for manual review, not to the committed ledger.

Outcomes:
  - ``published`` / ``out_of_scope`` / ``not_a_case`` : SETTLED — a successful
    extraction call classified the document; re-processing it would only repeat the
    result, so it is skipped from now on.
  - ``out_of_window`` : the document IS a sexual-offence case but falls outside the
    current launch window (LAUNCH_STATES / LAUNCH_LOOKBACK_DAYS). Terminal for
    coverage accounting, and skipped — but ONLY meaningful under a FIXED window.
    **If you widen LAUNCH_STATES or LAUNCH_LOOKBACK_DAYS, delete
    data/_meta/processed.json so these documents are re-examined.**
  - ``failed`` : the extraction call errored (provider). Retried on later runs up
    to :data:`config.EXTRACT_MAX_DOC_ATTEMPTS` times.
  - ``failed_permanent`` : exhausted its retries. Skipped; its URL is logged once.

A document quarantined to the review queue is NEVER settled here (it has no ledger
entry), so it re-surfaces every run until a human resolves it — "delay, not loss".
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline import config

__all__ = ["LEDGER_RELPATH", "Ledger", "load_ledger", "save_ledger"]

LEDGER_RELPATH = Path("_meta") / "processed.json"

_SETTLED = frozenset({"published", "rejected", "out_of_scope", "not_a_case", "out_of_window"})


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class Ledger:
    """The processed-document ledger. Keys are URL hashes; values carry outcome."""

    def __init__(self, documents: dict[str, dict[str, Any]] | None = None) -> None:
        self._docs: dict[str, dict[str, Any]] = documents or {}

    def should_process(self, url: str) -> bool:
        """True if ``url`` is new, or failed but still within its retry budget."""
        entry = self._docs.get(_hash(url))
        if entry is None:
            return True
        if entry.get("outcome") == "failed":
            return int(entry.get("attempts", 0)) < config.EXTRACT_MAX_DOC_ATTEMPTS
        return False  # settled or failed_permanent

    def record(self, url: str, outcome: str, run_date: str) -> str:
        """Record ``outcome`` for ``url``. Returns the resulting stored outcome.

        A ``failed`` outcome increments the attempt count and becomes
        ``failed_permanent`` once the retry budget is exhausted.
        """
        key = _hash(url)
        entry = self._docs.get(key) or {"first_seen": run_date, "attempts": 0}
        entry["last_seen"] = run_date
        if outcome == "failed":
            entry["attempts"] = int(entry.get("attempts", 0)) + 1
            resolved = (
                "failed_permanent"
                if entry["attempts"] >= config.EXTRACT_MAX_DOC_ATTEMPTS
                else "failed"
            )
        else:
            resolved = outcome
        entry["outcome"] = resolved
        self._docs[key] = entry
        return resolved

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, "documents": self._docs}

    @property
    def settled_count(self) -> int:
        return sum(1 for e in self._docs.values() if e.get("outcome") in _SETTLED)


def load_ledger(data_dir: Path) -> Ledger:
    """Load the ledger from ``data_dir/_meta/processed.json`` (empty if absent/bad)."""
    path = data_dir / LEDGER_RELPATH
    if not path.exists():
        return Ledger()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Ledger()
    documents = data.get("documents", {}) if isinstance(data, dict) else {}
    return Ledger(documents if isinstance(documents, dict) else {})


def save_ledger(data_dir: Path, ledger: Ledger) -> None:
    """Write the ledger atomically under ``data_dir/_meta/processed.json``."""
    path = data_dir / LEDGER_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
