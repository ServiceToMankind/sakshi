"""Month-to-date Gemini spend ledger (``data/_meta/spend.json``).

A cumulative USD total per calendar month, persisted in the committed-but-NOT-deployed
``_meta`` tree so the monthly budget cap (``config.monthly_max_usd``) survives across the
many runs in a month. This is aggregate cost accounting ONLY: it stores month keys and
dollar totals, never any case content, source text, URL, or PII — nothing here can carry
a victim detail, so it is guardrail-inert.

The enforcement lives in ``__main__.run``: a run reads the current month's total BEFORE
extracting and, if it already meets the cap, makes no new paid calls and flags the ops
issue; after extracting (+ verifying) it folds this run's estimate back in.
"""

from __future__ import annotations

import json
from pathlib import Path

SPEND_RELPATH = Path("_meta") / "spend.json"


def _month_of(run_date: str) -> str:
    """The ``YYYY-MM`` bucket for an ISO ``YYYY-MM-DD`` run date."""
    return str(run_date)[:7]


def load_spend(data_dir: Path) -> dict[str, float]:
    """Return the ``{month: usd}`` ledger, or ``{}`` if absent/unreadable."""
    path = data_dir / SPEND_RELPATH
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    months = raw.get("months", {}) if isinstance(raw, dict) else {}
    return {str(k): float(v) for k, v in months.items()}


def month_to_date(data_dir: Path, run_date: str) -> float:
    """USD already spent in ``run_date``'s calendar month (0.0 if none)."""
    return load_spend(data_dir).get(_month_of(run_date), 0.0)


def record_spend(data_dir: Path, run_date: str, usd: float) -> float:
    """Add ``usd`` to the run-date month's running total and persist. Returns the new
    month-to-date. A non-positive delta is a no-op add (still returns the current total),
    so a zero-cost run (e.g. one that hit the cap and skipped extraction) is idempotent.
    """
    months = load_spend(data_dir)
    month = _month_of(run_date)
    months[month] = round(months.get(month, 0.0) + max(0.0, float(usd)), 6)
    path = data_dir / SPEND_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"months": dict(sorted(months.items()))}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return months[month]
