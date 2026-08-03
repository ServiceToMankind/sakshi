"""§4e multilingual PII guard — the ENFORCED multilingual extension of the identity floor.

WIRED (issue #136) into the protected gates: :func:`scrub_multilingual_pii` runs inside
``pipeline.sanitize.sanitize_string`` (the last gate before disk), and
:func:`find_multilingual_pii` is asserted in ``scripts/pii_guard`` (the ship-time backstop).
Every active identity gate before this one — ``pii_constants.PII_VALUE_PATTERNS`` /
``AGE_EXPRESSION_PATTERNS``, the occupation scrub — is an ENGLISH regex; none fires on
Devanagari/Telugu/Tamil/Bengali script, nor on the *romanized* Indian-language terms that
survive an English-output extraction. This module closes that gap so a regional-language
source (§4d) cannot run with the identity floor silently disabled for its input.

Two re-identification vectors, plus an English-output tripwire:

1. **Romanized terms that survive the English-output extraction.** In a small district these
   identify a person as precisely as a name:
   - **Kinship** terms that TRANSLITERATE rather than translate ("the chacha", "her jija") —
     they state the victim–accused RELATIONSHIP, an absolutely forbidden field (§1a),
     regardless of direction.
   - **Local office titles** (sarpanch, patwari, pradhan, mukhiya) that name a village office
     holder uniquely.
   - **Sub-district geography** (gaon, thanda, basti, tola, wadi) — a locality finer than the
     district, which is the finest locality the project ever stores.
2. **Native-script text in a published field.** Extraction MUST output English; any
   Devanagari/Telugu/Tamil/… run in a field is either raw-source text that leaked or an
   un-Englishised value — both are treated as PII and redacted. Native-script AGE
   expressions (digits next to a script's word for "years") are called out specifically.

The ambiguity rule (why this does not false-positive on English): terms that are ALSO common
English words (mama, anna, akka, dada, didi, para, colony, nagar) are NOT in the always-on
lexicons — they live in :data:`LANGUAGE_KINSHIP_TERMS`, activated by the ``languages``
argument that each per-language §4d/D5 PR passes once its source language makes them
unambiguous. The always-on set is distinctly-Indian romanizations only. Failing toward
redaction is fine (a hit redacts / quarantines, it never leaks); false positives on plain
English are not.
"""

from __future__ import annotations

import re

__all__ = [
    "LANGUAGES",
    "LANGUAGE_KINSHIP_TERMS",
    "LOCAL_OFFICE_TITLES",
    "NATIVE_SCRIPT_AGE_PATTERNS",
    "NATIVE_SCRIPT_RANGES",
    "REDACTION_PLACEHOLDER",
    "ROMANIZED_KINSHIP_TERMS",
    "SUBDISTRICT_GEO_TERMS",
    "contains_native_script",
    "find_multilingual_pii",
    "find_native_scripts",
    "matched_native_script",
    "matched_romanized_pii",
    "scrub_multilingual_pii",
    "scrub_native_script",
]

# Must equal pipeline.sanitize.REDACTION_PLACEHOLDER (a test asserts parity). It contains no
# native script, digits, or lexicon term, so scrubbing is idempotent.
REDACTION_PLACEHOLDER = "[redacted]"

# Languages this guard has coverage for. The list is the §4d enablement checklist: a language
# is ready only when its native-script + romanized patterns exist AND fixtures prove they fire.
LANGUAGES: tuple[str, ...] = (
    "hindi",
    "marathi",
    "telugu",
    "tamil",
    "bengali",
    "malayalam",
    "kannada",
    "gujarati",
    "odia",
    "punjabi",
    "assamese",
)

# --- Vector 2: native-script detection (the English-output tripwire) --------------------------

# Unicode block per Indic script. A published field must be English; any run of these code
# points is redacted (and asserted absent). Each block includes that script's own digits.
NATIVE_SCRIPT_RANGES: dict[str, tuple[str, str]] = {
    "devanagari": ("ऀ", "ॿ"),  # Hindi, Marathi, Nepali
    "bengali": ("ঀ", "৿"),  # Bengali, Assamese
    "gurmukhi": ("਀", "੿"),  # Punjabi
    "gujarati": ("઀", "૿"),  # Gujarati
    "oriya": ("଀", "୿"),  # Odia
    "tamil": ("஀", "௿"),  # Tamil
    "telugu": ("ఀ", "౿"),  # Telugu
    "kannada": ("ಀ", "೿"),  # Kannada
    "malayalam": ("ഀ", "ൿ"),  # Malayalam
}
_ALL_NATIVE_CLASS = "".join(f"{lo}-{hi}" for lo, hi in NATIVE_SCRIPT_RANGES.values())
_NATIVE_RUN_RE = re.compile(f"[{_ALL_NATIVE_CLASS}]+")
_SCRIPT_RES: dict[str, re.Pattern[str]] = {
    name: re.compile(f"[{lo}-{hi}]") for name, (lo, hi) in NATIVE_SCRIPT_RANGES.items()
}


