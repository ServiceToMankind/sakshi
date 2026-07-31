"""Human-authored corrections over pipeline output (``corrections/<record-id>.yml``).

``data/`` is pipeline-generated and never hand-edited, but some fixes are impossible for the
pipeline to make on its own — a pre-existing over-merge it cannot re-split, a legalese summary
whose source article has rolled off the feed and cannot be re-extracted. Corrections are the
reviewed, committed, human-authored escape hatch for exactly those cases.

This is the FIRST slice — QUARANTINE only: a correction with ``quarantine: true`` routes its
record out of the published site into ``_review``. Field-level overrides (applied after
extraction, before sanitize, so they still pass every gate) land with the fuller mechanism.

Each file is keyed by record id and records who/when/why + the evidence relied on, so a
correction is auditable. Non-protected; it can only REMOVE a record or (later) narrow a field,
never smuggle content past sanitize/pii_guard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pipeline import config

__all__ = ["CORRECTIONS_DIR", "load_corrections", "quarantined_ids"]

CORRECTIONS_DIR = config.REPO_ROOT / "corrections"


def load_corrections(directory: Path = CORRECTIONS_DIR) -> dict[str, dict[str, Any]]:
    """Load every ``corrections/*.yml`` keyed by its ``record_id`` (empty if none)."""
    out: dict[str, dict[str, Any]] = {}
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and data.get("record_id"):
            out[str(data["record_id"])] = data
    return out


def quarantined_ids(corrections: dict[str, dict[str, Any]]) -> set[str]:
    """Ids a correction marks ``quarantine: true`` — held out of the published site."""
    return {rid for rid, c in corrections.items() if c.get("quarantine") is True}
