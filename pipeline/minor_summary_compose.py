"""Deterministic composer for a MINOR case's summary (§6b).

A minor's summary is NEVER model-written. §6b permits it to say MORE than the flat template,
but only from facts the extractor captured as STRUCTURED, schema-constrained fields — an
integer count, an enum set of institutional actions, booleans, a sentence length — plus the
offence label (from public charge codes), district, and year. A model cannot smuggle a
hamlet name into a boolean or an enum, so composing from these fields is as safe as the flat
template while carrying real accountability facts.

This module holds ONLY the composition (fixed vocabulary + enum/int inputs). It reads no
free text and can emit no token that is not from its fixed vocabulary, the offence label, the
district, or a number — asserted by the tests. ``sanitize.minor_summary`` calls
:func:`compose` for every child's case.

Since #267 it reads like a short news brief, in the order things happened: when and where,
how many people were accused, every charge in plain words, any weapon or threat, then what
the police and courts did and the outcome. When almost nothing is known it still says the
offence, place, time and status. Non-protected: it performs no PII detection and cannot
leak identity.
"""

from __future__ import annotations

from typing import Any

from pipeline.charges import other_charges

__all__ = ["MAX_BODY_CHARS", "compose"]

# Institutional-response enums -> a fixed, non-identifying sentence. ``arrest_made`` is
# handled in the lead sentence (it combines with the accused count), so it is not here.
_ACTION_SENTENCE: dict[str, str] = {
    "chargesheet_filed": "Police have filed a chargesheet.",
    "bail_granted": "Bail was granted.",
    "bail_denied": "Bail was denied.",
    "sit_formed": "A special investigation team was formed.",
    "suspension_ordered": "An official was suspended over the case.",
    "convicted": "The accused was convicted.",
    "acquitted": "The accused was acquitted.",
    "appeal_filed": "An appeal was filed.",
}
# The whole summary may be 700 characters (schemas/case.schema.json); this leaves room for
# the legal sentence the caller adds at the end.
MAX_BODY_CHARS = 640

# Police and court steps before any verdict, in the order they usually happen.
_STEPS_BEFORE_VERDICT: tuple[str, ...] = (
    "sit_formed",
    "suspension_ordered",
    "chargesheet_filed",
    "bail_granted",
    "bail_denied",
)
_COUNT_WORDS: tuple[str, ...] = (
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
)


_MONTHS: tuple[str, ...] = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# Where the case stands, when no court step below already says it.
_STATUS_SENTENCE: dict[str, str] = {
    "FIR_FILED": "An FIR has been filed.",
    "CHARGESHEETED": "A chargesheet has been filed.",
    "UNDER_TRIAL": "The case is under trial.",
    "CONVICTED": "The accused was convicted.",
    "ACQUITTED": "The accused was acquitted.",
    "APPEAL_PENDING": "An appeal is pending.",
    "CLOSED": "The case is closed.",
    "QUASHED": "The case was quashed.",
    "UNKNOWN": "The case status is not yet known.",
}


def _count_phrase(n: int) -> tuple[str, str]:
    """Return (subject phrase, verb) for an accused count, e.g. (3 -> "Three people", "were")."""
    word = _COUNT_WORDS[n] if 1 <= n <= 10 else str(n)
    return (f"{word} {'person' if n == 1 else 'people'}", "was" if n == 1 else "were")


