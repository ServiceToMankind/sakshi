"""Tests for deterministic district canonicalisation (pipeline.districts)."""

from __future__ import annotations

from pipeline.districts import ALIASES, canonical_district


def test_known_renames_are_canonicalised() -> None:
    assert canonical_district("Gurgaon") == "Gurugram"
    assert canonical_district("Bangalore") == "Bengaluru"


def test_alias_match_is_case_and_whitespace_insensitive() -> None:
    assert canonical_district("  gurgaon ") == "Gurugram"
    assert canonical_district("BANGALORE") == "Bengaluru"


def test_south_district_is_left_unmapped() -> None:
    # "South District" is an official Delhi district name; folding it into "South Delhi"
    # would collide two distinct anchor-less minor cases under weak-anchor dedupe.
    assert canonical_district("South District") == "South District"


def test_unknown_district_passes_through_trimmed() -> None:
    # Never invent or mis-map: an unknown value is only whitespace-normalised.
    assert canonical_district("  Hyderabad ") == "Hyderabad"
    assert canonical_district("Ranga  Reddy") == "Ranga Reddy"


def test_non_string_and_empty_yield_empty() -> None:
    assert canonical_district(None) == ""
    assert canonical_district("") == ""
    assert canonical_district("   ") == ""
    assert canonical_district(123) == ""


def test_aliases_are_lowercased_keys() -> None:
    # The table is matched case-insensitively, so every key must already be lower-cased.
    assert all(k == k.lower() for k in ALIASES)
