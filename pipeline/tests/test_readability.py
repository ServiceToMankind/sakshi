"""Tests for the deterministic non-minor readability gate (§6a)."""

from __future__ import annotations

from pipeline.readability import (
    MAX_WORDS_PER_SENTENCE,
    readability_violations,
    summary_is_readable,
)


def test_plain_summary_is_readable() -> None:
    plain = (
        "A cab driver was arrested for sexually assaulting a passenger. "
        "The incident occurred in Ranga Reddy district. "
        "Police apprehended the accused after the incident was reported."
    )
    assert readability_violations(plain) == []
    assert summary_is_readable(plain) is True


def test_legalese_terms_flagged() -> None:
    reasons = readability_violations(
        "The court stayed proceedings vide order in the instant matter; the petitioner appealed."
    )
    joined = " ".join(reasons)
    assert "stayed proceedings" in joined
    assert "vide order" in joined
    assert "the instant matter" in joined
    assert "petitioner" in joined


def test_abbreviated_and_section_citations_flagged() -> None:
    def reasons(text: str) -> str:
        return " ".join(readability_violations(text))

    assert "u/s" in reasons("Booked u/s 376 for the offence.")
    assert "section by number" in reasons("Charged under Section 376.")
    assert "section by number" in reasons("An FIR under IPC 376 was filed.")
    assert "section by number" in reasons("A POCSO 6 case was registered.")


def test_long_sentence_flagged() -> None:
    long_sentence = "word " * (MAX_WORDS_PER_SENTENCE + 1)
    reasons = readability_violations(long_sentence.strip() + ".")
    assert any("exceeds" in r for r in reasons)
    # A sentence exactly at the limit is fine.
    ok = "word " * MAX_WORDS_PER_SENTENCE
    assert readability_violations(ok.strip() + ".") == []


def test_non_string_summary_is_clean() -> None:
    assert readability_violations(None) == []
    assert readability_violations(123) == []
