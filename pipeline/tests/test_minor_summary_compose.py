"""Tests for the deterministic minor-summary composer (§6b), including the token guarantee."""

from __future__ import annotations

import re

from pipeline.minor_summary_compose import _ACTION_SENTENCE, _COUNT_WORDS, compose
from pipeline.sanitize import MINOR_WITHHELD_SENTENCE, minor_summary
from pipeline.severity import SEVERITY_RULES


def test_compose_returns_none_below_two_facts() -> None:
    assert compose({"accused_count": 3}, "rape of a minor", " in TESTVILLE") is None  # 1 fact
    assert compose({}, "rape of a minor", "") is None  # 0 facts


def test_compose_lead_arrest_with_count() -> None:
    body = compose(
        {"accused_count": 3, "institutional_actions": ["arrest_made", "chargesheet_filed"]},
        "aggravated sexual assault of a child",
        " in TESTVILLE",
    )
    assert body is not None
    assert body.startswith(
        "Three people were arrested in TESTVILLE for the aggravated sexual assault of a child."
    )
    assert "Police have filed a chargesheet." in body


def test_compose_singular_grammar_and_sentence_and_aggravators() -> None:
    body = compose(
        {
            "accused_count": 1,
            "institutional_actions": ["arrest_made", "convicted"],
            "weapon_or_threat": True,
            "repeat_offence": True,
            "sentence_years": 1,
        },
        "rape of a minor",
        " in TESTVILLE",
    )
    assert body is not None
    assert "One person was arrested in TESTVILLE" in body
    assert "A weapon or threat was involved." in body
    assert "The accused is recorded as a repeat offender." in body
    assert "The accused was convicted." in body
    assert "The court imposed a sentence of 1 year." in body  # singular "year"


def test_compose_accused_without_arrest_and_large_count() -> None:
    body = compose({"accused_count": 12, "weapon_or_threat": True}, "rape of a minor", "")
    assert body is not None
    assert body.startswith("12 people were accused of the rape of a minor.")


def test_compose_no_arrest_no_count_lead() -> None:
    body = compose(
        {"institutional_actions": ["sit_formed"], "repeat_offence": True},
        "sexual assault of a child",
        " in TESTVILLE",
    )
    assert body is not None
    assert body.startswith("A case of sexual assault of a child in TESTVILLE was recorded.")


def test_compose_arrest_without_count() -> None:
    body = compose(
        {"institutional_actions": ["arrest_made"], "weapon_or_threat": True},
        "rape of a minor",
        " in TESTVILLE",
    )
    assert body is not None
    assert body.startswith("An arrest was made in TESTVILLE for the rape of a minor.")


def test_compose_ignores_bad_typed_fields() -> None:
    # accused_count as a bool or <1, sentence as a bool, junk action -> not counted.
    assert compose({"accused_count": True, "sentence_years": False}, "rape of a minor", "") is None
    body = compose(
        {
            "accused_count": 0,
            "institutional_actions": ["not_an_enum", "bail_denied"],
            "weapon_or_threat": True,
        },
        "rape of a minor",
        "",
    )
    assert body is not None
    assert "Bail was denied." in body


def test_composed_summary_uses_only_allowed_tokens() -> None:
    """THE guarantee (§6b): every token in a composed minor summary is derived from the fixed
    composer vocabulary, a severity/offence label, the district, or a number — never model text."""
    allowed: set[str] = set()
    # Fixed composer vocabulary.
    fixed = (
        " ".join(_ACTION_SENTENCE.values())
        + " ".join(_COUNT_WORDS)
        + " people person was were arrested for the accused of a case recorded"
        + " A weapon or threat was involved The is as repeat offender court imposed"
        + " sentence year years"
        + " An arrest made in of the"
        + " "
        + MINOR_WITHHELD_SENTENCE
    )
    allowed |= set(re.findall(r"[A-Za-z]+", fixed.lower()))
    # Every word that can appear in a severity/category offence label.
    for label, _agg, _needles in SEVERITY_RULES:
        allowed |= set(re.findall(r"[A-Za-z]+", label.lower()))
    allowed |= {"child", "minor", "sexual", "offence", "involving", "harassment", "acid", "attack"}
    district = "TESTVILLE"
    allowed.add(district.lower())

    rec = {
        "minor_involved": True,
        "category": "pocso",
        "district": district,
        "state": "TG",
        "status": "CONVICTED",
        "incident_reported_date": "2026",
        "offence_sections": ["POCSO 6"],
        "accused_count": 4,
        "institutional_actions": ["arrest_made", "chargesheet_filed", "convicted", "appeal_filed"],
        "weapon_or_threat": True,
        "repeat_offence": True,
        "sentence_years": 15,
    }
    summary = minor_summary(rec)
    words = re.findall(r"[A-Za-z]+", summary.lower())
    unknown = sorted(w for w in words if w not in allowed)
    assert unknown == [], f"non-vocabulary tokens in composed minor summary: {unknown}"
    # And no digit that is not the accused count, the sentence length, or the POCSO citation.
    assert set(re.findall(r"\d+", summary)) <= {"4", "15", "23"}
