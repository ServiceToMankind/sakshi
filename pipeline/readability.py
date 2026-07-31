"""Deterministic readability gate for NON-MINOR summaries (§6a).

§6a is a GATE, not a prompt hint: a prompt will eventually be disobeyed, so a deterministic
check stands behind it. A published non-minor summary must be plain enough for a low-literacy
general reader — no legalese, no sentence longer than 25 words, and never a bare
section-number citation in prose (describe the offence, don't cite "u/s 376").

The SAME core powers the pipeline gate (a fresh non-compliant summary routes to ``_review``)
and ``scripts/readability_guard.py`` (the CI assertion over the written tree). A MINOR's
summary is deterministic (fixed vocabulary) and is never checked here. Non-protected.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["MAX_WORDS_PER_SENTENCE", "readability_violations", "summary_is_readable"]

MAX_WORDS_PER_SENTENCE = 25

# Legalese a general reader should not have to parse. Matched case-insensitively as whole
# words/phrases. Kept to unambiguous court-jargon so plain prose is never falsely flagged.
_BANNED_TERMS: tuple[str, ...] = (
    "stayed proceedings",
    "vide order",
    "learned counsel",
    "the instant matter",
    "quashed the proceedings",
    "aforesaid",
    "hereinafter",
    "prima facie",
    "cognizance",
    "petitioner",
    "petitioners",
    "respondent",
    "respondents",
)
_BANNED_RE = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in _BANNED_TERMS) + r")\b", re.I)
# Abbreviated statute references ("u/s", "r/w").
_ABBREV_RE = re.compile(r"\b(?:u/s|r/w)\b", re.I)
# A bare section-number-in-prose citation: "Section 376", "under section 376", "376 IPC",
# "IPC 376", "BNS 64", "POCSO 6". The offence must be described in words, not cited by number.
_SECTION_IN_PROSE_RE = re.compile(
    r"\bunder\s+section\b|\bsection\s+\d|\b\d{2,4}[A-Za-z]?\s*(?:IPC|BNS|BNSS|POCSO)\b"
    r"|\b(?:IPC|BNS|BNSS|POCSO)\s*\d",
    re.I,
)
_SENTENCE_SPLIT = re.compile(r"[.!?]+")


def readability_violations(summary: Any) -> list[str]:
    """Return a list of human-readable violation reasons for ``summary`` (empty = clean)."""
    if not isinstance(summary, str):
        return []
    reasons: list[str] = []
    banned = {m.group(0).lower() for m in _BANNED_RE.finditer(summary)}
    banned |= {m.group(0).lower() for m in _ABBREV_RE.finditer(summary)}
    for term in sorted(banned):
        reasons.append(f"legalese term '{term}'")
    if _SECTION_IN_PROSE_RE.search(summary):
        reasons.append("cites a statute section by number in prose")
    for sentence in _SENTENCE_SPLIT.split(summary):
        words = sentence.split()
        if len(words) > MAX_WORDS_PER_SENTENCE:
            reasons.append(f"sentence exceeds {MAX_WORDS_PER_SENTENCE} words ({len(words)})")
    return reasons


def summary_is_readable(summary: Any) -> bool:
    """True if ``summary`` has no readability violation."""
    return not readability_violations(summary)
