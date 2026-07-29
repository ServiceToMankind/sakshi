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


# --- Victim occupation / institution scrub (§4d, issue #88) ------------------
# A NON-MINOR record's model-written title/summary may name the VICTIM's occupation or
# institution ("an IndiGo cabin crew member", "a nurse", "a student at St X School"),
# which re-identifies the victim. §1a had recorded this as a prompt+verifier RESIDUAL
# ("a lexicon ... is too noisy"); a leak of exactly that shape was then observed on a live
# shard (SKS-2026-TG-000007: "raped an IndiGo cabin crew member"), which is the trigger §1a
# named for tightening "via a human-approved issue" — authorised here by issue #88.
#
# Two design rules keep this safe despite lexicon noise:
#  1. FAIL TOWARD REDACTION. An occupation term is scrubbed UNLESS it sits in clear ACCUSED
#     context (an accused noun/verb nearby). Over-redaction only degrades adult-case prose
#     (acceptable); under-redaction is a victim leak (never acceptable). The ACCUSED's
#     occupation is public and legitimate, so it is deliberately KEPT.
#  2. ONE SHARED CORE. ``scrub_victim_occupation`` (sanitizer, removes) and
#     ``matched_victim_occupation`` (pii_guard, asserts) both derive from
#     ``_victim_occupation_spans``, so the guard can only ever flag an occupation the
#     sanitizer would already have removed — never a kept accused occupation. Because the
#     sanitizer runs before every disk write, the guard is pure defence-in-depth.
#
# The lexicon is DELIBERATELY conservative. It excludes words that appear in real adult
# shards as the perpetrator, the judicial response, or a bare victim descriptor rather than
# a victim's job — police, officer, constable, inspector, judge, magistrate, prosecutor,
# passenger, woman/women, man/men, girl, boy, minor, child, person, people, resident,
# driver (commonly the accused here) — so those are never touched.
OCCUPATION_SCANNED_FIELDS: Final[frozenset[str]] = frozenset({"title", "summary"})

# Marker left where a victim occupation span was removed. Must contain no occupation term
# (keeps the scrub idempotent) and match no PII pattern.
OCCUPATION_REDACTION: Final[str] = "[occupation withheld]"

_OCCUPATION_TERMS: Final[tuple[str, ...]] = (
    "cabin crew member",
    "cabin crew",
    "crew member",
    "air hostess",
    "flight attendant",
    "stewardess",
    "nurse",
    "doctor",
    "teacher",
    "tutor",
    "lecturer",
    "professor",
    "student",
    "scholar",
    "intern",
    "software engineer",
    "software professional",
    "it professional",
    "it employee",
    "techie",
    "bpo employee",
    "call centre employee",
    "call center employee",
    "engineer",
    "developer",
    "programmer",
    "architect",
    "receptionist",
    "secretary",
    "accountant",
    "cashier",
    "tailor",
    "beautician",
    "hairdresser",
    "singer",
    "dancer",
    "actress",
    "actor",
    "journalist",
    "reporter",
    "news anchor",
    "housemaid",
    "housekeeper",
    "domestic worker",
    "domestic help",
    "labourer",
    "laborer",
    "vendor",
    "hawker",
    "shopkeeper",
    "waitress",
    "bartender",
    "homemaker",
    "housewife",
    "anganwadi worker",
    "asha worker",
    "sex worker",
    "sales girl",
    "salesgirl",
    "saleswoman",
    "maid",
)

