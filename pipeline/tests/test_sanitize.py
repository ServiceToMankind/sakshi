"""Synthetic tests for the PII sanitizer (the last gate before disk).

All values here are obviously fake (district "TESTVILLE", fake Aadhaar, fake
email). They assert the guardrail behaviour and are held to 100% BRANCH coverage
in ``make check`` -- the sanitizer is a legally mandated Phase 0 safety gate.
"""

from __future__ import annotations

import json

from pipeline.pii_constants import (
    OCCUPATION_REDACTION,
    is_forbidden_key,
    is_occupation_scanned_key,
    matched_value_patterns,
    matched_victim_occupation,
    scrub_victim_occupation,
)
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


def test_sanitize_scrubs_multilingual_markers_from_nonminor_prose() -> None:
    """§4e (issue #136): a romanized identity marker in the model prose is redacted, and any
    native-script span is redacted field-wide — but a place-name slug in a URL is untouched."""
    dirty = {
        "minor_involved": False,
        "title": "Accused, her chacha, held",
        "summary": "The sarpanch of Rampur gaon was named; बयान दर्ज.",
        "sources": [{"url": "https://x.invalid/gurgaon-child-case-101/"}],
    }
    clean = sanitize_record(dirty)
    assert "chacha" not in clean["title"]
    assert "sarpanch" not in clean["summary"] and "gaon" not in clean["summary"]
    assert "बयान" not in clean["summary"]  # native script removed
    # The citation URL's place-name slug ("gurgaon") is NOT mangled.
    assert clean["sources"][0]["url"] == "https://x.invalid/gurgaon-child-case-101/"


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
        "days_since_reported": 25,
    }
    clean = sanitize_record(dirty)
    assert "email" not in clean["court"]
    assert clean["court"]["name"] == "Special POCSO Court, TESTVILLE"
    assert "phone" not in clean["accused"][0]
    assert clean["accused"][0]["label"] == "Accused #1"
    assert clean["minor_involved"] is False
    assert clean["days_since_reported"] == 25


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
    "days_since_reported": 5,
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
    assert clean["incident_reported_date"] == "2026-07"  # month granularity (§2)
    assert clean["days_since_reported"] is None  # not stored for a minor
    assert clean["court"]["next_hearing"] is None
    assert clean["status_history"][0]["date"] == "2026-07"  # YYYY-MM, day dropped
    assert clean["minor_involved"] is True


def test_minor_projection_is_idempotent() -> None:
    once = sanitize_record(_MINOR_LEAK)
    assert sanitize_record(once) == once


def test_minor_summary_states_offence_from_child_severity_label() -> None:
    """§6: a minor's deterministic summary/title now name the plain-English offence derived
    from PUBLIC charge sections (§1a permits severity for minors). A child-severity label is
    used verbatim (it already conveys the minor)."""
    rec = {
        "minor_involved": True,
        "category": "pocso",
        "district": "TESTVILLE",
        "state": "TG",
        "status": "FIR_FILED",
        "incident_reported_date": "2026",
        "offence_sections": ["POCSO 6"],
    }
    clean = sanitize_record(rec)
    assert "aggravated penetrative assault on a child" in clean["summary"].lower()
    assert clean["title"].startswith("Aggravated penetrative assault on a child")
    assert "An FIR has been filed" in clean["summary"]
    assert clean["summary"].endswith("Identifying details are withheld by law (POCSO s.23).")
    assert "involving a minor" not in clean["title"]  # label already says "child"


def test_minor_summary_appends_minor_for_generic_severity_label() -> None:
    """A generic severity label (e.g. 'Rape' from BNS 64) gets 'involving a minor' appended
    so the child context is never lost."""
    rec = {
        "minor_involved": True,
        "category": "rape",
        "district": "TESTVILLE",
        "state": "TG",
        "status": "UNDER_TRIAL",
        "incident_reported_date": "2026",
        "offence_sections": ["BNS 64"],
    }
    clean = sanitize_record(rec)
    assert "Rape involving a minor" in clean["title"]
    assert "a case of rape involving a minor" in clean["summary"].lower()


def test_minor_summary_falls_back_to_category_without_sections() -> None:
    """With no charge sections (no severity), the coarse category carries the offence; a
    generic category gets 'involving a minor' appended."""
    rec = {
        "minor_involved": True,
        "category": "sexual_assault",
        "district": "TESTVILLE",
        "state": "HR",
        "status": "UNDER_TRIAL",
        "incident_reported_date": "2026",
        "offence_sections": [],
    }
    clean = sanitize_record(rec)
    assert "Sexual assault involving a minor" in clean["title"]
    assert "sexual assault involving a minor" in clean["summary"].lower()


