"""Coverage + trackability reporting (§3).

Two honest questions the accountability record must answer about ITSELF:

1. WHERE do we look? Every Indian state/UT is a declared block in ``sources.yml`` — a state
   with active sources is covered; a state with none is a DECLARED GAP (we know we do not
   cover it yet), not a silent blind spot. ``build_coverage`` turns that declaration plus the
   published corpus into ``data/coverage.json`` and the Coverage page.

2. Can the claim be RE-CHECKED? "Days without justice" is only honest if a case's status can
   actually be looked up again — i.e. it carries a queryable court anchor (a CNR, or a
   year-qualified FIR: station + number). The TRACKABILITY RATE is that fraction. It also
   prices court-record sourcing (Indian Kanoon) precisely: media-only records are not
   trackable.

Pure, non-identifying: counts and codes only. Non-protected.
"""

from __future__ import annotations

from typing import Any

from pipeline.dedupe import exact_anchor_keys
from pipeline.states import CANONICAL_STATES

__all__ = ["build_coverage", "is_court_anchored"]


def is_court_anchored(record: dict[str, Any]) -> bool:
    """True if the record carries a queryable court anchor (CNR or year-qualified FIR) whose
    status can be re-checked — the basis of the trackability rate."""
    return bool(exact_anchor_keys(record))


def build_coverage(
    source_configs: list[dict[str, Any]], records: list[dict[str, Any]], run_date: str
) -> dict[str, Any]:
    """Return the coverage.json payload from the (state-tagged) source configs + records."""
    # Active source count per state (national sources are counted separately).
    active_by_state: dict[str, int] = {}
    national_active = 0
    for cfg in source_configs:
        if not cfg.get("enabled"):
            continue
        state = str(cfg.get("state", "")).strip().upper()
        if state == "NATIONAL" or not state:
            national_active += 1
        else:
            active_by_state[state] = active_by_state.get(state, 0) + 1

    records_by_state: dict[str, int] = {}
    for record in records:
        state = str(record.get("state", "")).strip().upper()
        if state:
            records_by_state[state] = records_by_state.get(state, 0) + 1

    states: dict[str, dict[str, Any]] = {}
    for state in sorted(CANONICAL_STATES):
        active = active_by_state.get(state, 0)
        count = records_by_state.get(state, 0)
        states[state] = {
            "active_sources": active,
            "records": count,
            # A declared gap: a state the site explicitly does not source yet (no active
            # source AND no published record) — a KNOWN blind spot, not a silent one.
            "declared_gap": active == 0 and count == 0,
        }

    total = len(records)
    anchored = sum(1 for r in records if is_court_anchored(r))
    covered_states = sum(1 for s in states.values() if s["active_sources"] > 0 or s["records"] > 0)
    return {
        "generated": run_date,
        "trackability": {
            "total": total,
            "court_anchored": anchored,
            # Fraction of published records whose status can be re-checked via a court anchor.
            "rate": round(anchored / total, 4) if total else 0.0,
        },
        "states_covered": covered_states,
        "states_total": len(CANONICAL_STATES),
        "national_sources": national_active,
        "states": states,
    }
