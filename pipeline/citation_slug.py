"""Detect whether a citation URL's own slug states a detail the record withholds (§5).

A news URL slug routinely spells out what the record deliberately omits — a victim age
("3-year-old", "four-year-old"), gender ("girl"/"boys"), the accused's relationship to the
victim ("maternal-uncle", "teacher"), or an institution ("school", "welfare-home"). For a
minor that is a POCSO s.23 re-identification vector; for any victim it is a BNS s.72 concern.

The record keeps the URL (a citation must be verifiable) but marks it so the site can render
the domain — never the raw slug — as the link text and tuck a flagged source behind an
expander, showing clean sources first. This is a deterministic, side-effect-free scan of the
URL PATH only (the query/host are ignored); it never inspects victim data, only the public
slug. Non-protected file.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

__all__ = ["url_carries_identifying_slug"]

# Split a URL path into words so hyphen/underscore/dot-delimited slugs become plain tokens
# ("3-year-old" -> "3 year old", "maternal_uncle" -> "maternal uncle").
_PATH_SPLIT = re.compile(r"[/\-_.]+")

# Victim-identifying tokens. Biased to flag (a false flag only hides a source behind an
# expander; a missed one shows an identifying slug prominently). Deliberately EXCLUDES
# case/response words that are safe in a slug (court, bail, pocso, arrested, chargesheet,
# accused, convict) and the accused's OWN occupation when unrelated to the victim.
_IDENTIFYING = re.compile(
    r"\b(?:"
    # numeric age — "3 year old", "17 yr old", "16 yo"
    r"\d{1,2}\s?(?:year|yr)s?\s?old|\d{1,2}\s?yo|"
    # spelled age — "four year old"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen)\s?(?:year|yr)s?\s?old|"
    # age / life-stage words
    r"toddler|infant|teenager|teenaged|schoolgirl|schoolboy|"
    # gender
    r"girls?|boys?|woman|women|lady|"
    # accused-victim relationship
    r"father|stepfather|uncle|brother|cousin|grandfather|neighbour|neighbor|teacher|tutor|"
    r"guardian|relatives?|husband|maternal|paternal|caretaker|caregiver|warden|principal|"
    r"priest|"
    # institution / sub-district-scale locality
    r"school|college|hostel|orphanage|madrasa|convent|tuition|anganwadi|creche"
    r")\b",
    re.I,
)


def url_carries_identifying_slug(url: str) -> bool:
    """True if the URL's path slug states a victim age, gender, accused-victim relationship,
    or institution - a detail the record withholds."""
    slug = " ".join(_PATH_SPLIT.split(urlsplit(str(url)).path))
    return bool(_IDENTIFYING.search(slug))
