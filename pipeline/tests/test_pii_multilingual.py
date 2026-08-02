"""Tests for the §4e multilingual PII detection PROPOSAL (pipeline.pii_multilingual)."""

from __future__ import annotations

from pipeline.pii_multilingual import (
    LANGUAGES,
    find_multilingual_pii,
)


def test_romanized_kinship_relation_is_flagged() -> None:
    # A romanized kinship term states the victim–accused relationship (forbidden, §1a).
    assert "romanized_kinship_relation" in find_multilingual_pii("arrested the girl's chacha")
    assert "romanized_kinship_relation" in find_multilingual_pii("the accused, her jija, was held")
    assert "romanized_kinship_relation" in find_multilingual_pii("the mama garu of the child")


def test_local_office_title_is_flagged() -> None:
    assert "local_office_title" in find_multilingual_pii("the village sarpanch was named")
    assert "local_office_title" in find_multilingual_pii("a complaint to the patwari")


def test_subdistrict_geography_is_flagged() -> None:
    assert "subdistrict_geography" in find_multilingual_pii("in Rampur gaon near the school")
    assert "subdistrict_geography" in find_multilingual_pii("the thanda where it happened")


def test_native_script_age_is_flagged() -> None:
    # Devanagari age expression (defence-in-depth): digits + साल/वर्ष.
    assert "native_age:hindi" in find_multilingual_pii("पीड़िता १५ साल की थी")
    assert "native_age:hindi" in find_multilingual_pii("15 वर्ष")


def test_plain_english_does_not_false_positive() -> None:
    # A normal English summary (no distinctly-Indian kinship/office/geo term) must not fire —
    # ambiguous terms (mama, para, colony, nagar) were deliberately excluded from the lexicons.
    clean = (
        "A case of rape in South Delhi (2026). The accused was chargesheeted; "
        "the trial is under way at the district court."
    )
    assert find_multilingual_pii(clean) == []


def test_non_string_and_empty_are_safe() -> None:
    assert find_multilingual_pii("") == []
    assert find_multilingual_pii(None) == []  # type: ignore[arg-type]


def test_languages_checklist_is_the_enablement_gate() -> None:
    # The LANGUAGES tuple is the per-language enablement checklist (one PR each, §4d/§4e).
    assert "hindi" in LANGUAGES and "telugu" in LANGUAGES and "tamil" in LANGUAGES
    assert len(LANGUAGES) >= 9
