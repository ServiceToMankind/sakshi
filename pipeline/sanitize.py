"""PII sanitizer: the LAST gate before any record touches disk.

DO NOT edit without a human-approved issue. This module enforces a legally
mandatory Phase 0 obligation (BNS 2023 s.72; POCSO 2012 s.23): victim identity
and any re-identifying detail must NEVER be written to disk, logged, cached, or
committed.

Design contract:
- ``sanitize_record`` is invoked on every candidate record immediately before it
  is handed to validation/sharding. It recurses through the whole structure,
  DROPS any object key that is forbidden (``pii_constants.is_forbidden_key``),
  and scrubs any string VALUE that matches a ``PII_VALUE_PATTERN``.
- It is deliberately conservative: when in doubt, strip. Because this is the
  final safety gate, the test suite must reach 100% BRANCH coverage here.
- Sanitization is idempotent: ``sanitize_record(sanitize_record(x)) ==
  sanitize_record(x)``.

The single source of truth for what counts as PII is ``pipeline.pii_constants``;
this module must never hard-code its own copy of the forbidden lists.
"""

from __future__ import annotations

from typing import Any

from pipeline.pii_constants import (
    MINOR_SUMMARY_TEMPLATE,
    PII_VALUE_PATTERNS,
    is_forbidden_key,
    matched_value_patterns,
)

__all__ = [
    "MINOR_SUMMARY_TEMPLATE",
    "REDACTION_PLACEHOLDER",
    "contains_pii",
    "project_minor_record",
    "sanitize_record",
    "sanitize_string",
]

# Fixed marker left in free text where a PII-shaped span was removed. It must not
# itself match any PII value-pattern, so sanitisation stays idempotent.
REDACTION_PLACEHOLDER = "[redacted]"


def sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``record`` scrubbed of PII and Phase-0-projected.

    Two things happen, in order, as the last gate before disk:

    1. Forbidden keys (see ``pii_constants.is_forbidden_key``) are dropped and
       every string value is passed through :func:`sanitize_string`, recursively.
    2. If ``minor_involved is True`` the record is passed through
       :func:`project_minor_record`, which STRUCTURALLY replaces the model-written
       narrative and any day/age-precise field with the fixed Phase 0 allowance —
       no regex completeness or model compliance required for the protection.

    Must reach 100% branch coverage.
    """
    cleaned = _scrub_mapping(record)
    if cleaned.get("minor_involved") is True:
        cleaned = project_minor_record(cleaned)
    return cleaned


def _scrub_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Drop forbidden keys and sanitise every value in a mapping (recursive)."""
    cleaned: dict[str, Any] = {}
    for key, value in mapping.items():
        if is_forbidden_key(str(key)):
            # Drop the whole subtree — a forbidden key never survives.
            continue
        cleaned[key] = _sanitize_value(value)
    return cleaned


def _sanitize_value(value: Any) -> Any:
    """Recursively sanitise an arbitrary JSON value (scrub only; no projection)."""
    if isinstance(value, dict):
        return _scrub_mapping(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_string(value)
    return value


def project_minor_record(record: dict[str, Any]) -> dict[str, Any]:
    """Enforce the Phase 0 field allowance for a minor case, deterministically.

    POCSO s.23 permits only state, district, year, offence category, and judicial
    status for a minor. So the model-written ``summary`` is replaced with a fixed
    neutral template, ``incident_reported_date`` is truncated to the year,
    ``pending_days`` (a day-precise derivation) is nulled, ``court.next_hearing``
    is nulled, and each ``status_history`` date is truncated to the month. This is
    structural: it does not depend on the age-expression regexes catching anything.
    Idempotent — applying it twice yields the same record.
    """
    projected = dict(record)
    projected["summary"] = MINOR_SUMMARY_TEMPLATE
    reported = projected.get("incident_reported_date")
    if isinstance(reported, str) and reported:
        projected["incident_reported_date"] = reported[:4]  # year granularity only
    if "pending_days" in projected:
        projected["pending_days"] = None  # cannot be derived from a year; never stored
    court = projected.get("court")
    if isinstance(court, dict) and "next_hearing" in court:
        projected["court"] = {**court, "next_hearing": None}
    history = projected.get("status_history")
    if isinstance(history, list):
        projected["status_history"] = [_project_history_entry(entry) for entry in history]
    return projected


def _project_history_entry(entry: Any) -> Any:
    """Truncate a status_history entry's date to YYYY-MM (day precision is not stored)."""
    if isinstance(entry, dict) and isinstance(entry.get("date"), str) and entry["date"]:
        return {**entry, "date": entry["date"][:7]}
    return entry


def sanitize_string(s: str) -> str:
    """Return ``s`` with any substring matching a PII value-pattern redacted.

    Redaction (rather than raising) is used for free-text fields such as
    ``summary`` where a stray match must be neutralised without discarding the
    surrounding neutral prose. Idempotent: the placeholder matches no pattern.
    """
    result = s
    for pattern in PII_VALUE_PATTERNS.values():
        result = pattern.sub(REDACTION_PLACEHOLDER, result)
    return result


def contains_pii(value: object) -> bool:
    """Return True if ``value`` (a key name or a string value) looks like PII.

    Used as a fast assertion helper: forbidden field names and string values
    matching any :data:`pipeline.pii_constants.PII_VALUE_PATTERNS` both count.
    Non-string inputs are considered clean.
    """
    if isinstance(value, str):
        return is_forbidden_key(value) or bool(matched_value_patterns(value))
    return False