def contains_native_script(text: str) -> bool:
    """True if ``text`` contains any Indic-script character (an English-output violation)."""
    return bool(text) and _NATIVE_RUN_RE.search(text) is not None


def find_native_scripts(text: str) -> list[str]:
    """The Indic scripts present in ``text`` (empty if it is plain ASCII/Latin)."""
    if not text:
        return []
    return [name for name, pattern in _SCRIPT_RES.items() if pattern.search(text)]


# Native-script AGE expressions: a 1-2 digit run (native OR ASCII) next to a script's word for
# "years"/"age". A more SPECIFIC signal than the native-run tripwire (which already covers the
# whole span); kept per-script because an age is forbidden beyond the minor boolean.
NATIVE_SCRIPT_AGE_PATTERNS: dict[str, re.Pattern[str]] = {
    "hindi": re.compile(r"[0-9०-९]{1,2}\s*(?:साल|वर्ष|बरस|वर्षीय|वर्षीया)"),
    "telugu": re.compile(r"[0-9౦-౯]{1,2}\s*(?:ఏళ్ల|ఏళ్ళ|ఏళ్లు|సంవత్సరాల|సంవత్సరాలు)"),
    "tamil": re.compile(r"[0-9௦-௯]{1,2}\s*(?:வயது|வயதான|ஆண்டு)"),
    "bengali": re.compile(r"[0-9০-৯]{1,2}\s*(?:বছর|বছরের|বয়স|বয়সী)"),
    "malayalam": re.compile(r"[0-9൦-൯]{1,2}\s*(?:വയസ്സ്|വയസ്|വർഷം)"),
    "kannada": re.compile(r"[0-9೦-೯]{1,2}\s*(?:ವರ್ಷ|ವಯಸ್ಸು|ವರ್ಷದ)"),
    "gujarati": re.compile(r"[0-9૦-૯]{1,2}\s*(?:વર્ષ|વર્ષની|વરસ)"),
    "punjabi": re.compile(r"[0-9੦-੯]{1,2}\s*(?:ਸਾਲ|ਵਰ੍ਹੇ)"),
    "odia": re.compile(r"[0-9୦-୯]{1,2}\s*(?:ବର୍ଷ|ବର୍ଷର)"),
}

# --- Vector 1: romanized terms that survive an English-output extraction ----------------------

# Kinship terms that TRANSLITERATE and state a victim–accused relationship (§1a). ALWAYS-ON:
# distinctly-Indian romanizations only. Terms that are also common English words (mama, anna,
# akka, dada, didi) are NOT here — they are in LANGUAGE_KINSHIP_TERMS, per-language.
ROMANIZED_KINSHIP_TERMS: frozenset[str] = frozenset(
    {
        # Hindi / Urdu / north
        "chacha",
        "chachi",
        "chacha ji",
        "taya",
        "tayi",
        "phupha",
        "phupa",
        "phuphi",
        "phua",
        "mausa",
        "mausi",
        "mama ji",
        "jija",
        "jiju",
        "bhabhi",
        "devar",
        "devrani",
        "nanad",
        "jethani",
        "mausera",
        "chachera",
        "mamera",
        "fufera",
        # Telugu / south
        "mama garu",
        "pinni",
        "babai",
        "peddananna",
        "chinnanna",
        "bavagaru",
        "menamama",
        "menatha",
        # Tamil
        "chithappa",
        "periyappa",
        "athimber",
        # Marathi / Bengali / others (distinctly-Indian romanizations)
        "mavshi",
        "jamai",
    }
)

# English-AMBIGUOUS kinship terms, per language. Activated only when the caller passes the
# language (a §4d/D5 PR, whose source language makes these unambiguous). Never in the always-on
# scan, so plain English never false-positives on "mama"/"anna"/"dada".
LANGUAGE_KINSHIP_TERMS: dict[str, frozenset[str]] = {
    "hindi": frozenset({"mama", "mami", "bua", "dada", "dadi", "nana", "nani", "didi", "tau"}),
    "marathi": frozenset({"mama", "mami", "kaka", "kaki", "dada", "tai", "atya"}),
    "telugu": frozenset({"anna", "akka", "amma", "nanna", "tammudu", "chellelu", "mama"}),
    "tamil": frozenset({"anna", "akka", "mama", "appa", "amma", "thambi"}),
    "bengali": frozenset({"dada", "didi", "mama", "mami", "kaka", "kaki", "pisi"}),
    "kannada": frozenset({"anna", "akka", "mama", "appa", "amma", "thatha"}),
    "malayalam": frozenset({"chettan", "chechi", "amma", "appan", "mama"}),
    "gujarati": frozenset({"kaka", "kaki", "mama", "mami", "fua", "fai", "dada", "dadi"}),
    "punjabi": frozenset({"chacha", "taya", "mama", "bhua", "veer", "bhaji"}),
    "odia": frozenset({"mama", "mami", "kaka", "kaki", "bhai", "nana"}),
    "assamese": frozenset({"mama", "mami", "kaka", "khura", "pehi", "mahi"}),
}

