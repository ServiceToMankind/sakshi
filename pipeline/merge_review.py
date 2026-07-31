"""National-scale candidate-match detection for a HUMAN merge-review queue (§8).

The auto-merge in :mod:`pipeline.dedupe` only fuses records that share an EXACT anchor
(CNR / year-qualified FIR) or a day-precise date plus a corroborator — deliberately strict,
because over-merging undercounts (SKS-2026-DL-000003 fused many distinct proceedings). That
strictness leaves a gap: two records that are probably the same case but never shared an
exact anchor (e.g. two outlets, no CNR) stay separate.

This module closes the gap WITHOUT auto-merging: it scans the published corpus for candidate
pairs — same state, district, and category; incident date within +-3 days (day-precise on
both, so year-only minor projections never match here); and an overlapping accused name or
offence section — and clusters them into a review queue a HUMAN decides on. Nothing is merged
or removed; no record is missed. Non-protected, pure over already-published, non-identifying
fields (accused NAMES appear only from court records — the existing §5 rule).
"""

from __future__ import annotations

from typing import Any

from pipeline.dedupe import FUZZY_DATE_WINDOW_DAYS, _parse_date, exact_anchor_keys

__all__ = ["find_candidate_matches"]


def _accused_names(record: dict[str, Any]) -> set[str]:
    """Court-recorded accused names on a record (lower-cased), if any."""
    names: set[str] = set()
    for accused in record.get("accused") or []:
        name = str(accused.get("name_public_court_record") or "").strip().lower()
        if name:
            names.add(name)
    return names


def _sections(record: dict[str, Any]) -> set[str]:
    return {str(s).strip().lower() for s in record.get("offence_sections") or [] if str(s).strip()}


def _is_candidate_pair(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    """Return the shared signals if ``a`` and ``b`` are a merge-review candidate, else None."""
    if exact_anchor_keys(a) & exact_anchor_keys(b):
        return None  # already the same case by exact anchor (dedupe would have merged them)
    for field in ("state", "district", "category"):
        va = str(a.get(field, "")).strip().lower()
        vb = str(b.get(field, "")).strip().lower()
        if not va or va != vb:
            return None
    date_a = _parse_date(a.get("incident_reported_date"))
    date_b = _parse_date(b.get("incident_reported_date"))
    if not (date_a and date_b) or abs((date_a - date_b).days) > FUZZY_DATE_WINDOW_DAYS:
        return None  # not day-precise on both, or outside the window (excludes year-only minors)
    shared_accused = _accused_names(a) & _accused_names(b)
    shared_sections = _sections(a) & _sections(b)
    if not shared_accused and not shared_sections:
        return None
    return {
        "shared_accused": sorted(shared_accused),
        "shared_sections": sorted(shared_sections),
        "days_apart": abs((date_a - date_b).days),
    }


def find_candidate_matches(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return merge-review candidate clusters over ``records`` (published set).

    Each cluster is ``{"ids": [...], "state", "district", "category", "signals": [...]}`` where
    the ids MIGHT be the same case and a human must decide. Never merges; order-stable.
    """
    indexed = [(i, r) for i, r in enumerate(records) if str(r.get("id", ""))]
    parent = list(range(len(indexed)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pair_signals: dict[tuple[int, int], dict[str, Any]] = {}
    for ai in range(len(indexed)):
        for bi in range(ai + 1, len(indexed)):
            signals = _is_candidate_pair(indexed[ai][1], indexed[bi][1])
            if signals is not None:
                pair_signals[(ai, bi)] = signals
                parent[find(bi)] = find(ai)

    clusters: dict[int, list[int]] = {}
    for idx in range(len(indexed)):
        if any(idx in pair for pair in pair_signals):
            clusters.setdefault(find(idx), []).append(idx)

    out: list[dict[str, Any]] = []
    for members in clusters.values():
        members.sort()
        first = indexed[members[0]][1]
        cluster_signals = [
            {"ids": sorted((str(indexed[ai][1]["id"]), str(indexed[bi][1]["id"]))), **sig}
            for (ai, bi), sig in pair_signals.items()
            if ai in members and bi in members
        ]
        out.append(
            {
                "ids": sorted(str(indexed[m][1]["id"]) for m in members),
                "state": first.get("state"),
                "district": first.get("district"),
                "category": first.get("category"),
                "signals": sorted(cluster_signals, key=lambda s: s["ids"]),
            }
        )
    return sorted(out, key=lambda c: c["ids"])
