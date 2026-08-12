"""Tests for the §2 media offence-language pre-filter (high recall, tiered).

Fixtures are synthetic offence headlines (no real names) in each enabled language's native
script, plus general-news negatives that must NOT fire. The recall of the real term sets was
measured separately over 1064 live media documents (docs/offence-filter-recall.md).
"""

from __future__ import annotations

import pytest

from pipeline.offence_filter import (
    LANGUAGES_WITH_TERMS,
    media_offence_hit,
    offence_term_languages,
)


@pytest.mark.parametrize(
    "text",
    [
        # English
        "Man held for raping a minor girl in the city",
        "Two get 20 years for gang-rape",
        "College student sexually assaulted; driver arrested",
        "Accused booked under POCSO Act",
        "Woman alleges sexual harassment at office",
        # Hindi (Devanagari)
        "नाबालिग से दुष्कर्म, आरोपी गिरफ्तार — पॉक्सो एक्ट के तहत केस दर्ज",
        "सामूहिक बलात्कार के बाद हत्या, इलाके में दहशत",
        # Telugu
        "మైనర్ బాలికపై అత్యాచారం.. నిందితుడి అరెస్ట్",
        "చిన్నారిపై లైంగిక దాడి.. పోక్సో కేసు నమోదు",
        # Marathi (Devanagari)
        "अल्पवयीन मुलीवर बलात्कार, आरोपीला अटक",
        "विनयभंग प्रकरणी गुन्हा दाखल",
        # Tamil
        "சிறுமியை கற்பழித்த வழக்கில் கைது",
        "பள்ளி மாணவியிடம் பாலியல் தொல்லை; ஆசிரியர் மீது போக்சோ வழக்கு",
    ],
)
def test_offence_headlines_are_flagged(text: str) -> None:
    assert media_offence_hit(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Sensex falls 200 points as markets stay volatile",
        "Chief minister inaugurates new metro line in the capital",
        # a girl/student mention with NO offence must not fire (trimmed person-nouns)
        "బాలిక టేబుల్ టెన్నిస్ ఛాంపియన్‌షిప్‌లో విజేత",  # girl wins table tennis (Telugu)
        "இளம்பெண் விபத்தில் உயிரிழப்பு",  # young woman dies in accident (Tamil)
        "शाळकरी मुलगी शिष्यवृत्ती परीक्षेत पहिली",  # school girl tops scholarship exam (Marathi)
    ],
)
def test_non_offence_text_is_not_flagged(text: str) -> None:
    assert media_offence_hit(text) is False


def test_roman_terms_are_word_boundaried() -> None:
    # "rape" must not fire inside "grape"; "minor" is not a bare term at all.
    assert media_offence_hit("fresh grape harvest season begins") is False
    assert media_offence_hit("a minor injury was reported") is False


def test_statute_patterns_are_retained_as_hits() -> None:
    # A media report that cites a section still passes (defence in depth).
    assert media_offence_hit("chargesheet filed under IPC 376") is True


def test_offence_term_languages_reports_native_matches() -> None:
    langs = offence_term_languages("మైనర్ బాలికపై అత్యాచారం")
    assert "telugu" in langs
    assert offence_term_languages("Sensex falls 200 points") == []


def test_non_string_is_safe() -> None:
    assert media_offence_hit(None) is False  # type: ignore[arg-type]
    assert offence_term_languages(None) == []  # type: ignore[arg-type]


def test_languages_with_terms_is_the_enablement_gate() -> None:
    # A media feed in a language NOT listed here must stay enabled:false (§4).
    assert set(LANGUAGES_WITH_TERMS) == {"hindi", "telugu", "marathi", "tamil"}
