"""Tests for the §4e multilingual PII guard (pipeline.pii_multilingual), issue #136.

Per-script fixtures prove each vector FIRES — the §4d/§4e enablement precondition — and that
plain English does NOT false-positive. All fixtures are synthetic (no real case, no PII in a
real shape): a placeholder victim word + a script's age/kinship term, never a real name.
"""

from __future__ import annotations

import pytest

from pipeline.pii_multilingual import (
    LANGUAGE_KINSHIP_TERMS,
    LANGUAGES,
    NATIVE_SCRIPT_AGE_PATTERNS,
    REDACTION_PLACEHOLDER,
    contains_native_script,
    find_multilingual_pii,
    find_native_scripts,
    matched_native_script,
    matched_romanized_pii,
    scrub_multilingual_pii,
    scrub_native_script,
)


def test_romanized_kinship_relation_is_flagged() -> None:
    # A romanized kinship term states the victim–accused relationship (forbidden, §1a).
    assert "romanized_kinship_relation" in find_multilingual_pii("arrested the girl's chacha")
    assert "romanized_kinship_relation" in find_multilingual_pii("the accused, her jija, was held")
    assert "romanized_kinship_relation" in find_multilingual_pii("the mama garu of the child")


def test_local_office_title_is_flagged() -> None:
    assert "local_office_title" in find_multilingual_pii("the village sarpanch was named")
    assert "local_office_title" in find_multilingual_pii("a complaint to the patwari")
    assert "local_office_title" in find_multilingual_pii("the gram pradhan was accused")


def test_subdistrict_geography_is_flagged() -> None:
    assert "subdistrict_geography" in find_multilingual_pii("in Rampur gaon near the school")
    assert "subdistrict_geography" in find_multilingual_pii("the thanda where it happened")
    assert "subdistrict_geography" in find_multilingual_pii("a tola in the block")


def test_word_boundary_does_not_match_inside_a_longer_word() -> None:
    # "gaon" must NOT match inside "gurgaon" (the grouping-boundary fix). A place-name
    # substring is not a sub-district marker.
    assert find_multilingual_pii("a case in Gurgaon district") == []
    assert matched_romanized_pii("https://x.invalid/gurgaon-child-case") == []
    # But a genuinely delimited marker still fires (hyphen is a non-word boundary).
    assert "subdistrict_geography" in matched_romanized_pii("the rampur-gaon-case")


def test_native_vs_romanized_split() -> None:
    # matched_native_script: only native-script / native-age vectors.
    assert matched_native_script("her chacha in Rampur gaon") == []  # romanized, not native
    assert "native_script:devanagari" in matched_native_script("पीड़िता")
    # matched_romanized_pii: only romanized markers, no native.
    assert matched_romanized_pii("पीड़िता १५ साल") == []
    assert "romanized_kinship_relation" in matched_romanized_pii("her chacha")


# --- Native-script detection (the English-output tripwire) -----------------------------------


@pytest.mark.parametrize(
    ("text", "script"),
    [
        ("पीड़िता का बयान", "devanagari"),  # Hindi/Marathi
        ("অভিযুক্ত ধরা পড়ে", "bengali"),  # Bengali/Assamese
        ("ਪੀੜਤ ਦਾ ਬਿਆਨ", "gurmukhi"),  # Punjabi
        ("પીડિતાનું નિવેદન", "gujarati"),  # Gujarati
        ("ପୀଡ଼ିତାର ବୟାନ", "oriya"),  # Odia
        ("பாதிக்கப்பட்டவர்", "tamil"),  # Tamil
        ("బాధితురాలి వాంగ్మూలం", "telugu"),  # Telugu
        ("ಸಂತ್ರಸ್ತೆಯ ಹೇಳಿಕೆ", "kannada"),  # Kannada
        ("ഇരയുടെ മൊഴി", "malayalam"),  # Malayalam
    ],
)
def test_native_script_is_detected_per_script(text: str, script: str) -> None:
    assert contains_native_script(text)
    assert script in find_native_scripts(text)
    assert f"native_script:{script}" in find_multilingual_pii(text)


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("पीड़िता १५ साल की थी", "hindi"),
        ("15 वर्ष", "hindi"),
        ("బాధితురాలికి 15 ఏళ్ల", "telugu"),
        ("15 வயது சிறுமி", "tamil"),
        ("15 বছর বয়সী", "bengali"),
        ("15 വയസ്സ്", "malayalam"),
        ("15 ವರ್ಷ", "kannada"),
        ("15 વર્ષ", "gujarati"),
        ("15 ਸਾਲ", "punjabi"),
        ("15 ବର୍ଷ", "odia"),
    ],
)
def test_native_script_age_is_flagged_per_script(text: str, lang: str) -> None:
    assert f"native_age:{lang}" in find_multilingual_pii(text)


# --- The ambiguity rule: English-ambiguous terms only fire under a language guard -------------


def test_ambiguous_terms_do_not_fire_in_the_always_on_scan() -> None:
    # "mama"/"anna"/"dada" are common English words — never flagged without a language.
    assert find_multilingual_pii("mama took the child to see grandpa") == []
    assert find_multilingual_pii("Anna and Dada went home") == []


def test_ambiguous_terms_fire_when_the_language_is_activated() -> None:
    # A §4d/D5 PR passes languages=(...) once its source language makes the term unambiguous.
    hits = find_multilingual_pii("the mama of the child", languages=("hindi",))
    assert "romanized_kinship_relation:hindi" in hits
    te = find_multilingual_pii("the akka reported it", languages=("telugu",))
    assert "romanized_kinship_relation:telugu" in te
    # An unknown language key is simply ignored (no crash, no hit).
    assert find_multilingual_pii("the mama", languages=("klingon",)) == []


