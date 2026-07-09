"""Synthetic tests for the PII sanitizer (the last gate before disk).

All values here are obviously fake (district "TESTVILLE", fake Aadhaar, fake
email). They assert the guardrail behaviour and are held to 100% BRANCH coverage
in ``make check`` -- the sanitizer is a legally mandated Phase 0 safety gate.
"""

from __future__ import annotations

from pipeline.pii_constants import is_forbidden_key, matched_value_patterns
from pipeline.sanitize import (
    REDACTION_PLACEHOLDER,
    contains_pii,
    sanitize_record,
    sanitize_string,
)

# --- Constants layer ---------------------------------------------------------


def test_forbidden_key_exact_and_substring() -> None:
    """Canonical forbidden names and any key containing victim/survivor are caught."""
    assert is_forbidden_key("victim_name")
    assert is_forbidden_key("VICTIM_NAME")  # case-insensitive
    assert is_forbidden_key("address")
    assert is_forbidden_key("primary_survivor_notes")  # substring
    assert not is_forbidden_key("district")
    assert not is_forbidden_key("status")


def test_pii_value_patterns_match_synthetic_values() -> None:
    """Synthetic Aadhaar / mobile / email / PAN strings are recognised."""
    assert matched_value_patterns("1234 5678 9012") == ["aadhaar"]
    assert matched_value_patterns("test@testville.example") == ["email"]
    assert matched_value_patterns("ABCDE1234F") == ["pan"]
    assert "indian_mobile" in matched_value_patterns("+91 9876543210")
    assert matched_value_patterns("Special POCSO Court, TESTVILLE") == []


# --- sanitize_record ---------------------------------------------------------


def test_sanitize_drops_forbidden_field_keeps_clean_ones() -> None:
    """A forbidden key must not survive; clean sibling keys are preserved."""
    dirty = {"district": "TESTVILLE", "victim_name": "SHOULD NOT PERSIST"}
    clean = sanitize_record(dirty)
    assert "victim_name" not in clean
    assert clean["district"] == "TESTVILLE"


def test_sanitize_recurses_into_dicts_lists_and_leaves_scalars() -> None:
    """Nested dicts/lists are recursed; non-string scalars pass through unchanged."""
    dirty = {
        "court": {"name": "Special POCSO Court, TESTVILLE", "email": "clerk@testville.example"},
        "accused": [{"label": "Accused #1", "phone": "9876543210"}],
        "minor_involved": True,
        "pending_days": 25,
    }
    clean = sanitize_record(dirty)
    assert "email" not in clean["court"]
    assert clean["court"]["name"] == "Special POCSO Court, TESTVILLE"
    assert "phone" not in clean["accused"][0]
    assert clean["accused"][0]["label"] == "Accused #1"
    assert clean["minor_involved"] is True
    assert clean["pending_days"] == 25


def test_sanitize_is_idempotent() -> None:
    """Sanitising an already-clean record is a no-op."""
    dirty = {"summary": "Neutral note; reach test@testville.example please."}
    once = sanitize_record(dirty)
    twice = sanitize_record(once)
    assert once == twice
    assert "test@testville.example" not in once["summary"]


# --- sanitize_string ---------------------------------------------------------


def test_sanitize_string_redacts_pii_spans() -> None:
    """A stray Aadhaar/email in free text is redacted, not persisted verbatim."""
    scrubbed = sanitize_string("contact test@testville.example or 1234 5678 9012")
    assert "test@testville.example" not in scrubbed
    assert "1234 5678 9012" not in scrubbed
    assert REDACTION_PLACEHOLDER in scrubbed


def test_sanitize_string_leaves_clean_text_untouched() -> None:
    """Neutral prose with no PII is returned verbatim."""
    text = "Case pending before the Special POCSO Court, TESTVILLE."
    assert sanitize_string(text) == text


# --- contains_pii ------------------------------------------------------------


def test_contains_pii_for_keys_values_and_non_strings() -> None:
    """Forbidden key names and PII-shaped values are flagged; non-strings are clean."""
    assert contains_pii("victim_name")  # forbidden key name
    assert contains_pii("test@testville.example")  # PII value
    assert not contains_pii("district")  # clean string
    assert not contains_pii(25)  # non-string
