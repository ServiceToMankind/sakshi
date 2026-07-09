"""Sharded output writer (STUB).

Regenerates the whole ``data/`` tree idempotently each run so re-runs are safe;
humans NEVER hand-edit ``data/``. Writes are atomic (temp -> validate -> rename).

Outputs:
- ``data/{YYYY}/{STATE}.json``: full records sorted by date desc. A shard over
  500 KB auto-splits into ``{STATE}-p2.json``, recorded in the manifest.
- ``data/summary.json``: totals, status_counts, state_counts, 24-month trend,
  top-10 longest-pending (id + district + days only), generated_at. MUST stay
  < 50 KB (asserted in CI).
- ``data/index.json``: manifest of available shards with record counts and byte
  sizes so the frontend never 404-guesses.

``scripts/pii_guard`` runs as the final assertion after this stage.

Full implementation lands in the pipeline phase.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["write_shards"]

SUMMARY_MAX_BYTES: int = 50 * 1024
SHARD_SPLIT_BYTES: int = 500 * 1024


def write_shards(records: list[dict[str, Any]], data_dir: Path) -> None:
    """Write the full ``data/`` tree from ``records`` atomically and idempotently.

    Validates every record, assigns deterministic IDs, writes per-year/state
    shards (splitting any shard over ``SHARD_SPLIT_BYTES``), then regenerates
    ``summary.json`` (asserted < ``SUMMARY_MAX_BYTES``) and ``index.json``.

    TODO(pipeline-phase): implement temp->validate->rename atomic writes and the
    summary/index regeneration.
    """
    raise NotImplementedError("write_shards is implemented in the pipeline phase")