def test_minor_summary_uses_structured_composer_when_facts_resolve() -> None:
    """§6b: a minor with >=2 structured facts gets the richer deterministic composition; the
    non-identifying structured fields survive the minor projection; accused (names) do not."""
    rec = {
        "minor_involved": True,
        "category": "pocso",
        "district": "Kothagudem",
        "state": "TG",
        "status": "CHARGESHEETED",
        "incident_reported_date": "2026",
        "offence_sections": ["POCSO 6"],
        "accused_count": 3,
        "institutional_actions": ["arrest_made", "chargesheet_filed"],
        "accused": [
            {"label": "A1", "name_public_court_record": "Some Name", "status": "CHARGESHEETED"}
        ],
    }
    clean = sanitize_record(rec)
    assert clean["summary"].startswith(
        "Three people were arrested in Kothagudem for the aggravated penetrative assault"
    )
    assert "Police have filed a chargesheet." in clean["summary"]
    assert clean["summary"].endswith("Identifying details are withheld by law (POCSO s.23).")
    assert clean["accused_count"] == 3  # non-identifying structured fact kept
    assert clean["institutional_actions"] == ["arrest_made", "chargesheet_filed"]
    assert "accused" not in clean  # accused (with a NAME) is still stripped for a minor
    assert "Some Name" not in json.dumps(clean)


def test_minor_summary_child_category_without_sections_is_not_redundant() -> None:
    """A category that already says 'child' (pocso) with no sections must NOT get a
    redundant 'involving a minor' appended."""
    rec = {
        "minor_involved": True,
        "category": "pocso",
        "district": "TESTVILLE",
        "state": "TG",
        "status": "FIR_FILED",
        "incident_reported_date": "2026",
        "offence_sections": [],
    }
    clean = sanitize_record(rec)
    assert clean["title"].startswith("Child sexual offence —")
    assert "involving a minor" not in clean["title"]


def test_minor_projection_drops_accused() -> None:
    """POCSO s.23 / issue #55: a minor's record never carries an accused — naming an
    offender in a child case is a re-identification vector (accused↔victim proximity)."""
    rec = {
        "minor_involved": True,
        "state": "TG",
        "district": "TESTVILLE",
        "category": "pocso",
        "status": "CONVICTED",
        "accused": [
            {"label": "Accused #1", "name_public_court_record": "A. Person", "status": "CONVICTED"}
        ],
    }
    clean = sanitize_record(rec)
    assert "accused" not in clean  # stripped entirely
    assert "A. Person" not in json.dumps(clean)  # the court name never survives


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
    assert "days_since_reported" not in clean
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
        "days_since_reported": 5,
        "summary": "A neutral non-graphic summary of a reported adult case.",
    }
    clean = sanitize_record(rec)
    assert clean["incident_reported_date"] == "2026-07-05"
    assert clean["days_since_reported"] == 5
    assert clean["summary"] == "A neutral non-graphic summary of a reported adult case."


# --- §4d victim occupation / institution scrub -------------------------------


def test_victim_occupation_is_scrubbed_from_summary() -> None:
    """The observed live leak: a victim occupation + employer is redacted, while the
    ACCUSED's occupation/action prose survives."""
    rec = {
        "minor_involved": False,
        "title": "Driver arrested for office cab rape",
        "summary": (
            "A driver was arrested. He allegedly raped an IndiGo cabin crew member "
            "inside an office cab."
        ),
    }
    clean = sanitize_record(rec)
    assert "cabin crew member" not in clean["summary"]
    assert "IndiGo" not in clean["summary"]
    assert OCCUPATION_REDACTION in clean["summary"]
    assert "driver was arrested" in clean["summary"]  # accused action kept
    assert clean["title"] == "Driver arrested for office cab rape"  # accused occupation kept


def test_victim_occupation_scrub_covers_title_and_institution_tail() -> None:
    rec = {
        "minor_involved": False,
        "title": "A nurse was assaulted",  # victim occupation in the title
        "summary": "The survivor, a student at St Xavier School, was attacked.",
    }
    clean = sanitize_record(rec)
    assert "nurse" not in clean["title"] and OCCUPATION_REDACTION in clean["title"]
    assert "student" not in clean["summary"] and "St Xavier School" not in clean["summary"]