# OPTIONAL article + 0-3 filler/employer words, then the occupation term, then an optional
# bounded institution tail. The article is OPTIONAL so headline-style ("Nurse raped in X",
# "Cabin crew member molested") is caught, not only "a nurse". The filler run absorbs an
# employer ("an IndiGo cabin crew member") or a modifier ("a 24-year-old air hostess"); the
# tail absorbs "... at St Xavier School".
_OCCUPATION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\b(?:a|an|the)\s+(?:[\w.&'-]+\s+){0,3})?"
    r"\b(?:" + "|".join(re.escape(term) for term in _OCCUPATION_TERMS) + r")\b"
    r"(?:\s+(?:at|in|of|with|for)\s+[\w.&'-]+(?:\s+[\w.&'-]+){0,4}?\s+"
    r"(?:school|college|university|institute|academy|hospital|hostel|factory|mill|"
    r"company|firm|office|clinic|salon|parlour|showroom|mall|hotel|restaurant|airlines?))?",
    re.I,
)

# DIRECTIONAL disambiguation, tuned to grammar rather than a symmetric window. An occupation
# is the VICTIM's (REDACT) when it is the object/subject of an assault; the ACCUSED's (KEEP)
# only on a clear accused signal. Concretely:
#  - an assault verb immediately BEFORE ("raped a nurse") -> victim object -> redact (wins
#    even beside the word "accused": "the accused raped a nurse");
#  - otherwise whichever of {assault verb, accused verb} appears FIRST in the text right
#    AFTER the phrase decides it: "nurse was raped" / "cabin crew member raped, driver held"
#    -> assault first -> victim -> redact; "teacher was arrested/convicted" -> accused first
#    -> keep;
#  - else an accused NOUN just before ("the accused, a teacher,") -> keep;
#  - else default -> redact (fail toward redaction).
_ASSAULT_VERB_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:rape[ds]?|gang[\s-]?rape[ds]?|assault(?:ed|ing)?|molest(?:ed|ing)?|"
    r"attack(?:ed|ing)?|abus(?:ed|ing)|violat(?:ed|ing)|sodomi[sz](?:ed|ing))\b",
    re.I,
)
_ACCUSED_VERB_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:arrested|booked|convicted|held|detained|apprehended|nabbed|remanded|jailed|"
    r"imprisoned|sentenced|charged|chargesheeted|absconding)\b",
    re.I,
)
_ACCUSED_NOUN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:accused|convict|convicts|offender|perpetrator|rapist|molester|assailant|"
    r"attacker|abuser|defendant|appellant|culprit|suspect)\b",
    re.I,
)
# How far (chars) on each side to look for the directional signals — a few words only, so a
# signal about a DIFFERENT clause never reaches across to mislabel this occupation.
_CONTEXT_WINDOW: Final[int] = 30


def _first_pos(pattern: re.Pattern[str], text: str) -> int:
    """Start offset of ``pattern``'s first match in ``text``, or a large sentinel."""
    match = pattern.search(text)
    return match.start() if match else len(text) + 1


def _victim_occupation_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, matched-text) for every VICTIM occupation span in ``text``.

    Keep (omit) only when the occupation is clearly the ACCUSED's; otherwise redact.
    """
    spans: list[tuple[int, int, str]] = []
    for match in _OCCUPATION_RE.finditer(text):
        before = text[max(0, match.start() - _CONTEXT_WINDOW) : match.start()]
        after = text[match.end() : match.end() + _CONTEXT_WINDOW]
        if _ASSAULT_VERB_RE.search(before):
            keep = False  # victim: object of an assault verb
        elif _first_pos(_ACCUSED_VERB_RE, after) < _first_pos(_ASSAULT_VERB_RE, after):
            keep = True  # accused verb reaches the phrase before any assault verb
        elif _ACCUSED_VERB_RE.search(after) or _ASSAULT_VERB_RE.search(after):
            keep = False  # an assault verb comes first after -> victim (subject of passive)
        else:
            keep = bool(_ACCUSED_NOUN_RE.search(before))  # accused apposition, else redact
        if not keep:
            spans.append((match.start(), match.end(), match.group(0)))
    return spans


def scrub_victim_occupation(text: str) -> str:
    """Redact every VICTIM occupation/institution span in ``text`` (§4d).

    Right-to-left replacement with :data:`OCCUPATION_REDACTION` keeps earlier spans'
    offsets valid. Idempotent: the placeholder contains no occupation term.
    """
    spans = _victim_occupation_spans(text)
    if not spans:
        return text
    result = text
    for start, end, _ in reversed(spans):
        result = result[:start] + OCCUPATION_REDACTION + result[end:]
    return result


def matched_victim_occupation(text: str) -> list[str]:
    """Return the matched text of every VICTIM occupation span in ``text`` (pii_guard)."""
    return [matched for _, _, matched in _victim_occupation_spans(text)]


def is_occupation_scanned_key(key: str) -> bool:
    """True if ``key`` names a model-written field scanned/scrubbed for victim occupation."""
    return key in OCCUPATION_SCANNED_FIELDS


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
