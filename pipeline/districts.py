"""Deterministic district-name canonicalisation (§6 composer fix).

Public sources name the same district many ways — the pre-rename name ("Gurgaon"),
an administrative label that is not the common name ("South District" for the Delhi
district commonly written "South Delhi"), or stray whitespace/casing. A record's
`district` is user-facing (titles, summaries, scorecards) and is a **dedupe anchor**,
so two spellings of one district would both mislead a reader and split a case across
two rows. This module maps known aliases to one canonical spelling.

It is a CONSERVATIVE, EXPLICIT alias table — never a fuzzy matcher: an unknown value
passes through unchanged (only its surrounding whitespace is trimmed), so it can never
invent or mis-map a district. District is a locality, never victim identity — this adds
no PII and removes none of the guardrail floor (district stays the finest locality ever
stored). Non-protected: pure string normalisation, no PII detection.
"""

from __future__ import annotations

__all__ = ["ALIASES", "canonical_district"]

# alias (lower-cased, whitespace-collapsed) -> canonical spelling. Every entry is a
# well-established rename or a common-name mapping; extend only with a citable rename.
ALIASES: dict[str, str] = {
    # Official renames.
    "gurgaon": "Gurugram",
    "bangalore": "Bengaluru",
    "allahabad": "Prayagraj",
    "gauhati": "Guwahati",
    "calcutta": "Kolkata",
    "bombay": "Mumbai",
    "madras": "Chennai",
    "mysore": "Mysuru",
    "belgaum": "Belagavi",
    "gulbarga": "Kalaburagi",
    "mangalore": "Mangaluru",
    "pondicherry": "Puducherry",
    "poona": "Pune",
    # Administrative label -> common name (same Delhi district).
    "south district": "South Delhi",
    "new delhi district": "New Delhi",
}


def canonical_district(name: object) -> str:
    """Return the canonical spelling of a district name.

    Trims and space-collapses the input, then maps a known alias (case-insensitively) to
    its canonical form; an unknown value is returned trimmed/space-collapsed but otherwise
    unchanged. A non-string or empty input yields "".
    """
    if not isinstance(name, str):
        return ""
    collapsed = " ".join(name.split())
    if not collapsed:
        return ""
    return ALIASES.get(collapsed.lower(), collapsed)
