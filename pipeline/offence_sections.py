"""Deterministic offence-section normaliser (§4b).

The extractor emits ``offence_sections`` as a free-form ``list[str]`` with duplicates and
junk ("POCSO" vs "POCSO Act", "Section 376 IPC" vs "IPC 376", and non-section tokens like
"rape"/"sexual_assault"). Left raw, dedupe keeps near-duplicates apart, section-overlap
matching misses them, and the severity mapping (substring over ``site/src/severity_rules.json``)
misses reordered forms like "Section 70(2), BNS".

This module parses each entry into a canonical ``{act, section, subsection}`` and
re-serialises it to a canonical STRING in the exact shape the severity needles use
("BNS 70(2)", "IPC 376", "POCSO 6"), so:
  * the stored ``offence_sections`` becomes canonical + deduped (feeds dedupe and severity
    with clean input, and BOTH severity mirrors keep matching with NO change), and
  * genuinely unparseable tokens are separated into ``unparsed_sections`` for review.

LOSS-PRESERVING for severity: ``severity_rules.json`` has ACT-LESS needles ("376D", "326A",
"354D", "354C", "376E") and a bare-"POCSO" needle, so a bare section number IS a real
section and is KEPT (as its canonical bare form) — only a token with NO act and NO
section-number is treated as unparsed. Nothing a severity rule could match is ever dropped.

Pure and deterministic — no I/O, no model. Not a protected file.
"""

from __future__ import annotations

import re

__all__ = ["normalize_sections", "parse_section"]

# Act synonyms -> canonical act token. Order matters only for display; the patterns are
# mutually exclusive in practice. POCSO is checked before IPC/BNS since its long form has
# no digits to confuse the section scan.
_ACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bPOCSO\b|PROTECTION OF CHILDREN"), "POCSO"),
    (re.compile(r"\bBNS\b|BHARATIYA NYAYA SANHITA"), "BNS"),
    (re.compile(r"\bBNSS\b|BHARATIYA NAGARIK SURAKSHA"), "BNSS"),
    (re.compile(r"\bIPC\b|INDIAN PENAL CODE"), "IPC"),
    (re.compile(r"\bCRPC\b|CODE OF CRIMINAL PROCEDURE"), "CRPC"),
)

# A section number: 1-4 digits + up to 3 trailing letters (376, 376A, 376AB, 70), followed
# by zero or more parenthesised subsections ("(2)", "(2)(i)"), tolerating inner whitespace.
_SECTION_RE = re.compile(r"\b(\d{1,4}[A-Z]{0,3})((?:\s*\([^)]{1,4}\))*)")
_SUBSECTION_RE = re.compile(r"\(\s*([^)\s]{1,4})\s*\)")


def parse_section(raw: str) -> tuple[str | None, str | None, str]:
    """Parse one raw section string into ``(act, section, subsection_suffix)``.

    ``act`` is a canonical token or None; ``section`` is the number+letter part or None;
    ``subsection_suffix`` is the re-serialised "(x)(y)" string (empty when none). A string
    with neither a known act nor a section number yields ``(None, None, "")`` — i.e. junk.
    """
    text = " ".join(str(raw).upper().split())
    act = next((canon for pattern, canon in _ACT_PATTERNS if pattern.search(text)), None)
    match = _SECTION_RE.search(text)
    if match is None:
        return act, None, ""
    section = match.group(1)
    subs = _SUBSECTION_RE.findall(match.group(2))
    suffix = "".join(f"({sub})" for sub in subs)
    return act, section, suffix


def _canonical(act: str | None, section: str | None, suffix: str) -> str | None:
    """Re-serialise a parsed section to its canonical string, or None if it is junk."""
    if section is not None:
        return f"{act} {section}{suffix}" if act else f"{section}{suffix}"
    if act is not None:
        return act  # act-only ("POCSO Act" -> "POCSO"): matches the bare-act severity needle
    return None


def normalize_sections(sections: object) -> tuple[list[str], list[str]]:
    """Return ``(canonical_sections, unparsed_sections)`` for a raw sections list.

    ``canonical_sections`` is order-stable and de-duplicated, in the severity-needle shape.
    ``unparsed_sections`` holds the original (whitespace-trimmed) tokens that carried neither
    an act nor a section number — real junk, surfaced for review, kept OUT of the canonical
    list. A non-list input yields two empty lists.
    """
    if not isinstance(sections, list):
        return [], []
    canonical: list[str] = []
    unparsed: list[str] = []
    seen: set[str] = set()
    for raw in sections:
        canon = _canonical(*parse_section(str(raw)))
        if canon is None:
            token = " ".join(str(raw).split())
            if token and token not in unparsed:
                unparsed.append(token)
            continue
        if canon not in seen:
            seen.add(canon)
            canonical.append(canon)
    return canonical, unparsed
