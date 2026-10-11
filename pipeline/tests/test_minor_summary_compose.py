"""Tests for the child-case brief (#267): built only from structured facts, never model text."""

from __future__ import annotations

import re

from pipeline.charges import _PLAIN_CHARGES
from pipeline.minor_summary_compose import (
    _ACTION_SENTENCE,
    _COUNT_WORDS,
    _MONTHS,
    _STATUS_SENTENCE,
    compose,
)
from pipeline.sanitize import MINOR_WITHHELD_SENTENCE, minor_summary, minor_title
from pipeline.severity import SEVERITY_RULES

OFFENCE = "aggravated penetrative assault on a child"
WHERE = " in TESTVILLE, Telangana"


def test_reads_like_a_brief_in_the_order_things_happened() -> None:
    body = compose(
        {
            "incident_reported_date": "2013-06",
            "status": "ACQUITTED",
            "accused_count": 1,
            "institutional_actions": [
                "arrest_made",
                "chargesheet_filed",
                "convicted",
                "acquitted",
                "appeal_filed",
            ],
            "offence_sections": ["IPC 448", "IPC 506(I)", "POCSO 6"],
            "weapon_or_threat": True,
            "sentence_years": 10,
        },
        OFFENCE,
        WHERE,
    )
    assert body == (
        "In June 2013, one person was arrested in TESTVILLE, Telangana for the aggravated "
        "penetrative assault on a child. The charges also include house trespass and "
        "criminal intimidation. A weapon was used or a threat was made. Police have filed a "
        "chargesheet. The accused was convicted and sentenced to 10 years in prison, and "
        "later acquitted on appeal."
    )


def test_several_accused_convicted_with_a_sentence_each() -> None:
    body = compose(
        {
            "incident_reported_date": "2026-10",
            "status": "CONVICTED",
            "accused_count": 4,
            "institutional_actions": ["arrest_made", "convicted"],
            "sentence_years": 20,
        },
        OFFENCE,
        WHERE,
    )
    assert body.startswith("In October 2026, four people were arrested in TESTVILLE")
    assert body.endswith("The accused were convicted and sentenced each to 20 years in prison.")


def test_acquitted_then_convicted_on_appeal() -> None:
    body = compose(
        {
            "status": "CONVICTED",
            "institutional_actions": ["acquitted", "convicted", "appeal_filed"],
            "sentence_years": 1,
        },
        OFFENCE,
        "",
    )
    assert body.endswith(
        "The accused was first acquitted, and later convicted on appeal and sentenced to "
        "1 year in prison."
    )


def test_conflicting_verdicts_without_a_final_status_are_stated_plainly() -> None:
    body = compose(
        {"status": "APPEAL_PENDING", "institutional_actions": ["convicted", "acquitted"]},
        OFFENCE,
        "",
    )
    assert body.endswith("The accused was convicted at one stage and acquitted at another.")


def test_appeals_against_a_single_verdict() -> None:
    convicted = compose(
        {"status": "APPEAL_PENDING", "institutional_actions": ["convicted", "appeal_filed"]},
        OFFENCE,
        "",
    )
    assert convicted.endswith("An appeal against the verdict has been filed.")
    acquitted = compose(
        {"status": "ACQUITTED", "institutional_actions": ["acquitted", "appeal_filed"]},
        OFFENCE,
        "",
    )
    assert acquitted.endswith(
        "The accused was acquitted. An appeal against the acquittal has been filed."
    )


def test_lead_without_count_or_arrest_and_status_when_no_verdict() -> None:
    assert compose({"status": "UNDER_TRIAL"}, OFFENCE, WHERE) == (
        "A case of aggravated penetrative assault on a child was registered in TESTVILLE, "
        "Telangana. The case is under trial."
    )
    assert compose({"incident_reported_date": "2018"}, OFFENCE, "") == (
        "In 2018, a case of aggravated penetrative assault on a child was registered. "
        "The case status is not yet known."
    )
    arrest = compose(
        {"institutional_actions": ["arrest_made"], "status": "FIR_FILED"}, OFFENCE, WHERE
    )
    assert arrest.startswith("Police made an arrest in TESTVILLE, Telangana over the")
    accused = compose({"accused_count": 12, "repeat_offence": True}, OFFENCE, "")
    assert accused.startswith("12 people were accused of the aggravated")
    assert "The accused is recorded as a repeat offender." in accused


def test_no_repeated_status_and_other_steps() -> None:
    chargesheeted = compose(
        {"status": "CHARGESHEETED", "institutional_actions": ["chargesheet_filed", "sit_formed"]},
        OFFENCE,
        "",
    )
    assert chargesheeted.count("chargesheet") == 1
    assert (
        "A special investigation team was formed. Police have filed a chargesheet." in chargesheeted
    )
    sentence_only = compose({"sentence_years": 7}, OFFENCE, "")
    assert sentence_only.endswith("The court imposed a sentence of 7 years.")
    appeal = compose(
        {"status": "UNDER_TRIAL", "institutional_actions": ["appeal_filed"]}, OFFENCE, ""
    )
    assert appeal.endswith("The case is under trial. An appeal was filed.")


