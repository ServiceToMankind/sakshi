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

# Deterministic title/summary for a MINOR case are built ONLY from these allowed,
# non-identifying fields (POCSO s.23) — the model never writes a minor's title or
# summary. Presentation labels; not PII.
_CATEGORY_LABEL = {
    "rape": "Rape",
    "pocso": "Child sexual offence",
    "sexual_assault": "Sexual assault",
    "acid_attack": "Acid attack",
    "harassment": "Sexual harassment",
    "other": "Sexual offence",
}
_STATUS_PHRASE = {
    "FIR_FILED": "An FIR has been filed",
    "CHARGESHEETED": "A chargesheet has been filed",
    "UNDER_TRIAL": "The case is under trial",
    "CONVICTED": "The accused was convicted",
    "ACQUITTED": "The accused was acquitted",
    "APPEAL_PENDING": "An appeal is pending",
    "CLOSED": "The case is closed",
    "QUASHED": "The case was quashed",
    "UNKNOWN": "The case status is not yet known",
}
# One human sentence: the gap is legal compliance, not missing data.
MINOR_WITHHELD_SENTENCE = "Identifying details are withheld by law (POCSO s.23)."


def _case_year(record: dict[str, Any]) -> str:
    reported = str(record.get("incident_reported_date", ""))
    return reported[:4] if len(reported) >= 4 and reported[:4].isdigit() else ""


def _category_label(record: dict[str, Any]) -> str:
    return _CATEGORY_LABEL.get(str(record.get("category", "")).lower(), "Sexual offence")


def minor_title(record: dict[str, Any]) -> str:
    """Deterministic, non-identifying title for a minor case (allowed fields only)."""
    year = _case_year(record)
    where = str(record.get("district") or record.get("state") or "").strip()
    parts = [f"{_category_label(record)} case involving a minor"]
    if where:
        parts.append(f"— {where}")
    if year:
        parts.append(f"({year})")
    return " ".join(parts)[:90]


def minor_summary(record: dict[str, Any]) -> str:
    """Deterministic, non-identifying summary for a minor case (allowed fields only)."""
    year = _case_year(record)
    location = ", ".join(
        part
        for part in (str(record.get("district", "")).strip(), str(record.get("state", "")).strip())
        if part
    )
    phrase = _STATUS_PHRASE.get(str(record.get("status", "")).upper(), _STATUS_PHRASE["UNKNOWN"])
    where = f" in {location}" if location else ""
    reported = f" Reported {year}." if year else ""
    return f"{phrase}{where}.{reported} {MINOR_WITHHELD_SENTENCE}"


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
        cleaned = project_minor_record(cleaned)  # sets title + summary deterministically
    elif not str(cleaned.get("title", "")).strip():
        # Non-minor with no model title (older record / model omission): deterministic
        # fallback so the required `title` is always present. Non-identifying.
        cleaned["title"] = _nonminor_title(cleaned)
    return cleaned


def _nonminor_title(record: dict[str, Any]) -> str:
    """Deterministic fallback title for a non-minor record lacking a model title."""
    year = _case_year(record)
    where = str(record.get("district") or record.get("state") or "").strip()
    parts = [f"{_category_label(record)} case"]
    if where:
        parts.append(f"— {where}")
    if year:
        parts.append(f"({year})")
    return " ".join(parts)[:90]


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
    is nulled, each ``status_history`` date is truncated to the month, and any
    model-written ``verification_note`` (guardrail L free text — not age-scanned by
    pii_guard) is dropped. This is structural: it does not depend on the age-expression
    regexes catching anything. Idempotent — applying it twice yields the same record.
    """
    projected = dict(record)
    # Title AND summary are generated DETERMINISTICALLY from allowed non-identifying
    # fields — the model never writes a minor's title or summary (POCSO s.23).
    projected["title"] = minor_title(projected)
    projected["summary"] = minor_summary(projected)
    # The verifier's model-written note is free text the minor projection does not
    # otherwise neutralise and pii_guard does not age-scan — a minor's content is never
    # model-written, so drop it (canonical home for the guard; issue #44).
    projected.pop("verification_note", None)
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
