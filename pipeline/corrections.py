"""Human-authored corrections over pipeline output (``corrections/<record-id>.yml``).

``data/`` is pipeline-generated and never hand-edited, but some fixes are impossible for
the pipeline to make on its own — a pre-existing over-merge it cannot re-split, a legalese
summary whose source article has rolled off the feed and cannot be re-extracted. Corrections
are the reviewed, committed, human-authored escape hatch for exactly those cases, keyed by
record id and recording who/when/why + the evidence relied on, so every correction is
auditable in git.

A correction can do two things:

- ``quarantine: true`` — route the record OUT of the published site into ``_review``
  (used when a record should not be live at all, e.g. an unresolved over-merge).
- ``overrides: {field: value}`` — narrow or fix specific fields. Overrides are applied
  AFTER extraction and BEFORE the final sanitize, so a corrected value still passes every
  gate (``sanitize`` strips PII, the schema validates the shape, ``pii_guard`` backstops).
  A corrected record is marked ``corrected: true`` so the site can show it was reviewed.

Non-protected, and structurally incapable of weakening a guardrail: an override targeting a
forbidden PII field name, ``id``, or ``minor_involved`` is DROPPED before it is applied (it
can never smuggle victim data past sanitize or flip the minor projection), and whatever
survives is re-sanitised by the caller regardless.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pipeline import config
from pipeline.pii_constants import FORBIDDEN_FIELD_NAMES, FORBIDDEN_SUBSTRINGS

__all__ = [
    "CORRECTIONS_DIR",
    "apply_correction",
    "load_corrections",
    "override_is_allowed",
    "quarantined_ids",
]

CORRECTIONS_DIR = config.REPO_ROOT / "corrections"

# Top-level keys a correction may NEVER set: the id (identity anchor — reassigning it would
# fuse/split cases) and minor_involved (flipping it would bypass the POCSO s.23 projection).
_PROTECTED_OVERRIDE_KEYS = frozenset({"id", "minor_involved"})


def override_is_allowed(key: str) -> bool:
    """False if a correction must NOT be allowed to override this field: a forbidden PII
    field name, a name containing 'victim'/'survivor', or an identity/projection anchor."""
    low = key.lower()
    if low in _PROTECTED_OVERRIDE_KEYS or low in FORBIDDEN_FIELD_NAMES:
        return False
    return not any(sub in low for sub in FORBIDDEN_SUBSTRINGS)


def load_corrections(directory: Path = CORRECTIONS_DIR) -> dict[str, dict[str, Any]]:
    """Load every ``corrections/*.yml`` keyed by its ``record_id`` (empty if none/unreadable)."""
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


def _safe_overrides(correction: dict[str, Any]) -> dict[str, Any]:
    """The correction's overrides with any forbidden/identity-anchor key removed."""
    overrides = correction.get("overrides")
    if not isinstance(overrides, dict):
        return {}
    return {k: v for k, v in overrides.items() if isinstance(k, str) and override_is_allowed(k)}


def apply_correction(
    record: dict[str, Any], corrections: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Apply a matching correction's field OVERRIDES to ``record`` and mark it ``corrected``.

    Returns a NEW dict (or ``record`` unchanged if no correction with overrides matches its
    id). Quarantine is handled separately (see :func:`quarantined_ids`). Overrides targeting
    a forbidden/identity field are dropped; the CALLER must re-sanitise the result so an
    override can never bypass the PII gate or the schema.
    """
    corr = corrections.get(str(record.get("id", "")))
    if not corr:
        return record
    overrides = _safe_overrides(corr)
    if not overrides:
        return record
    return {**record, **overrides, "corrected": True}
