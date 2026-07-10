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

# --- Age-expression patterns (issue #7) --------------------------------------
# A concrete age is a re-identifying detail. For a MINOR it is forbidden outright
# (POCSO s.23) and removed structurally by the minor-record projection in
# ``pipeline.sanitize``; for a NON-minor record these patterns are defence in
# depth: any record whose free text still matches after sanitisation is
# QUARANTINED to data/_review (never a public shard), and ``scripts.pii_guard``
# asserts no published shard contains one. Kept SEPARATE from PII_VALUE_PATTERNS
# because the policy differs: PII values are always redacted in place; ages route
# a whole record to human review instead.
AGE_EXPRESSION_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "numeric_years_old": re.compile(
        r"\b\d{1,2}\s*[-\u2013]?\s*(?:year|yr)s?[\s\-\u2013]*old\b", re.I
    ),
    "aged_number": re.compile(r"\bage[d]?\s+\d{1,2}\b", re.I),
    "descriptor_number": re.compile(
        r"\b(?:minor|girl|boy|child|student|victim|woman|man|male|female)\s+"
        r"(?:aged\s+)?\d{1,2}\b",
        re.I,
    ),
    "school_class": re.compile(r"\bclass\s+(?:[IVX]{1,4}|\d{1,2})\b", re.I),
    "ordinal_standard": re.compile(
        r"\b\d{1,2}(?:st|nd|rd|th)\s+(?:standard|std|grade|class)\b", re.I
    ),
    "teenager_word": re.compile(r"\b(?:teenage[rd]?|adolescent)\b", re.I),
    "spelled_years_old": re.compile(
        r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
        r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)[\s\-]"
        r"(?:year|yr)s?[\s\-\u2013]*old\b",
        re.I,
    ),
}

# The fixed neutral text substituted for a minor case's free-text summary. Defined
# here (the single source of truth) so both ``pipeline.sanitize`` (which writes it)
# and ``schemas/case.schema.json`` (which asserts it, via a test) cannot drift.
MINOR_SUMMARY_TEMPLATE: Final[str] = (
    "Case involving a minor. Details withheld under POCSO s.23. "
    "See cited sources and judicial status."
)

# Narrative free-text field name(s) — the only place model-written prose (and thus
# a stray age) can hide after projection. Age-expression scanning targets THESE,
# not structural/citation fields (url, id, publisher) whose slugs may legitimately
# carry numbers ("...-18-year-old-...") that are the source's wording, not our claim.
FREE_TEXT_FIELD_NAMES: Final[frozenset[str]] = frozenset({"summary"})


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


def matched_age_patterns(value: str) -> list[str]:
    """Return the names of every age-expression pattern that matches ``value``.

    Empty list means the string carries no detectable age/school-class detail.
    """
    return [name for name, pattern in AGE_EXPRESSION_PATTERNS.items() if pattern.search(value)]


def is_free_text_key(key: str) -> bool:
    """True if ``key`` names a narrative free-text field that should be age-scanned."""
    return key in FREE_TEXT_FIELD_NAMES
