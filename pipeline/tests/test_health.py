"""Tests for the per-source pipeline accounting funnel (pipeline.health)."""

from __future__ import annotations

from pipeline.health import build_pipeline_health
from pipeline.sources.base import RawDocument


def _doc(url: str, publisher: str) -> RawDocument:
    return RawDocument(url=url, publisher=publisher, fetched_at="2026-08-04", text="…")


def test_funnel_attributes_documents_outcomes_and_records_per_publisher() -> None:
    raw = [
        _doc("u1", "The Hindu"),
        _doc("u2", "The Hindu"),
        _doc("u3", "Delhi High Court"),
    ]
    doc_outcomes = {"u1": "extracted", "u2": "out_of_scope", "u3": "extracted"}
    published = [{"sources": [{"publisher": "The Hindu"}]}]
    needs_review = [{"sources": [{"publisher": "Delhi High Court"}]}]
    review = [{"reason": "unverified", "record": {"sources": [{"publisher": "The Hindu"}]}}]

    health = build_pipeline_health(
        run_date="2026-08-04",
        raw_docs=raw,
        doc_outcomes=doc_outcomes,
        published=published,
        needs_review=needs_review,
        review=review,
        court_prefilter=[{"source": "Indian Kanoon", "hits": 50, "qualifying": 12, "fetched": 12}],
    )

    hindu = health["by_publisher"]["The Hindu"]
    assert hindu["documents"] == 2
    assert hindu["extracted"] == 1 and hindu["out_of_scope"] == 1
    assert hindu["published"] == 1
    assert hindu["quarantined"] == 1 and hindu["quarantine_reasons"] == {"unverified": 1}

    dhc = health["by_publisher"]["Delhi High Court"]
    assert dhc["documents"] == 1 and dhc["extracted"] == 1
    assert dhc["needs_review"] == 1 and dhc["published"] == 0

    assert health["court_prefilter"][0]["qualifying"] == 12


def test_funnel_counts_failed_outcome_and_unknown_urls_ignored() -> None:
    health = build_pipeline_health(
        run_date="2026-08-04",
        raw_docs=[_doc("u1", "PTI")],
        doc_outcomes={"u1": "failed", "u-ghost": "extracted"},  # u-ghost has no raw doc
        published=[],
        needs_review=[],
        review=[],
        court_prefilter=[],
    )
    pti = health["by_publisher"]["PTI"]
    assert pti["failed"] == 1 and pti["extracted"] == 0
    # a doc_outcome URL with no fetched document is not attributed anywhere
    assert set(health["by_publisher"]) == {"PTI"}


def test_review_item_without_record_does_not_crash() -> None:
    health = build_pipeline_health(
        run_date="2026-08-04",
        raw_docs=[],
        doc_outcomes={},
        published=[],
        needs_review=[],
        review=[{"reason": "schema_invalid"}],  # no "record" key
        court_prefilter=[],
    )
    assert health["by_publisher"] == {}


def test_prefilter_skipped_and_pass_rate_reported_per_publisher() -> None:
    raw = [_doc("u1", "Dainik Bhaskar"), _doc("u2", "Dainik Bhaskar"), _doc("u3", "The Hindu")]
    health = build_pipeline_health(
        run_date="2026-08-12",
        raw_docs=raw,
        doc_outcomes={"u1": "extracted"},
        published=[],
        needs_review=[],
        review=[],
        court_prefilter=[],
        prefilter_skipped_urls={"u2"},  # one Dainik Bhaskar doc skipped by the offence filter
    )
    db = health["by_publisher"]["Dainik Bhaskar"]
    assert db["documents"] == 2 and db["prefilter_skipped"] == 1
    assert db["prefilter_pass_rate"] == 0.5
    assert health["by_publisher"]["The Hindu"]["prefilter_pass_rate"] == 1.0


def test_prefilter_is_sorted_by_source() -> None:
    health = build_pipeline_health(
        run_date="2026-08-04",
        raw_docs=[],
        doc_outcomes={},
        published=[],
        needs_review=[],
        review=[],
        court_prefilter=[{"source": "Meghalaya"}, {"source": "Delhi"}],
    )
    assert [r["source"] for r in health["court_prefilter"]] == ["Delhi", "Meghalaya"]
