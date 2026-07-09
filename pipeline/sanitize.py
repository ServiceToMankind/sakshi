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
    PII_VALUE_PATTERNS,
    is_forbidden_key,
    matched_value_patterns,
)

__all__ = ["REDACTION_PLACEHOLDER", "contains_pii", "sanitize_record", "sanitize_string"]

# Fixed marker left in free text where a PII-shaped span was removed. It must not
# itself match any PII value-pattern, so sanitisation stays idempotent.
REDACTION_PLACEHOLDER = "[redacted]"


def sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``record`` with all forbidden keys and PII values removed.

    Recurses through nested dicts and lists. Forbidden keys (see
    ``pii_constants.is_forbidden_key``) are dropped entirely; string values are
    passed through :func:`sanitize_string`. This is the last gate before disk and
    must reach 100% branch coverage.
    """
    cleaned: dict[str, Any] = {}
    for key, value in record.items():
        if is_forbidden_key(str(key)):
            # Drop the whole subtree — a forbidden key never survives.
            continue
        cleaned[key] = _sanitize_value(value)
    return cleaned


def _sanitize_value(value: Any) -> Any:
    """Recursively sanitise an arbitrary JSON value."""
    if isinstance(value, dict):
        return sanitize_record(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_string(value)
    return value


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
