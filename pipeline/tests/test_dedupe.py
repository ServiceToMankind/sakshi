"""Synthetic stub test for case-anchored deduplication.

Fixtures are obviously fake (district "TESTVILLE", fake CNR). Marked ``xfail``
until ``pipeline.dedupe`` is implemented in the pipeline phase.
"""

from __future__ import annotations

from typing import Any

import pytest


def _synthetic_record(cnr: str, status: str) -> dict[str, Any]:
    return {
        "cnr": cnr,
        "state": "TG",
        "district": "TESTVILLE",
        "category": "sexual_assault",
        "status": status,
        "minor_involved": False,
        "sources": [
            {"url": "https://example.test/doc", "publisher": "eCourts", "retrieved": "2026-07-09"}
        ],
        "confidence": 0.95,
        "last_verified": "2026-07-09",
    }


@pytest.mark.xfail(reason="dedupe is implemented in the pipeline phase", strict=True)
def test_exact_cnr_dedup_merges_to_one() -> None:
    """Two records sharing a CNR collapse into a single deduped record."""
    from pipeline.dedupe import dedupe

    records = [
        _synthetic_record("TSHC01-000001-2026", "FIR_FILED"),
        _synthetic_record("TSHC01-000001-2026", "UNDER_TRIAL"),
    ]
    deduped, review = dedupe(records)
    assert len(deduped) == 1
    assert review == []