def test_bad_typed_fields_and_unknown_actions_are_ignored() -> None:
    body = compose(
        {
            "accused_count": True,
            "sentence_years": False,
            "institutional_actions": ["not_an_action", "bail_denied"],
            "incident_reported_date": "2026-13",
        },
        OFFENCE,
        "",
    )
    assert body == (
        "In 2026, a case of aggravated penetrative assault on a child was registered. "
        "Bail was denied. The case status is not yet known."
    )


def test_child_title_says_where_the_case_stands_and_fits() -> None:
    base = {
        "minor_involved": True,
        "category": "pocso",
        "state": "TG",
        "district": "TESTVILLE",
        "incident_reported_date": "2026",
        "offence_sections": ["POCSO 6"],
    }
    assert minor_title({**base, "status": "CONVICTED", "sentence_years": 20}) == (
        "Aggravated penetrative assault on a child — TESTVILLE (2026) — convicted, 20 years"
    )
    assert minor_title({**base, "status": "CONVICTED", "sentence_years": 1}).endswith(
        "convicted, 1 year"
    )
    assert minor_title(
        {**base, "status": "ACQUITTED", "institutional_actions": ["convicted", "appeal_filed"]}
    ).endswith("— acquitted on appeal")
    assert minor_title({**base, "status": "UNKNOWN"}).endswith("(2026)")  # nothing to add
    long_place = {**base, "district": "A Very Long District Name Indeed", "status": "UNDER_TRIAL"}
    assert len(minor_title(long_place)) <= 90 and "on trial" not in minor_title(long_place)
    unknown = {**base, "district": "Unknown", "status": "FIR_FILED"}
    assert (
        minor_title(unknown)
        == "Aggravated penetrative assault on a child — Telangana (2026) — FIR filed"
    )


def test_composed_summary_uses_only_allowed_tokens() -> None:
    """THE guarantee: every word in a child's summary comes from the fixed vocabulary, an
    offence or charge label, the place, a month, or a number. Never from model text."""
    fixed = " ".join(
        [
            *_ACTION_SENTENCE.values(),
            *_STATUS_SENTENCE.values(),
            *_COUNT_WORDS,
            *_MONTHS,
            *(plain for _code, _nums, plain in _PLAIN_CHARGES),
            "in people person was were arrested for the accused of a case registered police",
            "made an arrest over charges also include and weapon used or threat is recorded as",
            "repeat offender convicted sentenced each to year years prison later acquitted on",
            "appeal first at one stage another against verdict acquittal has been filed court",
            "imposed sentence",
            MINOR_WITHHELD_SENTENCE,
        ]
    )
    allowed = set(re.findall(r"[a-z]+", fixed.lower()))
    for label, _agg, _needles in SEVERITY_RULES:
        allowed |= set(re.findall(r"[a-z]+", label.lower()))
    allowed |= {"child", "minor", "sexual", "offence", "involving", "harassment", "acid", "attack"}
    allowed |= {"testville", "telangana", "s"}
    rec = {
        "minor_involved": True,
        "category": "pocso",
        "district": "TESTVILLE",
        "state": "TG",
        "status": "CONVICTED",
        "incident_reported_date": "2026-05",
        "offence_sections": ["POCSO 6", "IPC 363", "IPC 506"],
        "accused_count": 4,
        "institutional_actions": ["arrest_made", "chargesheet_filed", "convicted", "appeal_filed"],
        "weapon_or_threat": True,
        "repeat_offence": True,
        "sentence_years": 15,
    }
    summary = minor_summary(rec)
    unknown = sorted(w for w in re.findall(r"[a-z]+", summary.lower()) if w not in allowed)
    assert unknown == [], f"words outside the fixed vocabulary: {unknown}"
    assert set(re.findall(r"\d+", summary)) <= {"2026", "15", "23"}


def test_a_case_with_too_much_to_say_drops_the_least_important_lines_first() -> None:
    from pipeline.minor_summary_compose import MAX_BODY_CHARS

    body = compose(
        {
            "incident_reported_date": "2026-05",
            "status": "CONVICTED",
            "accused_count": 4,
            "institutional_actions": [
                "arrest_made",
                "sit_formed",
                "suspension_ordered",
                "chargesheet_filed",
                "bail_granted",
                "bail_denied",
                "convicted",
                "appeal_filed",
            ],
            "offence_sections": [
                "IPC 302",
                "IPC 307",
                "IPC 363",
                "IPC 366",
                "IPC 342",
                "IPC 328",
                "IPC 506",
                "IPC 201",
                "IPC 120B",
                "IT 67B",
                "POCSO 6",
            ],
            "weapon_or_threat": True,
            "repeat_offence": True,
            "sentence_years": 20,
        },
        "aggravated penetrative assault on a child with a very long name to push the length",
        " in A Very Long District Name, Telangana",
    )
    assert len(body) <= MAX_BODY_CHARS
    assert "Police have filed a chargesheet." in body  # kept
    assert body.endswith("An appeal against the verdict has been filed.")  # the outcome is kept
    assert "Bail was granted." not in body  # dropped first
