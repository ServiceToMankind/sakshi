"""Tests for canonical state-code normalisation."""

from __future__ import annotations

import pytest

from pipeline.states import CANONICAL_STATES, normalize_state


@pytest.mark.parametrize(
    ("code", "canonical"),
    [
        ("TS", "TG"),  # Telangana — the observed split
        ("ts", "TG"),  # case-insensitive
        (" TS ", "TG"),  # whitespace
        ("CG", "CT"),  # Chhattisgarh
        ("OR", "OD"),  # Odisha
        ("UK", "UT"),  # Uttarakhand
        ("TG", "TG"),  # already canonical
        ("UP", "UP"),
        ("XX", "XX"),  # unknown -> upper-cased as-is (a human catches a bad code)
        ("", ""),
    ],
)
def test_normalize_state(code: str, canonical: str) -> None:
    assert normalize_state(code) == canonical


def test_all_aliases_map_into_the_canonical_set() -> None:
    from pipeline.states import STATE_ALIASES

    for alias, canonical in STATE_ALIASES.items():
        assert canonical in CANONICAL_STATES
        assert alias not in CANONICAL_STATES  # an alias is never itself canonical