def test_accused_occupation_is_kept() -> None:
    """The accused's occupation is public — never scrubbed (accused verb/noun context)."""
    for summary in (
        "The accused, a teacher, was convicted.",  # accused verb after
        "A nurse was arrested for abetting the crime.",  # accused verb after, no assault
        "The convict, a doctor, is now in jail.",  # accused noun before, no verb after
    ):
        rec = {"minor_involved": False, "title": "Case", "summary": summary}
        assert sanitize_record(rec)["summary"] == summary


def test_headline_style_and_predicate_victim_occupation_scrubbed() -> None:
    """Article-less headline phrasing and a bare predicate occupation (no assault/accused
    verb adjacent) both default to redaction — the fail-toward-redaction branch."""
    head = sanitize_record(
        {"minor_involved": False, "title": "Techie raped in Hyderabad", "summary": "x"}
    )
    assert "Techie" not in head["title"] and OCCUPATION_REDACTION in head["title"]
    pred = sanitize_record(
        {"minor_involved": False, "title": "Case", "summary": "The survivor was a teacher."}
    )
    assert "teacher" not in pred["summary"]  # default redact: no accused signal present


def test_minor_record_occupation_scrub_is_skipped_but_projection_removes_it() -> None:
    """A minor's title/summary are replaced wholesale by the projection, so a victim
    occupation cannot survive even though the occupation scrub does not run on minors."""
    rec = {
        "minor_involved": True,
        "category": "pocso",
        "state": "TG",
        "district": "TESTVILLE",
        "status": "FIR_FILED",
        "summary": "A student nurse was assaulted.",  # model prose — must be replaced
    }
    clean = sanitize_record(rec)
    assert "nurse" not in clean["summary"]
    assert "withheld by law" in clean["summary"]  # deterministic minor projection


def test_scrub_occupation_fields_ignores_non_string_values() -> None:
    """A non-str title (None) is left untouched by the occupation scrub (branch coverage);
    a clean summary passes through unchanged."""
    rec = {"minor_involved": False, "title": None, "summary": "A neutral summary."}
    clean = sanitize_record(rec)
    assert clean["title"] is None  # non-str: scrub skips it (and str(None) is truthy)
    assert clean["summary"] == "A neutral summary."


def test_occupation_scrub_is_idempotent() -> None:
    once = scrub_victim_occupation("He raped a nurse near the market.")
    assert scrub_victim_occupation(once) == once  # placeholder carries no occupation term


def test_matched_victim_occupation_and_scanned_key_helpers() -> None:
    assert matched_victim_occupation("He raped a nurse.") == ["a nurse"]
    assert matched_victim_occupation("The accused, a nurse, was booked.") == []  # accused kept
    assert is_occupation_scanned_key("summary") and is_occupation_scanned_key("title")
    assert not is_occupation_scanned_key("district")


def test_minor_summary_uses_full_state_name_not_code() -> None:
    """§1c: a minor summary/title renders the full state name (never the 2-letter code)."""
    from pipeline.sanitize import minor_summary, minor_title

    record = {
        "minor_involved": True,
        "category": "pocso",
        "state": "HR",
        "district": "Gurugram",
        "status": "UNDER_TRIAL",
        "offence_sections": ["POCSO 4"],
        "incident_reported_date": "2026",
    }
    summary = minor_summary(record)
    assert "Haryana" in summary and ", HR" not in summary
    # Title falls back to the full state name when a district is absent.
    no_district = {**record, "district": ""}
    assert minor_title(no_district).endswith("— Haryana (2026)")


def test_minor_status_history_keeps_court_date_day_precision() -> None:
    """§2: a minor's incident date truncates to month, and each status_history date to month
    — EXCEPT a court-sourced date, which keeps full day precision (a public cause-list date
    attached to a case number, not a fact about where a child was)."""
    from pipeline.sanitize import project_minor_record

    record = {
        "minor_involved": True,
        "category": "pocso",
        "state": "TG",
        "district": "Warangal",
        "status": "CONVICTED",
        "offence_sections": ["POCSO 6"],
        "incident_reported_date": "2026-07-15",
        "status_history": [
            {"status": "FIR_FILED", "date": "2026-06-20", "source": 0},  # news -> month
            {"status": "CONVICTED", "date": "2026-07-30", "source": 1},  # court -> day kept
        ],
        "sources": [{"source_type": "news_article"}, {"source_type": "court"}],
    }
    projected = project_minor_record(record)
    assert projected["incident_reported_date"] == "2026-07"  # incident DAY withheld for a minor
    dates = {e["status"]: e["date"] for e in projected["status_history"]}
    assert dates["FIR_FILED"] == "2026-06"  # non-court date truncated to month
    assert dates["CONVICTED"] == "2026-07-30"  # court date keeps day precision
