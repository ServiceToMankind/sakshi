"""Synthetic stub test for the sharded output writer.

Fixtures are obviously fake (district "TESTVILLE"). Marked ``xfail`` until
``pipeline.shard`` is implemented in the pipeline phase.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline.shard import SUMMARY_MAX_BYTES


def test_summary_budget_constant_is_50kb() -> None:
    """The summary-size budget asserted in CI is 50 KB."""
    assert SUMMARY_MAX_BYTES == 50 * 1024


def _synthetic_record() -> dict[str, Any]:
    return {
        "id": "SKS-2026-TG-000001",
        "state": "TG",
        "district": "TESTVILLE",
        "category": "sexual_assault",
        "status": "UNDER_TRIAL",
        "minor_involved": False,
        "sources": [
            {"url": "https://example.test/doc", "publisher": "eCourts", "retrieved": "2026-07-09"}
        ],
        "confidence": 0.95,
        "last_verified": "2026-07-09",
    }


@pytest.mark.xfail(reason="write_shards is implemented in the pipeline phase", strict=True)
def test_write_shards_emits_summary_and_index(tmp_path: Path) -> None:
    """A run writes summary.json and index.json alongside per-state shards."""
    from pipeline.shard import write_shards

    write_shards([_synthetic_record()], tmp_path)
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "index.json").exists()
    assert (tmp_path / "summary.json").stat().st_size < SUMMARY_MAX_BYTES
