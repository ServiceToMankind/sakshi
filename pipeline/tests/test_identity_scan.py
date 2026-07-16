"""Tests for the deterministic identity-detail backstop (non-minor narrative gate)."""

from __future__ import annotations

from pipeline.identity_scan import has_identity_detail, matched_relationship_terms


def test_relationship_in_summary_is_flagged() -> None:
    """A victim-accused relationship in a non-minor summary re-identifies the victim."""
    rec = {
        "minor_involved": False,
        "summary": "A woman was raped by her brother-in-law; police registered an FIR.",
    }
    assert has_identity_detail(rec) is True


def test_relationship_in_title_is_flagged() -> None:
    rec = {"minor_involved": False, "title": "Man convicted of raping his neighbour"}
    assert has_identity_detail(rec) is True


def test_age_in_title_or_section_is_flagged() -> None:
    """Finding C/D: the model-written title and offence-section strings are age-scanned
    too (not just summary)."""
    assert has_identity_detail({"minor_involved": False, "title": "22-year-old raped in Warangal"})
    assert has_identity_detail(
        {"minor_involved": False, "offence_sections": ["POCSO 6", "victim aged 14"]}
    )


def test_clean_non_minor_summary_passes() -> None:
    """An act/district/response summary with no relationship or age is allowed through."""
    rec = {
        "minor_involved": False,
        "title": "Rape case under trial in Warangal",
        "summary": "A rape was reported in Warangal district. Police filed a chargesheet.",
        "offence_sections": ["BNS 64"],
    }
    assert has_identity_detail(rec) is False


def test_minor_records_are_skipped() -> None:
    """Minors are already projected (deterministic text, no accused) — this scan targets
    the non-minor narrative surface, so a minor never trips it."""
    rec = {
        "minor_involved": True,
        "summary": "The case is under trial. Identifying details are withheld by law (POCSO s.23).",
    }
    assert has_identity_detail(rec) is False


def test_matched_relationship_terms_helper() -> None:
    assert matched_relationship_terms("her stepfather and an uncle")  # non-empty
    assert matched_relationship_terms("a district hospital") == []
    assert matched_relationship_terms(123) == []  # type: ignore[arg-type]
