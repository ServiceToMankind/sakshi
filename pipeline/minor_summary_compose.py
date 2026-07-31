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
:func:`compose` and falls back to the flat template when fewer than two structured facts
resolve. Non-protected: it performs no PII detection and cannot leak identity.
"""

from __future__ import annotations

from typing import Any

__all__ = ["compose"]

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
# Fixed order the further-action sentences are emitted in (never the model's order).
_ACTION_ORDER: tuple[str, ...] = (
    "chargesheet_filed",
    "bail_granted",
    "bail_denied",
    "sit_formed",
    "suspension_ordered",
    "convicted",
    "acquitted",
    "appeal_filed",
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


def _count_phrase(n: int) -> tuple[str, str]:
    """Return (subject phrase, verb) for an accused count, e.g. (3 -> "Three people", "were")."""
    word = _COUNT_WORDS[n] if 1 <= n <= 10 else str(n)
    return (f"{word} {'person' if n == 1 else 'people'}", "was" if n == 1 else "were")


def _int_or_none(value: Any, minimum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= minimum else None


def compose(record: dict[str, Any], offence_lc: str, where: str) -> str | None:
    """Compose a minor summary body from structured facts, or None to signal fallback.

    ``offence_lc`` is the lower-cased offence phrase (e.g. "aggravated sexual assault of a
    child"); ``where`` is " in <district>" or "". Returns the composed sentences WITHOUT the
    statutory withholding line (the caller appends it), or None when fewer than two structured
    facts resolve (the caller then uses the flat template).
    """
    count = _int_or_none(record.get("accused_count"), 1)
    actions = [a for a in (record.get("institutional_actions") or []) if a in _ACTION_SENTENCE]
    arrested = "arrest_made" in (record.get("institutional_actions") or [])
    repeat = record.get("repeat_offence") is True
    weapon = record.get("weapon_or_threat") is True
    sentence_years = _int_or_none(record.get("sentence_years"), 0)

    resolved = sum(
        [count is not None, arrested or bool(actions), repeat, weapon, sentence_years is not None]
    )
    if resolved < 2:
        return None

    parts: list[str] = []
    # Lead: institutional action + accused count + offence + district (§6b order).
    if arrested and count is not None:
        subject, verb = _count_phrase(count)
        parts.append(f"{subject} {verb} arrested{where} for the {offence_lc}.")
    elif arrested:
        parts.append(f"An arrest was made{where} for the {offence_lc}.")
    elif count is not None:
        subject, verb = _count_phrase(count)
        parts.append(f"{subject} {verb} accused of the {offence_lc}{where}.")
    else:
        parts.append(f"A case of {offence_lc}{where} was recorded.")

    # Aggravators (the cruelty of the ACT may be stated — never the victim).
    if weapon:
        parts.append("A weapon or threat was involved.")
    if repeat:
        parts.append("The accused is recorded as a repeat offender.")

    # Further institutional actions, in fixed order (arrest already stated in the lead).
    parts.extend(_ACTION_SENTENCE[a] for a in _ACTION_ORDER if a in actions)

    if sentence_years is not None:
        unit = "year" if sentence_years == 1 else "years"
        parts.append(f"The court imposed a sentence of {sentence_years} {unit}.")

    return " ".join(parts)
