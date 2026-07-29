"""Tests for the deterministic offence-section normaliser (§4b)."""

from __future__ import annotations

from pipeline.offence_sections import normalize_sections, parse_section
from pipeline.severity import severity_label


def test_parse_section_act_and_number_variants() -> None:
    assert parse_section("IPC 376") == ("IPC", "376", "")
    assert parse_section("Section 376 IPC") == ("IPC", "376", "")
    assert parse_section("u/s 376 IPC") == ("IPC", "376", "")
    assert parse_section("bns 70 (2)") == ("BNS", "70", "(2)")
    assert parse_section("Section 70(2), BNS") == ("BNS", "70", "(2)")
    assert parse_section("POCSO s.6") == ("POCSO", "6", "")
    assert parse_section("POCSO Act") == ("POCSO", None, "")
    assert parse_section("376D") == (None, "376D", "")  # act-less real section
    assert parse_section("rape") == (None, None, "")  # junk


def test_normalize_dedups_and_canonicalises() -> None:
    canonical, unparsed = normalize_sections(["POCSO", "POCSO Act", "IPC 375"])
    assert canonical == ["POCSO", "IPC 375"]  # POCSO/POCSO Act collapse
    assert unparsed == []

    canonical, _ = normalize_sections(["Section 376 IPC", "IPC 376"])
    assert canonical == ["IPC 376"]  # reordered + canonical forms collapse


def test_normalize_separates_junk_into_unparsed_keeps_real_sections() -> None:
    """DL-000003-style grab-bag: real sections canonicalise; non-section tokens are
    surfaced in unparsed, never dropped silently."""
    canonical, unparsed = normalize_sections(
        ["rape", "sexual_assault", "PoCSO Act", "IPC 376(2)(i)", "POCSO 6", "BNS 70(1)"]
    )
    assert unparsed == ["rape", "sexual_assault"]
    assert "POCSO 6" in canonical and "BNS 70(1)" in canonical and "POCSO" in canonical


def test_act_less_sections_are_preserved_for_severity() -> None:
    """severity_rules.json has ACT-LESS needles (376D/326A/354D) — a bare section number is
    a real section and must survive normalisation so its severity still maps."""
    canonical, unparsed = normalize_sections(["376D", "326A", "354D"])
    assert canonical == ["376D", "326A", "354D"] and unparsed == []
    assert severity_label(canonical) == "Gang rape"  # 376D still labels


def test_normalisation_preserves_or_improves_severity() -> None:
    """Canonical output must map to the same (or a now-correct) severity label — never
    break the severity needles."""
    # reordered form did not match before; canonicalisation fixes it
    assert severity_label(["Section 70(2), BNS"]) is None
    canonical, _ = normalize_sections(["Section 70(2), BNS"])
    assert severity_label(canonical) == "Gang rape of a minor"


def test_normalize_is_idempotent() -> None:
    once, once_unparsed = normalize_sections(["POCSO Act", "bns 70 (2)", "junk"])
    assert once_unparsed == ["junk"]
    twice, twice_unparsed = normalize_sections(once)
    assert twice == once and twice_unparsed == []  # canonical input has no junk


def test_normalize_non_list_input() -> None:
    assert normalize_sections(None) == ([], [])
    assert normalize_sections("IPC 376") == ([], [])  # a bare string is not a sections list
