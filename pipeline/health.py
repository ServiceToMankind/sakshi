"""Per-source pipeline accounting — the funnel from documents to records (ops §3).

Answers the question that matters most at scale: "why did N documents produce M records?"
Per publisher it reports documents → extracted → published / held / quarantined (with the
reason for every drop); alongside it carries the court-source PRE-FILTER funnel (search hits
→ qualifying → billed doc fetches) that explains why so few documents were even extracted.

Counts only. A publisher name is public; a document URL's content and a record's text are
never touched here. Written to ``data/pipeline_health.json`` and summarised in the heartbeat.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pipeline.sources.base import RawDocument

__all__ = ["build_pipeline_health"]

_OUT_OF_SCOPE = frozenset({"out_of_scope", "not_a_case"})


def _publishers(record: Mapping[str, Any]) -> set[str]:
    return {
        str(s.get("publisher", ""))
        for s in (record.get("sources") or [])
        if isinstance(s, dict) and s.get("publisher")
    }


def build_pipeline_health(
    *,
    run_date: str,
    raw_docs: Iterable[RawDocument],
    doc_outcomes: Mapping[str, str],
    published: Iterable[Mapping[str, Any]],
    needs_review: Iterable[Mapping[str, Any]],
    review: Iterable[Mapping[str, Any]],
    court_prefilter: list[dict[str, Any]],
    prefilter_skipped_urls: set[str] | None = None,
) -> dict[str, Any]:
    """Build the per-publisher funnel + the court pre-filter section (counts only).

    ``doc_outcomes`` maps a document URL to ``extracted`` | ``out_of_scope`` | ``not_a_case`` |
    ``failed``. ``review`` items are ``{"reason", "record"}``. ``court_prefilter`` is the list
    of per-source pre-filter rows (hits/qualifying/fetched) surfaced by the court sources.
    ``prefilter_skipped_urls`` are media documents skipped by the §2 offence-language pre-filter
    (fetched but not sent to an LLM) — reported per publisher as ``prefilter_skipped`` with a
    ``prefilter_pass_rate``, so the media funnel is as auditable as the court one.
    """
    skipped = prefilter_skipped_urls or set()
    per: dict[str, dict[str, Any]] = {}

    def slot(publisher: str) -> dict[str, Any]:
        return per.setdefault(
            publisher,
            {
                "documents": 0,
                "prefilter_skipped": 0,
                "extracted": 0,
                "out_of_scope": 0,
                "failed": 0,
                "published": 0,
                "needs_review": 0,
                "quarantined": 0,
                "quarantine_reasons": {},
            },
        )

    url_publisher: dict[str, str] = {}
    for doc in raw_docs:
        entry = slot(doc.publisher)
        entry["documents"] += 1
        if doc.url in skipped:
            entry["prefilter_skipped"] += 1
        url_publisher.setdefault(doc.url, doc.publisher)

    for url, outcome in doc_outcomes.items():
        publisher = url_publisher.get(url)
        if publisher is None:
            continue
        entry = slot(publisher)
        if outcome == "extracted":
            entry["extracted"] += 1
        elif outcome in _OUT_OF_SCOPE:
            entry["out_of_scope"] += 1
        elif outcome == "failed":
            entry["failed"] += 1

    for record in published:
        for publisher in _publishers(record):
            slot(publisher)["published"] += 1
    for record in needs_review:
        for publisher in _publishers(record):
            slot(publisher)["needs_review"] += 1
    for item in review:
        quarantined = item.get("record") if isinstance(item, Mapping) else None
        reason = (
            str(item.get("reason", "unspecified")) if isinstance(item, Mapping) else "unspecified"
        )
        for publisher in _publishers(quarantined or {}):
            entry = slot(publisher)
            entry["quarantined"] += 1
            reasons = entry["quarantine_reasons"]
            reasons[reason] = reasons.get(reason, 0) + 1

    for entry in per.values():
        media = entry["documents"]
        passed = media - entry["prefilter_skipped"]
        entry["prefilter_pass_rate"] = round(passed / media, 3) if media else None

    return {
        "generated": run_date,
        "by_publisher": {pub: per[pub] for pub in sorted(per)},
        "court_prefilter": sorted(court_prefilter, key=lambda r: str(r.get("source", ""))),
    }
