"""Synthetic tests for the PII sanitizer (the last gate before disk).

All values here are obviously fake (district "TESTVILLE", fake Aadhaar, fake
email). They assert the guardrail behaviour and are held to 100% BRANCH coverage
in ``make check`` -- the sanitizer is a legally mandated Phase 0 safety gate.
"""

from __future__ import annotations

import json

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
        "minor_involved": False,  # non-minor: no projection, scalars pass through
        "pending_days": 25,
    }
    clean = sanitize_record(dirty)
    assert "email" not in clean["court"]
    assert clean["court"]["name"] == "Special POCSO Court, TESTVILLE"
    assert "phone" not in clean["accused"][0]
    assert clean["accused"][0]["label"] == "Accused #1"
    assert clean["minor_involved"] is False
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


# --- minor-record projection (issue #7) --------------------------------------

# The exact shape of the first supervised run's leaking record (SKS-2026-DL-000001),
# synthetic-ified: TESTVILLE district, example.invalid source. Its age lives in the
# free-text summary, so it ESCAPES the forbidden-field and PII-value gates — the
# structural minor projection is what removes it.
_MINOR_LEAK = {
    "category": "rape",
    "confidence": 0.85,
    "district": "TESTVILLE",
    "id": "SKS-2026-TG-000001",
    "incident_reported_date": "2026-07-05",
    "minor_involved": True,
    "pending_days": 5,
    "status": "UNKNOWN",
    "status_history": [{"status": "FIR_FILED", "date": "2026-07-05", "source": 0}],
    "court": {"name": "Special POCSO Court, TESTVILLE", "next_hearing": "2026-08-02"},
    "summary": "Police rescued a 17-year-old who had been kidnapped; the accused was arrested.",
    "sources": [
        {
            "url": "https://example.invalid/live-updates-x",
            "publisher": "The Example Herald",
            "source_type": "live_blog",
            "retrieved": "2026-07-09",
        }
    ],
}


def test_minor_projection_replaces_age_narrative_and_truncates_dates() -> None:
    """A minor record's age-bearing narrative and day/age-precise fields are projected."""
    clean = sanitize_record(_MINOR_LEAK)
    # Title + summary are deterministic, non-identifying, and carry the legal sentence.
    assert clean["summary"].endswith("Identifying details are withheld by law (POCSO s.23).")
    assert "17-year-old" not in clean["summary"]  # model narrative gone
    assert "involving a minor" in clean["title"]
    assert "17-year-old" not in clean["title"]
    assert clean["incident_reported_date"] == "2026"  # year granularity only
    assert clean["pending_days"] is None  # not stored for a minor
    assert clean["court"]["next_hearing"] is None
    assert clean["status_history"][0]["date"] == "2026-07"  # YYYY-MM, day dropped
    assert clean["minor_involved"] is True


def test_minor_projection_is_idempotent() -> None:
    once = sanitize_record(_MINOR_LEAK)
    assert sanitize_record(once) == once


def test_minor_projection_drops_model_verification_note() -> None:
    """Guardrail L / POCSO s.23: the verifier's model-written free-text note is never
    part of a minor's allowed shape and pii_guard does not age-scan it — so the minor
    projection drops it (canonical home; issue #44). A leaky note never reaches disk."""
    rec = {
        "minor_involved": True,
        "state": "TG",
        "district": "TESTVILLE",
        "category": "pocso",
        "status": "FIR_FILED",
        "verified": True,
        "verification_note": "Corroborated; the 17-year-old survivor's school confirmed it.",
    }
    clean = sanitize_record(rec)
    assert "verification_note" not in clean  # model free text dropped for the minor
    assert "17-year-old" not in json.dumps(clean)  # the age never survives
    assert clean["verified"] is True  # the boolean flag itself is retained


def test_minor_projection_absent_optional_fields_only_forces_title_and_summary() -> None:
    """With the optional day/age fields absent, title + summary are still generated."""
    minimal = {"minor_involved": True, "state": "TG", "district": "TESTVILLE"}
    clean = sanitize_record(minimal)
    assert clean["summary"].endswith("Identifying details are withheld by law (POCSO s.23).")
    assert "involving a minor" in clean["title"]
    assert "incident_reported_date" not in clean
    assert "pending_days" not in clean
    assert "court" not in clean
    assert "status_history" not in clean


def test_minor_projection_court_without_next_hearing_is_untouched() -> None:
    rec = {"minor_involved": True, "court": {"name": "Special POCSO Court, TESTVILLE"}}
    clean = sanitize_record(rec)
    assert clean["court"] == {"name": "Special POCSO Court, TESTVILLE"}


def test_minor_projection_status_entry_without_date_is_untouched() -> None:
    rec = {
        "minor_involved": True,
        "status_history": [
            {"status": "FIR_FILED", "date": "2026-07-05", "source": 0},  # truncated
            {"status": "UNKNOWN", "source": 1},  # no date -> returned as-is
        ],
    }
    clean = sanitize_record(rec)
    assert clean["status_history"][0]["date"] == "2026-07"
    assert clean["status_history"][1] == {"status": "UNKNOWN", "source": 1}


def test_non_minor_record_is_not_projected() -> None:
    """minor_involved False leaves the narrative and full-precision dates intact."""
    rec = {
        "minor_involved": False,
        "incident_reported_date": "2026-07-05",
        "pending_days": 5,
        "summary": "A neutral non-graphic summary of a reported adult case.",
    }
    clean = sanitize_record(rec)
    assert clean["incident_reported_date"] == "2026-07-05"
    assert clean["pending_days"] == 5
    assert clean["summary"] == "A neutral non-graphic summary of a reported adult case."
