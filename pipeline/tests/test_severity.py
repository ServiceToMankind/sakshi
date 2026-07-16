"""Tests for the charge-section severity mapping (public-charge-derived, non-identifying)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.severity import (
    is_aggravated,
    is_repeat_offender,
    severity_label,
)

_RULES = json.loads(
    (
        Path(__file__).resolve().parent.parent.parent / "site" / "src" / "severity_rules.json"
    ).read_text()
)


@pytest.mark.parametrize(
    ("sections", "label", "aggravated"),
    [
        (["BNS 70(2)"], "Gang rape of a minor", True),
        (["BNS 70(1)"], "Gang rape", True),
        (["BNS 66"], "Rape resulting in death or persistent vegetative state", True),
        (["POCSO 6"], "Aggravated penetrative assault on a child", True),
        (["BNS 64", "IPC 376"], "Rape", False),
        (["IPC 354"], "Assault to outrage modesty", False),
        (["BNS 124"], "Acid attack", True),
        (["some unmatched section"], None, False),
        ([], None, False),
    ],
)
def test_severity_label_and_aggravated(
    sections: list[str], label: str | None, aggravated: bool
) -> None:
    assert severity_label(sections) == label
    assert is_aggravated(sections) == aggravated


def test_most_severe_rule_wins_when_multiple_match() -> None:
    """A gang-rape-of-a-minor charge outranks a plain rape charge on the same case."""
    assert severity_label(["IPC 376", "BNS 70(2)", "BNS 64"]) == "Gang rape of a minor"
    assert is_aggravated(["IPC 376", "BNS 70(2)"]) is True


def test_section_matching_is_space_and_case_insensitive() -> None:
    assert severity_label(["bns 70 (2)"]) == "Gang rape of a minor"
    assert severity_label(["Section 376 IPC"]) == "Rape"


@pytest.mark.parametrize(
    ("section", "label"),
    [
        # A shorter needle that PREFIXES a longer, more-specific section code must NOT
        # shadow it (boundary-aware matching — was the correctness-review Defect 1).
        ("IPC 376AB", "Rape of a minor"),  # not "…death…" (IPC 376A prefix)
        ("IPC 354C", "Voyeurism"),  # not "Assault…" (IPC 354 prefix)
        ("IPC 354D", "Stalking"),  # not "Assault…" (IPC 354 prefix)
        ("IPC 376A", "Rape resulting in death or persistent vegetative state"),
        ("IPC 376", "Rape"),
    ],
)
def test_needle_matching_respects_code_boundaries(section: str, label: str) -> None:
    assert severity_label([section]) == label


def test_repeat_offender_flag() -> None:
    assert is_repeat_offender(["BNS 64", "BNS 71"]) is True
    assert is_repeat_offender(["BNS 64"]) is False


def test_non_list_input_is_safe() -> None:
    assert severity_label(None) is None
    assert is_aggravated("BNS 64") is False  # a bare string is not a section list
    assert is_repeat_offender(None) is False


def test_rules_json_shape_is_stable() -> None:
    """The shared rules file the frontend also imports keeps its contract."""
    assert isinstance(_RULES["rules"], list) and _RULES["rules"]
    for rule in _RULES["rules"]:
        assert set(rule) >= {"label", "aggravated", "sections"}
        assert isinstance(rule["sections"], list) and rule["sections"]
    assert isinstance(_RULES["repeat_sections"], list)
