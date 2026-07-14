"""Synthetic fixtures for offline dry-runs and tests.

Every value here is obviously fake (district "TESTVILLE", example.invalid URLs).
These NEVER represent a real case. The dry-run pipeline (``python -m pipeline
--dry-run``) uses them to prove the fetch->extract->sanitize->dedupe->shard flow
works end-to-end without touching the network or the Gemini API.

The two extractions intentionally describe the SAME case from two sources (a
court record and a media report) so the dry-run exercises case-anchored dedup
and source-union merging. The court extraction carries a forbidden ``victim``
key so the run visibly demonstrates the sanitizer dropping it before disk.
"""

from __future__ import annotations

from typing import Any

from pipeline.sources.base import RawDocument


def fixture_raw_documents() -> list[RawDocument]:
    """Two synthetic already-public documents describing one TESTVILLE case."""
    return [
        RawDocument(
            url="https://example.invalid/testville/court/order-1",
            publisher="eCourts",
            fetched_at="2026-07-09",
            text=(
                "In the Sessions Court, TESTVILLE. Case CNR TSHC01-000001-2026, "
                "arising from FIR 000/2026 registered at TESTVILLE PS. Offence under "
                "BNS 64. Accused #1 present; matter is under trial. "
                "Next hearing listed for 2026-08-02."
            ),
        ),
        RawDocument(
            url="https://example.invalid/testville/news/report-1",
            publisher="The Example Herald",
            fetched_at="2026-07-09",
            text=(
                "A case registered at TESTVILLE PS under FIR 000/2026, relating to an "
                "offence under BNS 64, is under trial at the Sessions Court in "
                "TESTVILLE district."
            ),
        ),
    ]


def fixture_extractions() -> list[dict[str, Any]]:
    """Two synthetic pre-sanitize extraction dicts for the same case.

    The first is court-sourced and (deliberately) carries a forbidden ``victim``
    key to demonstrate the sanitizer; the second is media-sourced with the
    accused name withheld. They deduplicate to a single published record with
    both sources unioned and the court status winning.
    """
    return [
        {
            "cnr": "TSHC01-000001-2026",
            "fir_ref": {"station": "TESTVILLE PS", "number": "000/2026"},
            "state": "TG",
            "district": "TESTVILLE",
            "incident_reported_date": "2026-06-14",
            "offence_sections": ["BNS 64"],
            "category": "rape",
            "minor_involved": False,
            "status": "UNDER_TRIAL",
            "status_history": [{"status": "FIR_FILED", "date": "2026-06-15", "source": 0}],
            "accused": [
                {"label": "Accused #1", "name_public_court_record": None, "status": "UNDER_TRIAL"}
            ],
            "court": {"name": "Sessions Court, TESTVILLE", "next_hearing": "2026-08-02"},
            "summary": (
                "Illustrative synthetic case pending before the Sessions Court, TESTVILLE."
            ),
            "sources": [
                {
                    "url": "https://example.invalid/testville/court/order-1",
                    "publisher": "eCourts",
                    "source_type": "court",
                    "retrieved": "2026-07-09",
                }
            ],
            "confidence": 0.94,
            # Forbidden key emitted by the model — the sanitizer MUST drop it.
            "victim": None,
        },
        {
            "fir_ref": {"station": "TESTVILLE PS", "number": "000/2026"},
            "state": "TG",
            "district": "TESTVILLE",
            "incident_reported_date": "2026-06-14",
            "offence_sections": ["BNS 64"],
            "category": "rape",
            "minor_involved": False,
            "status": "FIR_FILED",
            "accused": [
                {"label": "Accused #1", "name_public_court_record": None, "status": "FIR_FILED"}
            ],
            "court": {"name": "Sessions Court, TESTVILLE", "next_hearing": None},
            "summary": "Synthetic media report of a case under trial in TESTVILLE district.",
            "sources": [
                {
                    "url": "https://example.invalid/testville/news/report-1",
                    "publisher": "The Example Herald",
                    "source_type": "news_article",
                    "retrieved": "2026-07-09",
                }
            ],
            "confidence": 0.94,
        },
    ]
