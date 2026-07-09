"""Single source of truth for PII guardrail constants.

DO NOT edit without a human-approved issue. These constants encode a legally
mandatory Phase 0 obligation and are imported by BOTH ``pipeline.sanitize`` (the
last gate before disk) and ``scripts.pii_guard`` (the final CI assertion). Any
divergence between the two consumers would create a hole in the guarantee that
victim identity is never written to disk, logged, cached, or committed.

Legal basis:
- Section 72, Bharatiya Nyaya Sanhita 2023 (formerly IPC 228A): criminalizes
  disclosing the identity of victims of sexual offences.
- Section 23, POCSO Act 2012: same for minors, extending to ANY identifying
  detail.

The lists below are reproduced EXACTLY from the canonical project specification.
Keep them identical everywhere they are referenced.
"""

from __future__ import annotations

import re
from typing import Final

# --- Forbidden object-key names (case-insensitive match) ---------------------
# Reproduced exactly from the canonical spec. If a key equals any of these names
# (compared case-insensitively) the record is rejected/stripped.
FORBIDDEN_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "victim",
        "victim_name",
        "victim_age",
        "victim_address",
        "survivor",
        "survivor_name",
        "complainant_name",
        "accused_victim_relation",
        "address",
        "home_address",
        "family",
        "family_members",
        "father_name",
        "mother_name",
        "guardian",
        "guardian_name",
        "relative",
        "school",
        "school_name",
        "college",
        "workplace",
        "employer",
        "employer_name",
        "photo",
        "photograph",
        "image",
        "image_url",
        "phone",
        "mobile",
        "contact",
        "contact_number",
        "email",
        "aadhaar",
        "aadhar",
        "pan",
        "dob",
        "date_of_birth",
        "birth_date",
        "latitude",
        "longitude",
        "gps",
        "geo",
        "coordinates",
    }
)

# Any key that merely CONTAINS one of these substrings (case-insensitive) is also
# forbidden -- catches variants like "primary_victim", "survivor_notes", etc.
FORBIDDEN_SUBSTRINGS: Final[frozenset[str]] = frozenset({"victim", "survivor"})

# --- Forbidden string VALUE patterns -----------------------------------------
# Compiled from the canonical PII value-regex list. sanitize + pii_guard scan
# every string value against these, regardless of the key it sits under.
PII_VALUE_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "indian_mobile": re.compile(r"\b(?:\+?91[\-\s]?)?[6-9]\d{9}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
}


def is_forbidden_key(key: str) -> bool:
    """Return True if ``key`` is a forbidden field name or contains a forbidden substring.

    Matching is case-insensitive, exactly as the guardrail specification requires.
    """
    lowered = key.lower()
    if lowered in FORBIDDEN_FIELD_NAMES:
        return True
    return any(sub in lowered for sub in FORBIDDEN_SUBSTRINGS)


def matched_value_patterns(value: str) -> list[str]:
    """Return the names of every PII value-pattern that matches ``value``.

    Empty list means the string is clean.
    """
    return [name for name, pattern in PII_VALUE_PATTERNS.items() if pattern.search(value)]
