"""Spot adult records that may be about the same incident as a child's case (issue #255).

One incident is often reported in several articles, and the AI decides "child or adult" for
each article on its own. When one article says the victim is a child and another doesn't,
we could end up publishing an adult-style summary of a child's case. The law (POCSO Act,
section 23) forbids that, so when an adult record looks like it belongs to the same incident
as a child's case, we hold it for review instead of publishing it. Approving it puts it back.

"Looks like the same incident" means all of these:
- same state, and reported within a month of each other;
- their article links share a rare word that isn't an everyday news word, a surname, a
  state, a big city or a district we already know (in practice, the name of a
  neighbourhood, park or village).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from pipeline.pii_constants import KNOWN_PLACES

__all__ = ["possible_child_cases"]

# Two reports more than this many days apart are treated as different incidents.
_WINDOW_DAYS = 31
# A word found in more than this many records' links is too common to tie two records together.
_MAX_RECORDS_SHARING_A_WORD = 12
# Shorter words are almost always everyday ones ("cops", "held"); place names are longer.
_MIN_WORD_LENGTH = 5

# Words that show up in news links all the time and say nothing about which incident it is.
_EVERYDAY_WORDS = frozenset(
    [
        "rape",
        "raped",
        "rapes",
        "gang",
        "gangrape",
        "gangraped",
        "minor",
        "minors",
        "girl",
        "girls",
        "woman",
        "women",
        "child",
        "children",
        "police",
        "case",
        "cases",
        "court",
        "high",
        "supreme",
        "accused",
        "arrested",
        "arrest",
        "held",
        "booked",
        "news",
        "india",
        "city",
        "cities",
        "national",
        "state",
        "district",
        "crime",
        "sexual",
        "assault",
        "assaulted",
        "assaulting",
        "harassment",
        "harassed",
        "molested",
        "molestation",
        "pocso",
        "years",
        "year",
        "after",
        "with",
        "from",
        "into",
        "over",
        "under",
        "against",
        "amid",
        "says",
        "said",
        "probe",
        "trial",
        "bail",
        "jail",
        "custody",
        "judicial",
        "remand",
        "remands",
        "remanded",
        "sentenced",
        "sentence",
        "convicted",
        "conviction",
        "convict",
        "convicts",
        "acquitted",
        "acquits",
        "life",
        "imprisonment",
        "death",
        "murder",
        "murdered",
        "killed",
        "kill",
        "officer",
        "cops",
        "personnel",
        "officers",
        "station",
        "allegedly",
        "alleged",
        "accuses",
        "allegations",
        "allegation",
        "family",
        "families",
        "victim",
        "survivor",
        "students",
        "student",
        "staff",
        "campus",
        "classes",
        "class",
        "school",
        "college",
        "university",
        "teacher",
        "teachers",
        "hospital",
        "doctor",
        "nurse",
        "village",
        "town",
        "area",
        "park",
        "temple",
        "near",
        "home",
        "house",
        "hotel",
        "road",
        "highway",
        "train",
        "auto",
        "driver",
        "leader",
        "leaders",
        "minister",
        "ministers",
        "chief",
        "party",
        "government",
        "govt",
        "registered",
        "complaint",
        "chargesheet",
        "filed",
        "files",
        "investigation",
        "investigate",
        "seeks",
        "sought",
        "seek",
        "orders",
        "order",
        "article",
        "articleshow",
        "html",
        "story",
        "latest",
        "live",
        "updates",
        "breaking",
        "more",
        "what",
        "when",
        "where",
        "which",
        "their",
        "them",
        "this",
        "that",
        "these",
        "those",
        "first",
        "second",
        "third",
        "shocking",
        "details",
        "detail",
        "report",
        "reports",
        "reported",
        "reporting",
        "video",
        "photos",
        "week",
        "weeks",
        "month",
        "months",
        "time",
        "times",
        "hindi",
        "telugu",
        "tamil",
        "another",
        "five",
        "four",
        "three",
        "penalty",
        "prosecution",
        "during",
        "suspended",
        "suspends",
        "official",
        "officials",
        "safety",
        "security",
        "attempt",
        "female",
        "male",
        "challans",
        "challan",
        "formed",
        "special",
        "team",
        "public",
        "absconding",
        "delivered",
        "verdict",
        "posing",
        "faces",
        "faced",
        "visit",
        "fake",
        "threats",
        "threat",
        "knife",
        "weapon",
        "weapons",
        "protest",
        "protests",
        "protesters",
        "demand",
        "demands",
        "cancels",
        "cancel",
        "cancelled",
        "online",
        "offline",
        "today",
        "yesterday",
        "congress",
    ]
)
# Common surnames also turn up in links (of the accused, officials, reporters).
_SURNAMES = frozenset(
    [
        "reddy",
        "kumar",
        "singh",
        "sharma",
        "yadav",
        "naidu",
        "verma",
        "gupta",
        "patel",
        "khan",
        "ahmed",
        "devi",
        "kumari",
        "mishra",
        "pandey",
        "tiwari",
        "chauhan",
        "joshi",
        "menon",
        "pillai",
        "iyer",
        "babu",
        "raju",
        "prasad",
        "chand",
        "gowda",
        "goud",
        "shetty",
        "patil",
        "jadhav",
        "shinde",
        "pawar",
        "sheikh",
        "ansari",
        "qureshi",
        "siddiqui",
        "mohammed",
        "mohammad",
        "kaur",
        "gill",
        "sandhu",
        "sidhu",
        "dhillon",
        "grewal",
        "rathore",
        "rajput",
        "thakur",
        "mehta",
        "desai",
        "parmar",
        "solanki",
        "chaudhary",
        "choudhary",
        "meena",
        "gurjar",
        "saini",
        "agarwal",
        "bansal",
        "mittal",
    ]
)
_PLACE_WORDS = frozenset(word for place in KNOWN_PLACES for word in place.split())
_WORD_RE = re.compile(r"[a-z]+")


def _reported(record: dict[str, Any]) -> date | None:
    """The report date as a day (a child's month-only date counts as the 15th)."""
    value = str(record.get("incident_reported_date") or "")
    try:
        if len(value) >= 10:
            return date.fromisoformat(value[:10])
        if len(value) == 7:
            return date(int(value[:4]), int(value[5:7]), 15)
    except ValueError:
        return None
    return None


def _link_words(record: dict[str, Any], districts: frozenset[str]) -> set[str]:
    """Rare-looking words from a record's article links."""
    words: set[str] = set()
    for source in record.get("sources") or []:
        path = urlsplit(str(source.get("url", ""))).path.lower()
        for word in _WORD_RE.findall(path):
            if (
                len(word) >= _MIN_WORD_LENGTH
                and word not in _EVERYDAY_WORDS
                and word not in _SURNAMES
                and word not in _PLACE_WORDS
                and word not in districts
            ):
                words.add(word)
    return words


def possible_child_cases(records: list[dict[str, Any]]) -> set[int]:
    """Positions (in ``records``) of adult records that may belong to a child's incident."""
    districts = frozenset(
        word for r in records for word in str(r.get("district") or "").lower().split()
    )
    words = [_link_words(r, districts) for r in records]
    how_many = Counter(word for record_words in words for word in record_words)
    children = [i for i, r in enumerate(records) if r.get("minor_involved") is True]
    flagged: set[int] = set()
    for i, adult in enumerate(records):
        if adult.get("minor_involved") is True:
            continue
        when = _reported(adult)
        if when is None:
            continue
        for j in children:
            child = records[j]
            child_when = _reported(child)
            if child.get("state") != adult.get("state") or child_when is None:
                continue
            if abs((when - child_when).days) > _WINDOW_DAYS:
                continue
            shared = {w for w in words[i] & words[j] if how_many[w] <= _MAX_RECORDS_SHARING_A_WORD}
            if shared:
                flagged.add(i)
                break
    return flagged
