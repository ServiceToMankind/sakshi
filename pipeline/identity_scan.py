"""Deterministic identity-detail backstop for NON-MINOR model-written free text.

The accountability layer lets a non-minor ``summary`` state the act / district /
institutional response, and the extraction prompt forbids victim identity — but that
is an LLM instruction, not a gate. This module is the DETERMINISTIC backstop: it
quarantines a record to ``_review`` when its model-written free text (``title``,
``summary``, ``offence_sections``) reveals a **victim-accused relationship** (the
sharpest re-identification vector, especially intra-familial — ``accused_victim_relation``
is a forbidden field) or an **age**, regardless of what the model produced.

Scope note: occupation and sub-district-in-prose ("a nurse", "at the college hostel")
are NOT scanned here — a lexicon for them is too noisy (they legitimately describe the
accused / institutional response) and would over-quarantine every adult case. Those stay
prompt- and verifier-guarded; relationship + age are low-false-positive and high-signal.
Minor records are skipped: their title/summary are the deterministic projection and carry
no model narrative or accused.
"""

from __future__ import annotations

import re
from typing import Any

from pipeline.pii_constants import matched_age_patterns

__all__ = ["has_identity_detail", "matched_relationship_terms"]

# Victim-accused relationship terms. Stating or implying the relationship is forbidden
# (it re-identifies the victim by proximity to a named/knowable accused). In a sexual-
# offence summary these words almost always denote that relationship; the rare false
# positive (a witness) only over-quarantines to human review, which is safe.
_RELATIONSHIP_TERMS = (
    "husband",
    "wife",
    "spouse",
    "father",
    "mother",
    "brother",
    "sister",
    "son",
    "daughter",
    "uncle",
    "aunt",
    "cousin",
    "nephew",
    "niece",
    "grandfather",
    "grandmother",
    "grandson",
    "granddaughter",
    "in-law",
    "in-laws",
    "father-in-law",
    "mother-in-law",
    "brother-in-law",
    "sister-in-law",
    "son-in-law",
    "daughter-in-law",
    "stepfather",
    "stepmother",
    "stepson",
    "stepdaughter",
    "step-father",
    "step-mother",
    "guardian",
    "relative",
    "neighbour",
    "neighbor",
    "boyfriend",
    "girlfriend",
    "fiance",
    "fiancee",
    "fiancé",
    "fiancée",
    "partner",
)
_RELATIONSHIP_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in _RELATIONSHIP_TERMS) + r")\b",
    re.IGNORECASE,
)

# Model-written free-text fields on a NON-MINOR record.
_SCANNED_TEXT_FIELDS = ("title", "summary")


def matched_relationship_terms(value: str) -> list[str]:
    """Relationship terms found in ``value`` (empty if none / non-string)."""
    return _RELATIONSHIP_RE.findall(value) if isinstance(value, str) else []


def has_identity_detail(record: dict[str, Any]) -> bool:
    """True if a NON-MINOR record's model-written free text reveals a victim-accused
    relationship, or an age (in title, summary, or an offence-section string).

    Minors return False here: their title/summary are the deterministic projection and
    they carry no accused, so this scan targets the non-minor narrative surface the
    accountability layer widened.
    """
    if record.get("minor_involved"):
        return False
    texts: list[str] = [
        value for field in _SCANNED_TEXT_FIELDS if isinstance((value := record.get(field)), str)
    ]
    texts.extend(s for s in (record.get("offence_sections") or []) if isinstance(s, str))
    return any(matched_relationship_terms(text) or matched_age_patterns(text) for text in texts)
