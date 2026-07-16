"""Severity labels derived from public charge sections — never from victim particulars.

Charge codes (BNS / POCSO / IPC sections) are public court information and encode the
brutality of the OFFENCE without any identifying detail. Mapping them to a plain-language
severity label + an ``aggravated`` flag is therefore a projection of the CHARGES only,
safe for every case including a minor's (it adds no victim detail — see CLAUDE.md §1a).

The rules are the SINGLE SOURCE ``site/src/severity_rules.json``, loaded here and imported
by the frontend mirror ``site/src/severity.js`` — so the two can never drift.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = [
    "REPEAT_SECTIONS",
    "SEVERITY_RULES",
    "is_aggravated",
    "is_repeat_offender",
    "severity_label",
]

_RULES_PATH = Path(__file__).resolve().parent.parent / "site" / "src" / "severity_rules.json"
_DATA = json.loads(_RULES_PATH.read_text(encoding="utf-8"))

# (label, aggravated, [UPPER-cased section substrings]) — MOST SEVERE FIRST.
SEVERITY_RULES: list[tuple[str, bool, list[str]]] = [
    (r["label"], bool(r["aggravated"]), [s.upper() for s in r["sections"]]) for r in _DATA["rules"]
]
REPEAT_SECTIONS: list[str] = [s.upper() for s in _DATA["repeat_sections"]]


def _needle_pattern(needles: list[str]) -> re.Pattern[str]:
    """A boundary-aware alternation over ``needles``: a needle matches only when NOT
    immediately followed by another alphanumeric — so "IPC 376A" no longer shadows the
    more-specific "IPC 376AB", and "BNS 70" does not match "BNS 700", while
    "BNS 70(2)" (next char "(") and end-of-string still match. Mirrors severity.js."""
    alternation = "|".join(re.escape(n) for n in needles)
    return re.compile(f"(?:{alternation})(?![A-Z0-9])")


# Precompiled boundary-aware matchers, parallel to SEVERITY_RULES / REPEAT_SECTIONS.
_RULE_MATCHERS: list[tuple[str, bool, re.Pattern[str]]] = [
    (label, aggravated, _needle_pattern(needles)) for label, aggravated, needles in SEVERITY_RULES
]
_REPEAT_MATCHER = _needle_pattern(REPEAT_SECTIONS)


def _haystack(sections: Any) -> str:
    """Upper-case + space-normalise the sections into one searchable string, so
    "BNS 70(2)", "bns 70 (2)", and "Section 70(2), BNS" all match the same rule."""
    if not isinstance(sections, list):
        return ""
    return " | ".join(" ".join(str(s).upper().split()) for s in sections)


def severity_label(offence_sections: Any) -> str | None:
    """The single most-severe plain-language label for the charges, or None.

    None means the sections matched no known rule (the card falls back to the coarse
    ``category`` label). Derived ONLY from the sections — never victim data.
    """
    hay = _haystack(offence_sections)
    if not hay:
        return None
    for label, _aggravated, matcher in _RULE_MATCHERS:
        if matcher.search(hay):
            return label
    return None


def is_aggravated(offence_sections: Any) -> bool:
    """True if the matched rule is an aggravated category (dark-red badge weight)."""
    hay = _haystack(offence_sections)
    if not hay:
        return False
    for _label, aggravated, matcher in _RULE_MATCHERS:
        if matcher.search(hay):
            return aggravated
    return False


def is_repeat_offender(offence_sections: Any) -> bool:
    """True if a repeat/habitual-offender section is charged (a separate aggravating
    axis, never the primary label)."""
    return bool(_REPEAT_MATCHER.search(_haystack(offence_sections)))