def test_plain_english_does_not_false_positive() -> None:
    clean = (
        "A case of rape in South Delhi (2026). The accused was chargesheeted; "
        "the trial is under way at the district court."
    )
    assert find_multilingual_pii(clean) == []


def test_non_string_and_empty_are_safe() -> None:
    assert find_multilingual_pii("") == []
    assert find_multilingual_pii(None) == []  # type: ignore[arg-type]
    assert find_native_scripts("") == []
    assert contains_native_script("") is False


# --- The scrub (wired into sanitize.sanitize_string) -----------------------------------------


def test_scrub_redacts_native_script_and_romanized_markers() -> None:
    text = "The accused, her chacha, a sarpanch, in Rampur gaon; पीड़िता १५ साल."
    scrubbed = scrub_multilingual_pii(text)
    assert "chacha" not in scrubbed
    assert "sarpanch" not in scrubbed
    assert "gaon" not in scrubbed
    assert not contains_native_script(scrubbed)  # native script fully removed
    assert REDACTION_PLACEHOLDER in scrubbed


def test_scrub_native_script_only_touches_native() -> None:
    # The field-wide scrub (sanitize_string) removes native script but LEAVES romanized text
    # (a URL slug's place name must not be mangled — romanized is scrubbed in prose only).
    assert scrub_native_script("her chacha in Rampur gaon") == "her chacha in Rampur gaon"
    scrubbed = scrub_native_script("बयान 15 वर्ष")
    assert not contains_native_script(scrubbed)


def test_scrub_is_idempotent() -> None:
    text = "her jija in Rampur gaon; 15 वर्ष"
    once = scrub_multilingual_pii(text)
    assert scrub_multilingual_pii(once) == once


def test_scrub_leaves_plain_english_untouched() -> None:
    clean = "A case of rape in South Delhi. The accused was chargesheeted."
    assert scrub_multilingual_pii(clean) == clean


def test_scrub_non_string_and_empty_are_safe() -> None:
    assert scrub_multilingual_pii("") == ""
    assert scrub_multilingual_pii(None) is None  # type: ignore[arg-type]
    assert scrub_native_script("") == ""
    assert scrub_native_script(None) is None  # type: ignore[arg-type]


def test_redaction_placeholder_matches_sanitizer() -> None:
    # Parity: the multilingual scrub must reuse the sanitizer's placeholder so
    # sanitize_string stays idempotent (the placeholder matches no pattern).
    from pipeline.sanitize import REDACTION_PLACEHOLDER as SANITIZE_PLACEHOLDER

    assert REDACTION_PLACEHOLDER == SANITIZE_PLACEHOLDER


def test_languages_checklist_is_the_enablement_gate() -> None:
    # The LANGUAGES tuple is the per-language enablement checklist (one PR each, §4d/§4e).
    assert "hindi" in LANGUAGES and "telugu" in LANGUAGES and "tamil" in LANGUAGES
    assert len(LANGUAGES) >= 9
    # Every language with an ambiguous-kinship set is on the checklist.
    assert set(LANGUAGE_KINSHIP_TERMS).issubset(set(LANGUAGES))
    # Every language with a native-age pattern is on the checklist.
    assert set(NATIVE_SCRIPT_AGE_PATTERNS).issubset(set(LANGUAGES))


def test_telugu_guard_ready() -> None:
    # §4d TELUGU enablement readiness (#136): the wired guard fires on this language's vectors —
    # native script, a native-script age, and a romanized kinship term under the language guard.
    # The feed lands enabled:false; this proves the identity floor is ready first.
    assert "native_script:telugu" in find_multilingual_pii("బాధితురాలి వాంగ్మూలం")
    assert "native_age:telugu" in find_multilingual_pii("15 ఏళ్ల బాలిక")
    assert "romanized_kinship_relation:telugu" in find_multilingual_pii(
        "the akka reported it", languages=("telugu",)
    )


def test_marathi_guard_ready() -> None:
    # §4d MARATHI enablement readiness (#136): the wired guard fires on this language's
    # vectors — native script, a native-script age, and a romanized kinship term under the
    # language guard. The feed lands enabled:false; this proves the floor is ready first.
    assert "native_script:devanagari" in find_multilingual_pii("पीडितेचा जबाब")
    assert "native_age:hindi" in find_multilingual_pii("१५ वर्ष")
    assert "romanized_kinship_relation:marathi" in find_multilingual_pii(
        "the kaka of the child", languages=("marathi",)
    )


def test_tamil_guard_ready() -> None:
    # §4d TAMIL enablement readiness (#136): the wired guard fires on this language's
    # vectors — native script, a native-script age, and a romanized kinship term under the
    # language guard. The feed lands enabled:false; this proves the floor is ready first.
    assert "native_script:tamil" in find_multilingual_pii("பாதிக்கப்பட்டவர் வாக்குமூலம்")
    assert "native_age:tamil" in find_multilingual_pii("15 வயது சிறுமி")
    assert "romanized_kinship_relation:tamil" in find_multilingual_pii(
        "the akka reported it", languages=("tamil",)
    )


def test_bengali_guard_ready() -> None:
    # §4d BENGALI enablement readiness (#136): the wired guard fires on this language's
    # vectors — native script, a native-script age, and a romanized kinship term under the
    # language guard. The feed lands enabled:false; this proves the floor is ready first.
    assert "native_script:bengali" in find_multilingual_pii("অভিযুক্ত ধরা পড়েছে")
    assert "native_age:bengali" in find_multilingual_pii("15 বছর বয়সী")
    assert "romanized_kinship_relation:bengali" in find_multilingual_pii(
        "the dada of the child", languages=("bengali",)
    )
