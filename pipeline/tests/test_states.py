"""Tests for canonical state-code normalisation."""

from __future__ import annotations

import pytest

from pipeline.states import CANONICAL_STATES, STATE_NAMES, normalize_state, state_name


@pytest.mark.parametrize(
    ("code", "canonical"),
    [
        ("TS", "TG"),  # Telangana — the observed split
        ("TL", "TG"),  # Telangana mis-code (§4a — the observed SKS-2026-TL-000001 record)
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


def test_state_name_resolves_code_alias_and_unknown() -> None:
    assert state_name("HR") == "Haryana"
    assert state_name("TS") == "Telangana"  # alias normalised before lookup
    assert state_name("dl") == "Delhi"  # case-insensitive
    assert state_name("XX") == "XX"  # unknown -> upper-cased code passthrough
    assert state_name("") == ""


def test_every_canonical_state_has_a_name() -> None:
    assert set(STATE_NAMES) == set(CANONICAL_STATES)


def test_state_names_parity_with_frontend() -> None:
    """STATE_NAMES must match site/src/format.js exactly so a state reads the same on the
    site and in the pipeline's deterministic minor projection (CLAUDE.md §5 no-drift)."""
    import re
    from pathlib import Path

    fmt = (Path(__file__).resolve().parents[2] / "site" / "src" / "format.js").read_text()
    block = re.search(r"const STATE_NAMES = \{(.*?)\};", fmt, re.S)
    assert block is not None
    frontend = dict(re.findall(r"([A-Z]{2}):\s*'([^']+)'", block.group(1)))
    assert frontend == STATE_NAMES