# Local office / authority titles that identify a village office holder uniquely.
LOCAL_OFFICE_TITLES: frozenset[str] = frozenset(
    {
        "sarpanch",
        "up-sarpanch",
        "upsarpanch",
        "sarpanchni",
        "patwari",
        "patwary",
        "gram pradhan",
        "pradhan",
        "mukhiya",
        "gram panchayat",
        "gram sabha",
        "gram sevak",
        "lambardar",
        "kotwal",
        "talati",
        "tehsildar",
        "naib tehsildar",
        "numberdar",
        "zilla parishad",
        "panchayat samiti",
    }
)

# Sub-district geography terms (a locality FINER than the district — the finest we ever store).
# English-ambiguous forms (para, colony, hamlet, nagar, pura) are EXCLUDED by design.
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
        "mauza",
        "tanr",
    }
)


def _boundaried(terms: frozenset[str]) -> re.Pattern[str]:
    """A case-insensitive, word-boundaried alternation over ``terms`` (longest first so a
    multi-word term wins over its prefix). The alternation is GROUPED so the word boundaries
    bind the whole set — without the group, ``(?<![\\w])`` would guard only the first term and
    ``(?![\\w])`` only the last, so a middle term like "gaon" would match inside "gurgaon"."""
    alt = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![\w])(?:{alt})(?![\w])", re.IGNORECASE)


_KINSHIP_RE = _boundaried(ROMANIZED_KINSHIP_TERMS)
_OFFICE_RE = _boundaried(LOCAL_OFFICE_TITLES)
_GEO_RE = _boundaried(SUBDISTRICT_GEO_TERMS)
_LANG_KINSHIP_RES: dict[str, re.Pattern[str]] = {
    lang: _boundaried(terms) for lang, terms in LANGUAGE_KINSHIP_TERMS.items()
}


def matched_native_script(text: str) -> list[str]:
    """Native-script vectors in ``text``: ``native_age:<lang>`` and ``native_script:<script>``.

    Scanned in EVERY published field (a URL/id/enum is ASCII, so this never false-positives
    there) because extraction must output English — a native-script run anywhere is a leak.
    """
    if not isinstance(text, str) or not text:
        return []
    hits: list[str] = []
    for lang, pattern in NATIVE_SCRIPT_AGE_PATTERNS.items():
        if pattern.search(text):
            hits.append(f"native_age:{lang}")
    for script in find_native_scripts(text):
        hits.append(f"native_script:{script}")
    return hits


def matched_romanized_pii(text: str, *, languages: tuple[str, ...] = ()) -> list[str]:
    """Romanized identity vectors in ``text``: kinship relationship, local office title, or
    sub-district locality. Scanned only in PROSE fields (title/summary) — a citation URL slug
    legitimately carries a place name (e.g. ``.../rampur-gaon-case/``). ``languages`` activates
    that language's English-ambiguous kinship set (a §4d/D5 PR passes it once its source
    language makes those terms unambiguous)."""
    if not isinstance(text, str) or not text:
        return []
    hits: list[str] = []
    if _KINSHIP_RE.search(text):
        hits.append("romanized_kinship_relation")
    if _OFFICE_RE.search(text):
        hits.append("local_office_title")
    if _GEO_RE.search(text):
        hits.append("subdistrict_geography")
    for lang in languages:
        rx = _LANG_KINSHIP_RES.get(lang)
        if rx is not None and rx.search(text):
            hits.append(f"romanized_kinship_relation:{lang}")
    return hits


def find_multilingual_pii(text: str, *, languages: tuple[str, ...] = ()) -> list[str]:
    """All multilingual re-identification vectors in ``text`` (romanized + native), empty=none.

    The combined view (used by tests and callers that scan prose). ``scripts/pii_guard`` scopes
    the two families differently: native-script everywhere, romanized markers in prose only.
    """
    return matched_romanized_pii(text, languages=languages) + matched_native_script(text)


def scrub_native_script(text: str) -> str:
    """Redact native-script age spans and any native-script run — the English-output
    enforcement wired into :func:`pipeline.sanitize.sanitize_string` (safe on every field:
    a URL/id/date is ASCII, so nothing is touched there). Idempotent."""
    if not isinstance(text, str) or not text:
        return text
    result = text
    for pattern in NATIVE_SCRIPT_AGE_PATTERNS.values():
        result = pattern.sub(REDACTION_PLACEHOLDER, result)
    return _NATIVE_RUN_RE.sub(REDACTION_PLACEHOLDER, result)


def scrub_multilingual_pii(text: str) -> str:
    """Redact romanized identity markers AND native-script from ``text`` — the full scrub for
    PROSE fields (title/summary), wired into ``pipeline.sanitize``. Idempotent — the placeholder
    matches none of the patterns. Conservative: an office title is redacted even where it might
    name an accused official (fails toward redaction, per issue #136)."""
    if not isinstance(text, str) or not text:
        return text
    result = text
    for pattern in (_KINSHIP_RE, _OFFICE_RE, _GEO_RE):
        result = pattern.sub(REDACTION_PLACEHOLDER, result)
    return scrub_native_script(result)