def _int_or_none(value: Any, minimum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= minimum else None


def _when(record: dict[str, Any]) -> str:
    """ "In June 2013, " from a child's month-precise date, "In 2013, ", or nothing."""
    value = str(record.get("incident_reported_date") or "")
    year = value[:4] if value[:4].isdigit() else ""
    month = int(value[5:7]) if len(value) >= 7 and value[5:7].isdigit() else 0
    if year and 1 <= month <= 12:
        return f"In {_MONTHS[month]} {year}, "
    return f"In {year}, " if year else ""


def _join(items: list[str]) -> str:
    """ "a", "a and b", "a, b and c"."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _sentenced(years: int | None, plural: bool) -> str:
    if years is None:
        return ""
    unit = "year" if years == 1 else "years"
    return f" and sentenced {'each ' if plural else ''}to {years} {unit} in prison"


def _outcome(record: dict[str, Any], actions: set[str], years: int | None, plural: bool) -> str:
    """What the courts decided, in order, or "" if no verdict is recorded."""
    status = str(record.get("status", "")).upper()
    convicted, acquitted = "convicted" in actions, "acquitted" in actions
    on_appeal = " on appeal" if "appeal_filed" in actions else ""
    subject = "The accused were" if plural else "The accused was"
    if convicted and acquitted:
        if status == "ACQUITTED":
            return (
                f"{subject} convicted{_sentenced(years, plural)}, and later acquitted{on_appeal}."
            )
        if status == "CONVICTED":
            later = f"later convicted{on_appeal}{_sentenced(years, plural)}"
            return f"{subject} first acquitted, and {later}."
        return f"{subject} convicted at one stage and acquitted at another."
    if convicted:
        text = f"{subject} convicted{_sentenced(years, plural)}."
        if "appeal_filed" in actions:
            text += " An appeal against the verdict has been filed."
        return text
    if acquitted:
        text = f"{subject} acquitted."
        if "appeal_filed" in actions:
            text += " An appeal against the acquittal has been filed."
        return text
    return ""


def compose(record: dict[str, Any], offence_lc: str, where: str) -> str:
    """Compose a child's case as a short news brief from structured facts only.

    ``offence_lc`` is the lower-cased offence phrase (e.g. "aggravated sexual assault of a
    child"); ``where`` is " in <district>" (or the state) or "". Returns the sentences WITHOUT
    the legal withholding line, which the caller appends.
    """
    count = _int_or_none(record.get("accused_count"), 1)
    raw_actions = record.get("institutional_actions") or []
    actions = {a for a in raw_actions if a in _ACTION_SENTENCE or a == "arrest_made"}
    repeat = record.get("repeat_offence") is True
    weapon = record.get("weapon_or_threat") is True
    years = _int_or_none(record.get("sentence_years"), 0)
    plural = count is not None and count > 1

    # Lead: how many, what, where — then "In June 2013, ..." in front.
    if "arrest_made" in actions and count is not None:
        subject, verb = _count_phrase(count)
        lead = f"{subject} {verb} arrested{where} for the {offence_lc}."
    elif "arrest_made" in actions:
        lead = f"Police made an arrest{where} over the {offence_lc}."
    elif count is not None:
        subject, verb = _count_phrase(count)
        lead = f"{subject} {verb} accused of the {offence_lc}{where}."
    else:
        lead = f"A case of {offence_lc} was registered{where}."
    when = _when(record)
    if when:
        lead = when + lead[0].lower() + lead[1:]
    parts = [lead]

    # Sentences we can drop, least important first, if a case has too much to fit.
    optional: list[str] = []
    others = other_charges(record.get("offence_sections") or [])
    if others:
        parts.append(f"The charges also include {_join(others)}.")
    # The cruelty of the ACT may be stated, never anything about the victim.
    if weapon:
        parts.append("A weapon was used or a threat was made.")
    if repeat:
        parts.append("The accused is recorded as a repeat offender.")

    # What the police and courts did, in the order it happens.
    for step in _STEPS_BEFORE_VERDICT:
        if step in actions:
            parts.append(_ACTION_SENTENCE[step])
            if step != "chargesheet_filed":
                optional.append(_ACTION_SENTENCE[step])
    optional += [
        "The accused is recorded as a repeat offender.",
        "A weapon was used or a threat was made.",
        *([f"The charges also include {_join(others)}."] if others else []),
    ]
    outcome = _outcome(record, actions, years, plural)
    if outcome:
        parts.append(outcome)
    elif years is not None:
        unit = "year" if years == 1 else "years"
        parts.append(f"The court imposed a sentence of {years} {unit}.")
    else:
        status = str(record.get("status", "")).upper()
        if not (status == "CHARGESHEETED" and "chargesheet_filed" in actions):
            parts.append(_STATUS_SENTENCE.get(status, _STATUS_SENTENCE["UNKNOWN"]))
        if "appeal_filed" in actions and status != "APPEAL_PENDING":
            parts.append(_ACTION_SENTENCE["appeal_filed"])
    for sentence in optional:
        if len(" ".join(parts)) <= MAX_BODY_CHARS:
            break
        if sentence in parts:
            parts.remove(sentence)
    return " ".join(parts)
