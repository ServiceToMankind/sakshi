"""PROPOSAL (§4e) — multilingual PII detection for enabling non-English sources.

**NOT YET WIRED, and it is a HARD BLOCKER that it be wired before any non-English source is
enabled.** Every active identity gate today — ``pii_constants.PII_VALUE_PATTERNS`` /
``AGE_EXPRESSION_PATTERNS``, ``sanitize``, ``scripts/pii_guard`` — is an ENGLISH regex. None
fires on Devanagari/Telugu/Tamil/Bengali script, and none fires on the *romanized* Indian-
language terms that survive an English-output extraction. Enabling a regional-language source
without extending these guards runs the pipeline with the identity floor silently disabled
for most of its input.

This module is the reviewed STARTING POINT for that extension. Wiring it into the protected
files (`pii_constants.py` / `sanitize.py` / `scripts/pii_guard.py`) requires a human-approved
issue (CLAUDE.md §2). Per §4e, no non-English source may be enabled until (a) that wiring
lands, and (b) fixture records in each enabled script prove the guard FIRES at 100% branch
coverage. Language enablement is one PR per language, each carrying its guard extension.

Two re-identification vectors this addresses:

1. **Romanized terms that survive the English-output extraction.** In a small district these
   identify a person as precisely as a name:
   - **Kinship** terms that TRANSLITERATE rather than translate — "the mama", "the chacha" —
     which state the victim–accused RELATIONSHIP (an absolutely forbidden field, §1a),
     regardless of direction.
   - **Local office titles** (sarpanch, patwari, pradhan, mukhiya) that name a village office
     holder uniquely.
   - **Sub-district geography** (gaon, thanda, basti, palli, wadi, tola, para) — a locality
     finer than the district, which is the finest we ever store.
2. **Native-script age/kinship expressions in raw source text** (defence-in-depth if the
   in-memory source text ever leaks into a field): e.g. Devanagari ``साल`` / ``वर्ष`` with digits.

Detections here are a REVIEW/QUARANTINE signal (like ``dedupe.has_identity_detail``), not a
scrub — a relationship or a sub-district locality means the record must not auto-publish.
"""

from __future__ import annotations

import re

__all__ = [
    "LANGUAGES",
    "LOCAL_OFFICE_TITLES",
    "NATIVE_SCRIPT_AGE_PATTERNS",
    "ROMANIZED_KINSHIP_TERMS",
    "SUBDISTRICT_GEO_TERMS",
    "find_multilingual_pii",
]

# Languages this proposal has SOME coverage for. The list is the enablement checklist: a
# language is ready only when its native-script patterns + fixtures exist and are wired.
LANGUAGES: tuple[str, ...] = (
    "hindi",
    "telugu",
    "tamil",
    "marathi",
    "bengali",
    "malayalam",
    "kannada",
    "gujarati",
    "odia",
    "punjabi",
    "assamese",
)

# --- Vector 1: romanized terms that survive an English-output extraction ---------------------

# Kinship terms that TRANSLITERATE (appear romanized in English text) and state a victim–accused
# relationship — a forbidden field (§1a). Deliberately DISTINCTLY-INDIAN + high-precision: terms
# that are also common English words (mama, anna, dada, didi, para) are EXCLUDED here — the
# per-language wiring PR re-adds them behind a language guard where they are unambiguous. Failing
# toward review is fine (a hit quarantines, it does not leak); false positives on English are not.
ROMANIZED_KINSHIP_TERMS: frozenset[str] = frozenset(
    {
        # Hindi/Urdu/north
        "chacha",
        "chachi",
        "chacha ji",
        "taya",
        "phupha",
        "phupa",
        "bua",
        "phua",
        "mausa",
        "mausi",
        "mama ji",
        "jija",
        "jiju",
        "bhabhi",
        "devar",
        "nanad",
        "mausera",
        "chachera",
        "mamera",
        "fufera",
        # Telugu/south
        "mama garu",
        "pinni",
        "babai",
        "peddananna",
        "chinnanna",
        "thammudu",
        "chellelu",
        "menamama",
        "menatha",
        # Tamil
        "chithappa",
        "periyappa",
        "athimber",
        # Marathi/Bengali/others (distinctly-Indian romanizations)
        "mavshi",
        "jamai",
    }
)

# Local office / authority titles that identify a village office holder uniquely.
LOCAL_OFFICE_TITLES: frozenset[str] = frozenset(
    {
        "sarpanch",
        "up-sarpanch",
        "upsarpanch",
        "patwari",
        "patwary",
        "gram pradhan",
        "mukhiya",
        "gram panchayat",
        "lambardar",
        "kotwal",
        "talati",
        "tehsildar",
        "numberdar",
        "zilla parishad",
        "gram sabha",
    }
)

# Sub-district geography terms (a locality FINER than the district — the finest we ever store).
# English-ambiguous forms (para, colony, hamlet, nagar, pura) are EXCLUDED; a per-language PR
# re-adds them behind a language guard.
SUBDISTRICT_GEO_TERMS: frozenset[str] = frozenset(
    {
        "gaon",
        "thanda",
        "tanda",
        "basti",
        "basthi",
        "palli",
        "wadi",
        "vadi",
        "tola",
        "tolla",
        "mohalla",
        "muhalla",
        "purwa",
        "kheda",
        "khera",
        "dhani",
        "majra",
    }
)


def _boundaried(terms: frozenset[str]) -> re.Pattern[str]:
    """A case-insensitive, word-boundaried alternation over a term set (longest first so a
    multi-word term wins over its prefix)."""
    alt = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![\w]){alt}(?![\w])", re.I)


_KINSHIP_RE = _boundaried(ROMANIZED_KINSHIP_TERMS)
_OFFICE_RE = _boundaried(LOCAL_OFFICE_TITLES)
_GEO_RE = _boundaried(SUBDISTRICT_GEO_TERMS)

# --- Vector 2: native-script age expressions (defence-in-depth) ------------------------------

# Per-script age expressions: a run of native OR ASCII digits next to a "years" word. Extend one
# script at a time with a native speaker + fixtures. Only Hindi (Devanagari) is filled in as the
# worked first example; the others are placeholders a per-language PR completes.
NATIVE_SCRIPT_AGE_PATTERNS: dict[str, re.Pattern[str]] = {
    # Devanagari (Hindi/Marathi): digits (Devanagari ०-९ or ASCII) within a few chars of
    # साल (saal) or वर्ष (varsh) = "years".
    "hindi": re.compile(r"[0-9०-९]{1,2}\s*(?:साल|वर्ष|बरस)"),
}


def find_multilingual_pii(text: str) -> list[str]:
    """Return the multilingual re-identification vectors present in ``text`` (empty = none).

    Each hit is a REVIEW/QUARANTINE signal — a romanized kinship relationship, a local office
    title, a sub-district locality, or a native-script age. Conservative + high-precision by
    design; a per-language PR broadens it with fixtures before that language is enabled.
    """
    if not isinstance(text, str) or not text:
        return []
    hits: list[str] = []
    if _KINSHIP_RE.search(text):
        hits.append("romanized_kinship_relation")
    if _OFFICE_RE.search(text):
        hits.append("local_office_title")
    if _GEO_RE.search(text):
        hits.append("subdistrict_geography")
    for lang, pattern in NATIVE_SCRIPT_AGE_PATTERNS.items():
        if pattern.search(text):
            hits.append(f"native_age:{lang}")
    return hits
