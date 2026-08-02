"""Pipeline orchestrator: fetch -> extract -> sanitize -> dedupe -> validate -> shard.

Wires the daily run end to end. EVERY record — and every log line and review
entry — passes through :mod:`pipeline.sanitize` before it can touch disk; nothing
from a source or the model is trusted directly.

Usage::

    python -m pipeline                 # real run against the sources in sources.yml
    python -m pipeline --dry-run       # offline: fixtures only, no network/Gemini

Scope is bounded by ``LAUNCH_STATES`` / ``LAUNCH_LOOKBACK_DAYS`` (env), so a
supervised first run can be limited to a readable window. ``--dry-run`` proves
the whole flow works with synthetic TESTVILLE fixtures without a network or key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from functools import reduce
from pathlib import Path
from typing import Any, TextIO

from scripts.pii_guard import iter_json_files, scan_json_file

from pipeline import config, fixtures, spend, verify
from pipeline.citation_slug import url_carries_identifying_slug
from pipeline.corrections import apply_correction, load_corrections, quarantined_ids
from pipeline.coverage import build_coverage
from pipeline.dedupe import dedupe, exact_anchor_keys, merge_records
from pipeline.districts import canonical_district
from pipeline.extract.gemini import ExtractionClient, extract
from pipeline.gates import auto_publish_eligible, has_pocso_signal
from pipeline.ledger import Ledger, load_ledger, save_ledger
from pipeline.merge_review import find_candidate_matches
from pipeline.offence_sections import normalize_sections
from pipeline.readability import readability_violations
from pipeline.sanitize import sanitize_record, sanitize_string
from pipeline.shard import WriteResult, write_shards
from pipeline.sources.base import RawDocument
from pipeline.sources.http import PoliteClient
from pipeline.sources.registry import build_sources, load_source_configs
from pipeline.states import CANONICAL_STATES, normalize_state
from pipeline.validate import (
    iter_shard_files,
    load_schema,
    project_to_schema,
    validate_record,
    withhold_unsourced_accused_names,
)


@dataclass
class RunReport:
    """Everything a caller (or the review PR) needs to know about a run."""

    new: int = 0
    # A MATERIAL change (status/court/offence_sections/accused/severity actually changed) —
    # NOT a re-sighting. A record re-seen unchanged is a `rechecked`, never a `material`. This
    # is what makes the site stop appearing to churn daily (§1).
    material: int = 0
    rechecked: int = 0
    review: int = 0
    published: int = 0
    needs_review: int = 0
    verified: int = 0
    verify_demoted: int = 0
    verify_usd: float = 0.0
    fetched: int = 0
    # Community case submissions (§6) fetched this run + how many reached the published site.
    # A high fetched-but-not-published ratio is itself a signal (submission quality/spam).
    submissions: int = 0
    submissions_published: int = 0
    processed: int = 0
    skipped_settled: int = 0
    extracted: int = 0
    rejected_out_of_scope: int = 0
    estimated_usd: float = 0.0
    # Monthly budget accounting (pipeline.spend): cumulative USD spent this calendar month
    # (incl. this run) vs the cap; budget_exhausted is set when a run made no paid calls
    # because the month's cap was already reached (heartbeat + ops issue surface it).
    month_to_date: float = 0.0
    monthly_cap: float = 0.0
    budget_exhausted: bool = False
    scope: str = ""
    state_counts: dict[str, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    review_reasons: dict[str, int] = field(default_factory=dict)
    needs_review_reasons: dict[str, int] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


def _log(report: RunReport, message: str) -> None:
    """Append a log line, sanitized — logs never carry PII either."""
    report.logs.append(sanitize_string(message))


async def _fetch_all(
    client: PoliteClient, fetched_at: str, court_only: bool = False
) -> list[RawDocument]:
    """Fetch from every ENABLED source (sources.yml) with one polite client. ``court_only``
    (refresh mode) restricts to court-record sources."""
    docs: list[RawDocument] = []
    for source in build_sources(client, fetched_at=fetched_at, court_only=court_only):
        docs.extend(await source.fetch())
    return docs


def _fetch_documents(
    fetched_at: str, court_only: bool = False
) -> list[RawDocument]:  # pragma: no cover - network I/O
    async def _go() -> list[RawDocument]:
        async with PoliteClient() as client:
            return await _fetch_all(client, fetched_at, court_only=court_only)

    return asyncio.run(_go())


def _illustrative_cost(docs: list[RawDocument]) -> float:
    """A rough cost estimate for the fixture docs (~4 chars/token) for the dry-run."""
    input_tokens = sum(len(doc.text) for doc in docs) // 4 + 400 * len(docs)
    output_tokens = 200 * len(docs)
    return config.estimate_cost_usd(input_tokens, output_tokens)


# Substrings that flag a document as a LIKELY sexual-offence case, used only to
# ORDER extraction (relevant first) so a truncated run reaches cases before its
# wall-clock budget runs out. Generous by design — a false positive only reorders,
# and the extractor's in_scope gate + deterministic offence-section check decide
# what is actually a case. Not a filter: nothing is dropped from coverage.
_OFFENCE_HINTS: tuple[str, ...] = (
    "rape",
    "gangrape",
    "gang rape",
    "sexual",
    "molest",
    "pocso",
    "outrage",
    "modesty",
    "stalk",
    "voyeur",
    "unnatural offence",
    "assault",
    "abuse",
    "harass",
    "376",
    "375",
    "377",
    "354",
    "509",
)


def _looks_offence_relevant(doc: RawDocument) -> bool:
    """True if a document's text hints at a sexual offence (for extraction ORDERING)."""
    text = doc.text.lower()
    return any(hint in text for hint in _OFFENCE_HINTS)


def _drop_null_top_level(record: dict[str, Any]) -> dict[str, Any]:
    """Drop TOP-LEVEL keys whose value is null.

    The model emits e.g. ``court: null`` for a missing optional object, but the schema
    allows such optional fields to be ABSENT, not null — so a kept null fails
    validation and (before this) crashed or quarantined an otherwise-clean record. A
    required field that is null is also dropped, so it fails the schema's ``required``
    check and routes to review rather than publishing malformed. Nested nulls (e.g. an
    accused's withheld ``name_public_court_record``) are preserved — only the top
    level is pruned.
    """
    return {key: value for key, value in record.items() if value is not None}


def _in_scope(
    record: dict[str, Any], states: frozenset[str] | None, lookback: int | None, run_date: str
) -> bool:
    """True if the record is within the configured state set and lookback window."""
    if states is not None and str(record.get("state", "")).upper() not in states:
        return False
    if lookback is not None:
        try:
            reported = date.fromisoformat(str(record.get("incident_reported_date")))
            run_day = date.fromisoformat(run_date)
        except (ValueError, TypeError):
            return False
        if reported > run_day or (run_day - reported).days > lookback:
            return False
    return True


def _scope_label(states: frozenset[str] | None, lookback: int | None) -> str:
    where = ",".join(sorted(states)) if states else "all states"
    window = f"last {lookback}d" if lookback is not None else "no window"
    return f"{where}; {window}"


def _strip_minor_model_note(record: dict[str, Any]) -> dict[str, Any]:
    """Drop the verifier's model-written ``verification_note`` from a MINOR record.

    A minor's published fields must be deterministic and non-identifying (POCSO s.23);
    the note is free model text that the minor projection does not otherwise neutralise,
    and it is invisible to ``pii_guard`` (not a forbidden key, not a PII-value match, and
    the age-scan only inspects ``summary``). So a note like "the 15-year-old survivor's
    school in Kochi" would ship un-scanned. Stripping it here is defence in depth for the
    canonical fix in ``project_minor_record`` (protected — pending a human-approved
    issue). Non-minor records keep the note. Idempotent.
    """
    if record.get("minor_involved") is True and "verification_note" in record:
        return {key: value for key, value in record.items() if key != "verification_note"}
    return record


def _write_coverage(records: list[dict[str, Any]], data_dir: Path, run_date: str) -> None:
    """Write data/coverage.json — per-state coverage (declared gaps included) and the
    trackability rate (§3). Public counts only; committed for the Coverage page."""
    coverage = build_coverage(load_source_configs(), records, run_date)
    path = data_dir / "coverage.json"
    path.write_text(json.dumps(coverage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_merge_review(records: list[dict[str, Any]], data_dir: Path, run_date: str) -> None:
    """Write data/_merge_review/candidates.json — POSSIBLE duplicate clusters a human must
    decide on (§8). NEVER auto-merges and never removes a record; the corpus is untouched.
    The file is written even when empty (an empty list is the honest "no candidates" state)
    so a reviewer can trust it, and rewritten each run so a resolved candidate disappears."""
    candidates = find_candidate_matches(records)
    path = data_dir / "_merge_review" / "candidates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated": run_date, "candidates": candidates}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_review(review: list[dict[str, Any]], data_dir: Path, run_date: str) -> None:
    if not review:
        return
    review_dir = data_dir / "_review"
    review_dir.mkdir(parents=True, exist_ok=True)
    # Coerce minor BEFORE sanitize (symmetric with _write_needs_review) so a quarantined
    # record whose minor_involved is a non-bool/absent/POCSO-implied minor is still
    # age-projected — defence in depth for any record that reaches _review unfinalized.
    payload = [
        {
            "reason": item["reason"],
            "record": _strip_minor_model_note(sanitize_record(_coerce_minor(item["record"]))),
        }
        for item in review
    ]
    (review_dir / f"review-{run_date}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# The needs-review queue: published-quality records HELD from auto-publish by the
# graduated gate. Single accumulating file (NOT sharded -> never indexed -> never on
# the public site); under data/ so pii_guard scans it and the review PR shows it.
NEEDS_REVIEW_RELPATH = Path("_needs_review") / "queue.json"

# The landing feed: the latest published records, so the site's home view needs no
# shard-walking. Regenerated every run from the published (auto-eligible) set.
RECENT_RELPATH = Path("recent.json")
RECENT_FEED_SIZE = 50


def _write_recent(records: list[dict[str, Any]], data_dir: Path) -> None:
    """Write data/recent.json — the latest published records for the landing feed."""
    ordered = sorted(
        records,
        key=lambda r: (str(r.get("incident_reported_date", "")), str(r.get("id", ""))),
        reverse=True,
    )
    feed = [
        {
            "id": record.get("id"),
            "title": record.get("title"),
            "summary": record.get("summary"),
            "state": record.get("state"),
            "district": record.get("district"),
            "category": record.get("category"),
            "status": record.get("status"),
            # Public charge sections — the landing feed derives the severity badge from
            # these. Charge codes are non-identifying (they describe the OFFENCE, not the
            # victim), so this is guardrail-safe for every case including a minor's.
            "offence_sections": record.get("offence_sections") or [],
            "incident_reported_date": record.get("incident_reported_date"),
            "minor_involved": bool(record.get("minor_involved")),
            "publisher": (record.get("sources") or [{}])[0].get("publisher", ""),
            "verified": bool(record.get("verified")),
            # Public temporal fields. first_published is write-once; last_status_change is
            # present ONLY when a material field actually changed (else absent). The feed
            # shows "Status changed <date>" only when last_status_change is present — never a
            # blanket "updated today" (§1). last_checked stays internal (data/_meta/).
            "first_published": record.get("first_published"),
            "last_status_change": record.get("last_status_change"),
        }
        for record in ordered[:RECENT_FEED_SIZE]
    ]
    (data_dir / RECENT_RELPATH).write_text(
        json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_needs_review(items: list[tuple[dict[str, Any], list[str]]], data_dir: Path) -> None:
    """Write (or clear) the needs-review queue from the CURRENT held set.

    Regenerated every run from what failed the gate this run — which already includes
    carried-over holds that still fail it — so the file is the live accumulation, not a
    per-day snapshot. An empty set clears the file so a promoted/removed record does
    not linger in the queue.
    """
    path = data_dir / NEEDS_REVIEW_RELPATH
    if not items:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Coerce minor BEFORE sanitize at this single write choke point, so EVERY held
    # record — fresh or carried over — is age-projected when its minor status is a
    # non-bool, absent, or POCSO-implied minor. A carryover held record bypasses the
    # fresh-extraction coercion, so without this it could keep day-precise detail.
    payload = [
        {
            "reasons": reasons,
            "record": _strip_minor_model_note(sanitize_record(_coerce_minor(record))),
        }
        for record, reasons in items
    ]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_existing_published(data_dir: Path) -> list[dict[str, Any]]:
    """Load already-published records so a run regenerates the FULL tree.

    The committed shards are the canonical store. Without this, a run that only
    fetched new documents would republish just those and ``_clear_stale_shards``
    would delete all prior cases. Existing records re-enter dedupe so new documents
    merge into them and history is preserved.
    """
    records: list[dict[str, Any]] = []
    for shard in iter_shard_files(data_dir):
        records.extend(json.loads(shard.read_text(encoding="utf-8")))
    return records


def _record_urls(records: list[dict[str, Any]]) -> set[str]:
    return {str(s.get("url", "")) for r in records for s in r.get("sources", [])}


def _canonicalize_state(record: dict[str, Any]) -> dict[str, Any]:
    """Normalise a record's GEOGRAPHY to one canonical spelling so a single jurisdiction is
    never split across two forms in ids, shard files, dedupe anchors, and the scorecard:

    - state code to its canonical form (e.g. TS->TG). If the change makes the record's id
      encode the OLD state, the id is CLEARED so write_shards re-mints a matching one — the
      per-state shard file and the case-page lookup are both keyed on the id's state-part,
      so a mismatched id would 404.
    - district spelling to its canonical form (e.g. Gurgaon->Gurugram, South District->South
      Delhi) via :func:`pipeline.districts.canonical_district`. District is a dedupe anchor
      and user-facing, so two spellings would both split a case and mislead a reader; the id
      is NOT re-minted on a district change (the id encodes only year+state+serial).
    """
    updated = record
    district = updated.get("district")
    if isinstance(district, str):
        canonical_d = canonical_district(district)
        if canonical_d != district:
            updated = {**updated, "district": canonical_d}
    original = str(updated.get("state", ""))
    canonical = normalize_state(original)
    if canonical != original:
        updated = {**updated, "state": canonical}
        rid = str(updated.get("id", ""))
        if rid.startswith("SKS-") and len(rid) >= 11 and rid[9:11] != canonical:
            updated.pop("id", None)
    return updated


def _split_by_jurisdiction(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition ``records`` into (publishable, review-entries) by state validity (§4a).

    A record whose (already-canonicalised) state is not a code the site recognises is a
    data-quality signal, not something to ship to a phantom shard/scorecard: it is diverted
    to ``_review`` with reason ``unknown_state`` (a 2-letter code is present but unrecognised)
    or ``no_jurisdiction`` (no state at all). Callers append the second list to their review
    queue. Aliases are already resolved upstream (``_canonicalize_state``), so a valid alias
    like TL->TG is never diverted.
    """
    jurisdictional: list[dict[str, Any]] = []
    diverted: list[dict[str, Any]] = []
    for record in records:
        state = str(record.get("state", "")).strip().upper()
        if state in CANONICAL_STATES:
            jurisdictional.append(record)
        else:
            reason = "unknown_state" if state else "no_jurisdiction"
            diverted.append({"reason": reason, "record": record})
    return jurisdictional, diverted


def _split_unreadable(
    records: list[dict[str, Any]], grandfathered_ids: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition ``records`` by the §6a readability GATE (the pipeline side of
    ``pipeline.readability`` — the deterministic backstop the prompt cannot guarantee).

    A FRESH non-minor record whose summary carries a readability violation (legalese, a
    section-number-in-prose citation, or an over-long sentence) is diverted to ``_review``
    with reason ``unreadable_summary`` — so an unreadable summary never publishes and never
    trips the CI readability assertion on a fresh record. An already-live record (its id in
    ``grandfathered_ids``) is NEVER demoted (the guard's BASELINE_ALLOWLIST tracks those
    until re-extraction); a MINOR's summary is deterministic (fixed vocabulary) and exempt.
    """
    readable: list[dict[str, Any]] = []
    diverted: list[dict[str, Any]] = []
    for record in records:
        if (
            not record.get("minor_involved")
            and str(record.get("id", "")) not in grandfathered_ids
            and readability_violations(record.get("summary"))
        ):
            diverted.append({"reason": "unreadable_summary", "record": record})
        else:
            readable.append(record)
    return readable, diverted


def _coerce_minor(record: dict[str, Any]) -> dict[str, Any]:
    """Normalise ``minor_involved`` to a STRICT bool before the last gate — fail CLOSED.

    The sanitizer's minor projection triggers on ``is True`` (strict identity), the
    graduated gate holds on truthiness, and the dedupe merge coerces with ``or`` —
    three notions that diverge for a truthy non-bool value (e.g. 1 or "true"). Coercing
    once here, before sanitize, makes all three agree.

    Two fail-CLOSED rules, because getting "minor" wrong is a POCSO s.23 offence, not a
    bug: (1) an ABSENT/None flag becomes ``True`` — an unknown minor status is treated
    as a minor (projected + held), never published as non-minor; (2) any POCSO signal
    forces ``True`` — POCSO applies only to minors, so a POCSO case the model flagged
    non-minor is projected and held, not shipped with day-precise detail. Only an
    explicit, present, falsy, non-POCSO value is treated as non-minor.
    """
    record = dict(record)
    minor = record.get("minor_involved")
    if minor is None or has_pocso_signal(record):
        record["minor_involved"] = True
    else:
        record["minor_involved"] = bool(minor)
    return record


# Human-approved held records are promoted to publish. Approval is by source URL, in a
# committed allowlist a human edits (or a reviewed-PR adds to) — the SAME "human merge
# publishes them" gate the graduated design calls for. A promoted minor record stays
# minimal/projected (approval never un-projects it); only its already-safe form ships.
APPROVED_RELPATH = Path("_needs_review") / "approved.json"


def _load_approved(base_dir: Path) -> set[str]:
    """Load the set of human-approved RAW source URLs.

    Matched RAW (not through sanitize_string): sanitisation is non-injective — two
    distinct URLs with a PII-shaped digit run collapse to one '[redacted]' string, so
    matching in that space could promote a NON-approved minor. A record whose stored
    URL was PII-redacted simply will not match a raw approved URL and stays held (safe);
    the operator uses the real article URL.
    """
    path = base_dir / APPROVED_RELPATH
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    urls = data.get("approved_source_urls", []) if isinstance(data, dict) else data
    if not isinstance(urls, list):
        return set()
    return {str(url).strip() for url in urls if str(url).strip()}


def _is_approved(record: dict[str, Any], approved: set[str]) -> bool:
    return any(
        str(source.get("url", "")).strip() in approved for source in record.get("sources", [])
    )


def _verified_hold_reasons(record: dict[str, Any]) -> list[str]:
    """Reasons a VERIFIED, FRESH record is still held for a human (verifier-live mode).

    Exactly the graduated auto-publish gate MINUS ``minor_involved``: a verified minor's
    title/summary are deterministic and non-identifying, so it publishes. Every OTHER
    hold still applies — crucially ``pocso_minor_mismatch`` (a POCSO signal on a record
    flagged non-minor is a suspect determination that would ship day-precise dates), plus
    ``named_accused`` (defamation liability), ``live_blog_only``, and sub-threshold
    ``confidence``. Delegating to :func:`auto_publish_eligible` keeps the two in lockstep
    so this can never silently drift from the canonical gate.
    """
    _eligible, reasons = auto_publish_eligible(record)
    return [reason for reason in reasons if reason != "minor_involved"]


def _finalize_for_disk(record: dict[str, Any], case_schema: dict[str, Any]) -> dict[str, Any]:
    """Run the FULL last gate on one record and return its publish-safe form.

    coerce-minor -> sanitize/project -> withhold unsourced accused names, then strip a
    minor's model-written ``verification_note`` (see :func:`_strip_minor_model_note`).
    This is the single choke point for every record that may touch a shard, so a dedupe
    merge that flipped ``minor_involved`` after the per-candidate sanitize is re-projected
    to the minimal non-identifying shape here. Idempotent for an already-projected record.
    """
    finalized = _strip_minor_model_note(
        withhold_unsourced_accused_names(
            project_to_schema(sanitize_record(_coerce_minor(record)), case_schema)
        )
    )
    return _flag_identifying_sources(_normalize_offence_sections(finalized))


def _flag_identifying_sources(record: dict[str, Any]) -> dict[str, Any]:
    """Mark each source whose URL slug states a withheld detail (§5) so the site renders the
    domain — never the raw slug — and tucks it behind an expander. Set after project_to_schema
    so the flag is schema-valid; idempotent; the URL itself is kept (a citation is verifiable).
    """
    sources = record.get("sources")
    if not sources:
        return record
    flagged = []
    for source in sources:
        updated = dict(source)
        if url_carries_identifying_slug(str(updated.get("url", ""))):
            updated["url_carries_identifying_slug"] = True
        else:
            updated.pop("url_carries_identifying_slug", None)
        flagged.append(updated)
    return {**record, "sources": flagged}


def _normalize_offence_sections(record: dict[str, Any]) -> dict[str, Any]:
    """Rewrite ``offence_sections`` to its canonical, de-duplicated form and split any junk
    tokens into ``unparsed_sections`` (§4b). Runs after project_to_schema so both keys are
    schema-valid; idempotent. Public charge codes only — never victim data."""
    sections = record.get("offence_sections")
    if not sections:
        return record
    canonical, unparsed = normalize_sections(sections)
    updated = {**record, "offence_sections": canonical}
    if unparsed:
        updated["unparsed_sections"] = unparsed
    else:
        updated.pop("unparsed_sections", None)
    return updated


def _preserve_refresh_narrative(kept: list[dict[str, Any]], existing: list[dict[str, Any]]) -> int:
    """Freeze the reviewed NARRATIVE (title/summary) of each refreshed record to the text
    already on the site. Returns the count of records whose narrative was held.

    Refresh (§2) is a STATUS-only update: a weekly court re-query may advance a record's
    status, append a timeline point, or add a court source — but it must never rewrite the
    reviewed prose. A court JUDGMENT is a HIGH-PII SOURCE, not a text to republish (§1b):
    its narrative about the family, the hamlet, the child's schooling is exactly what must
    not survive extraction, and the merge (court beats media in ``dedupe._order``) would
    otherwise make the fresh judgment's model summary the primary and overwrite the vetted
    one. A genuinely NEW narrative belongs to the daily ``discover`` run and its review, not
    a silent refresh. Minor summaries are deterministic projections (recomposed from
    structured facts, never model prose), so they are left to re-project — only NON-MINOR
    model narratives are restored here. Mutates ``kept`` in place.
    """
    by_id = {str(r.get("id", "")): r for r in existing if r.get("id")}
    by_anchor: dict[str, dict[str, Any]] = {}
    for record in existing:
        for anchor in exact_anchor_keys(record):
            by_anchor.setdefault(anchor, record)
    held = 0
    for record in kept:
        if record.get("minor_involved"):
            continue
        prior = by_id.get(str(record.get("id", "")))
        if prior is None:
            prior = next((by_anchor[a] for a in exact_anchor_keys(record) if a in by_anchor), None)
        if prior is None:
            continue
        changed = False
        for key in ("title", "summary"):
            if prior.get(key) and record.get(key) != prior.get(key):
                record[key] = prior[key]
                changed = True
        held += changed
    return held


def _dedup_approved_by_url(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge approved records that share a source URL (same article => same case).

    Scoped to the OPERATOR-APPROVED set only, so it cannot fuse distinct cases in the
    general pipeline (a multi-case roundup article would be handled at review); the
    operator approved these specific URLs as one case each.
    """
    groups: list[tuple[set[str], list[dict[str, Any]]]] = []
    for record in records:
        urls = {str(s.get("url", "")).strip() for s in record.get("sources", []) if s.get("url")}
        for group_urls, members in groups:
            if group_urls & urls:
                group_urls.update(urls)
                members.append(record)
                break
        else:
            groups.append((set(urls), [record]))
    return [reduce(merge_records, members) for _, members in groups]


def _load_needs_review_queue(base_dir: Path) -> list[dict[str, Any]]:
    """Load HELD records from a committed ``_needs_review/queue.json`` under ``base_dir``.

    Held records must re-enter dedupe every run so they persist and can be promoted —
    in AUTO mode there is no STAGED_DIR, so the queue on main (``data_dir``) is the
    only carryover path; without this a held record whose source rolls off the feed
    would be dropped when the queue is regenerated.
    """
    queue = base_dir / NEEDS_REVIEW_RELPATH
    if not queue.exists():
        return []
    records: list[dict[str, Any]] = []
    for item in json.loads(queue.read_text(encoding="utf-8")):
        record = item.get("record") if isinstance(item, dict) else None
        if isinstance(record, dict):
            records.append(record)
    return records


def _load_staged_carryover() -> list[dict[str, Any]]:
    """Prior STAGED (not-yet-on-main) records, restored so they persist regardless of
    re-fetch or re-extraction.

    The scrape workflow archives the data-staging branch's shards into ``STAGED_DIR``
    before the run; folding them back into dedupe means a force-pushed staging branch
    can never destroy the only copy — even if the source doc rolled off the feed or
    its re-extraction failed. Absent ``STAGED_DIR`` (auto mode, tests) => none.
    """
    staged_dir = os.environ.get("STAGED_DIR", "").strip()
    if not staged_dir or not Path(staged_dir).exists():
        return []
    base = Path(staged_dir)
    records: list[dict[str, Any]] = []
    for shard in iter_shard_files(base):
        records.extend(json.loads(shard.read_text(encoding="utf-8")))
    # Prior needs-review HOLDS persist too: a record held from auto-publish whose
    # source rolled off the feed would otherwise vanish from the queue (same loss
    # class as a staged publish). Re-entering dedupe, it is re-split — still held if it
    # still fails the gate, or promoted to the site if a court update cleared it.
    queue = base / NEEDS_REVIEW_RELPATH
    if queue.exists():
        for item in json.loads(queue.read_text(encoding="utf-8")):
            record = item.get("record") if isinstance(item, dict) else None
            if isinstance(record, dict):
                records.append(record)
    return records


def _update_ledger(
    ledger: Ledger,
    doc_outcomes: dict[str, str],
    published: list[dict[str, Any]],
    existing_urls: set[str],
    review: list[dict[str, Any]],
    needs_review: list[dict[str, Any]],
    run_date: str,
    report: RunReport,
    data_dir: Path,
) -> None:
    """Record each processed document's outcome and persist the ledger.

    An ``extracted`` document resolves to one of these fates:
    - its URL is among the records ALREADY ON ``main`` (``existing_urls``) -> settle
      ``published`` (confirmed on disk; a merged review PR, or a landed auto-commit);
    - it published to THIS run's tree but is NOT yet on main -> ``staged_pending``,
      NOT settled, so it re-surfaces every run until the record reaches main. This is
      what stops a force-pushed staging branch from destroying the only copy;
    - it is quarantined to the review queue, OR held in the needs-review queue by the
      graduated gate -> NOT settled (``continue``), re-surfaces until a human resolves
      or promotes it (its record copy persists via carryover meanwhile);
    - it was dropped by the launch scope window (state/lookback) -> ``out_of_window``,
      terminal for coverage accounting under the CURRENT window. (Widening
      LAUNCH_STATES/LOOKBACK later requires deleting the ledger-state branch.)
    ``out_of_scope``/``not_a_case``/``failed`` come straight from extraction.
    """
    published_urls = _record_urls(published)
    # A held-but-published-quality record is NOT settled either: it must re-surface so a
    # human can promote it (or a later court update can clear the gate automatically).
    held_urls = _record_urls(needs_review) | {
        str(source.get("url", ""))
        for item in review
        for source in item["record"].get("sources", [])
    }
    for url, outcome in doc_outcomes.items():
        # The ledger KEY stays the RAW doc url (injective — no PII-collapse collision).
        # But records store SANITISED source urls, so membership must be tested in the
        # sanitised space: a PII-shaped url (a redacted digit run) still matches its own
        # stored record. Without this, a quarantined review doc whose url is PII-shaped
        # falls through to out_of_window, settles, and is silently lost (never a shard,
        # never re-surfaced — the carryover restores year shards only, not _review).
        canon = sanitize_string(url)
        # A transient re-extraction FAILURE must never discard a staged record — keep
        # it pending (its copy persists via staged_carryover) and retry indefinitely.
        if outcome == "failed" and ledger.is_pending(url):
            continue
        # A doc quarantined/held THIS run must NEVER settle — checked FIRST, before the
        # published/existing classification. The sanitised URL space is non-injective,
        # so a review doc whose canon collides with an on-main published record would
        # otherwise settle "published" and be lost (carryover restores shards + the
        # held queue, never _review). Erring toward re-surfacing (a rare colliding
        # published doc merely re-processes) is the safe direction.
        if outcome == "extracted" and canon in held_urls:
            continue
        if outcome == "extracted":
            if canon in existing_urls:
                outcome = "published"  # confirmed on main
            elif canon in published_urls:
                outcome = "staged_pending"  # staged this run, not yet on main
            elif ledger.is_pending(url):
                outcome = "staged_pending"  # defense: never downgrade a pending record
            else:
                outcome = "out_of_window"  # scope-filtered (state/lookback)
        if ledger.record(url, outcome, run_date) == "failed_permanent":
            _log(report, f"failed_permanent after retries (manual review): {url}")
    save_ledger(data_dir, ledger)


def _assert_no_pii(data_dir: Path) -> None:
    """Run scripts/pii_guard over the written tree; raise on any finding."""
    findings = [f for json_file in iter_json_files([data_dir]) for f in scan_json_file(json_file)]
    if findings:
        raise RuntimeError(
            f"pii_guard blocked the write: {len(findings)} finding(s); first: {findings[0]}"
        )


def _render_report(report: RunReport, run_date: str) -> str:
    def table(title: str, counts: dict[str, int]) -> str:
        if not counts:
            return f"### {title}\n\n_none_\n"
        rows = "\n".join(f"| {k or '—'} | {v} |" for k, v in counts.items())
        return f"### {title}\n\n| key | count |\n|---|---|\n{rows}\n"

    return (
        f"# Data review: {run_date}\n\n"
        f"**Mode:** {config.launch_mode()} · **Scope:** {report.scope}\n\n"
        "| metric | value |\n|---|---|\n"
        f"| Fetched documents | {report.fetched} |\n"
        f"| Processed this run | {report.processed} |\n"
        f"| Skipped (already settled) | {report.skipped_settled} |\n"
        f"| Extracted candidates | {report.extracted} |\n"
        f"| Rejected (out of scope) | {report.rejected_out_of_scope} |\n"
        f"| **Auto-eligible (on site)** | {report.published} |\n"
        f"| **Held for review (not on site)** | {report.needs_review} |\n"
        f"| New this run | {report.new} |\n"
        f"| Materially changed | {report.material} |\n"
        f"| Re-checked (unchanged) | {report.rechecked} |\n"
        f"| Review queue (below threshold) | {report.review} |\n"
        f"| Verified (fresh, this run) | {report.verified} |\n"
        f"| Verifier-demoted (quarantined) | {report.verify_demoted} |\n"
        f"| Est. extraction cost | ${report.estimated_usd:.4f} |\n"
        f"| Est. verification cost | ${report.verify_usd:.4f} |\n"
        f"| **Month-to-date spend** | ${report.month_to_date:.4f} / ${report.monthly_cap:.2f} |\n"
        + (
            "| ⚠ **Monthly budget** | EXHAUSTED — no new Gemini calls this run; "
            "extraction resumes next month |\n"
            if report.budget_exhausted
            else ""
        )
        + "\n"
        f"{table('Auto-eligible by state', report.state_counts)}\n"
        f"{table('Auto-eligible by source', report.source_counts)}\n"
        f"{table('Held for review (why)', report.needs_review_reasons)}\n"
        f"{table('Review queue (reasons)', report.review_reasons)}\n"
        "> **Auto-eligible** records (non-minor, no named accused, durable source, "
        "confidence ≥ 0.85) publish to the site on merge. **Held-for-review** records "
        "(`data/_needs_review/queue.json`) are minors, named accused, live-blog-only, "
        "or the 0.80-0.84 band - a human promotes them; they never auto-publish. Every "
        "record is cited to a public source; accused names appear only from court "
        "records. Review the `data/` diff, `data/_needs_review/`, and `data/_review/` "
        "before merging. Nothing publishes until a human merges this PR.\n"
    )


def _write_logs(report: RunReport, logs_dir: Path, run_date: str) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "run.log").write_text("\n".join(report.logs) + "\n", encoding="utf-8")
    (logs_dir / "run_summary.env").write_text(
        # UPDATED now means MATERIAL changes only (status/court/sections/accused/severity) —
        # re-sightings are RECHECKED and never inflate the "~N updated" commit message (§1).
        f"NEW={report.new}\nUPDATED={report.material}\nRECHECKED={report.rechecked}\n"
        f"REVIEW={report.review}\n"
        f"PUBLISHED={report.published}\nNEEDS_REVIEW={report.needs_review}\n"
        f"REJECTED={report.rejected_out_of_scope}\n"
        f"FETCHED={report.fetched}\nPROCESSED={report.processed}\n"
        f"SKIPPED={report.skipped_settled}\nEXTRACTED={report.extracted}\n"
        f"COST={report.estimated_usd:.6f}\n"
        f"VERIFIED={report.verified}\nVERIFY_DEMOTED={report.verify_demoted}\n"
        f"VERIFY_COST={report.verify_usd:.6f}\n"
        f"MONTH_TO_DATE={report.month_to_date:.6f}\n"
        f"MONTHLY_CAP={report.monthly_cap:.6f}\n"
        f"BUDGET_EXHAUSTED={1 if report.budget_exhausted else 0}\n"
        f"SUBMISSIONS={report.submissions}\n"
        f"SUBMISSIONS_PUBLISHED={report.submissions_published}\n",
        encoding="utf-8",
    )
    (logs_dir / "run_report.md").write_text(_render_report(report, run_date), encoding="utf-8")


def _print_journey(
    out: TextIO,
    raw_docs: list[RawDocument],
    pre_sanitize: dict[str, Any],
    sanitized: dict[str, Any],
    published: dict[str, Any],
    sharded: dict[str, Any] | None,
) -> None:
    def block(title: str, value: Any) -> None:
        out.write(f"\n--- {title} ---\n")
        out.write(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
        out.write("\n")

    out.write("\n=== ONE RECORD'S JOURNEY (synthetic TESTVILLE fixture) ===\n")
    block(
        "1. RAW documents",
        [{"url": d.url, "publisher": d.publisher, "text": d.text} for d in raw_docs],
    )
    block("2. EXTRACTED (pre-sanitize; note the forbidden 'victim' key)", pre_sanitize)
    block("3. SANITIZED (forbidden keys dropped, PII values redacted)", sanitized)
    block("4. DEDUPED / MERGED (sources unioned, court status wins)", published)
    if sharded is not None:
        block("5. SHARDED (deterministic id, first_published, pending_days assigned)", sharded)


def run(
    *,
    dry_run: bool,
    data_dir: Path,
    logs_dir: Path,
    run_date: str,
    out: TextIO,
    docs: list[RawDocument] | None = None,
    extract_client: ExtractionClient | None = None,
    verify_client: verify.VerificationClient | None = None,
    mode: str = "discover",
) -> RunReport:
    """Execute one pipeline run and return a :class:`RunReport`.

    ``mode`` (§2): ``discover`` (default, daily) fetches every source and CREATES new records;
    ``refresh`` (weekly) fetches only court-record sources and only UPDATES records that already
    exist (matched by exact anchor / id) — it never creates a new record. Splitting the two
    keeps the temporal architecture honest at scale: feeds can grow without producing a flood
    of never-re-checked first reports.
    """
    report = RunReport()
    is_refresh = mode == "refresh"
    states = config.launch_states()
    lookback = config.launch_lookback_days()
    report.scope = _scope_label(states, lookback)

    # HARD scope gate (real runs only): never run SILENTLY unscoped. LAUNCH_STATES
    # must be explicitly set — ALL (all states, intentional) or a comma list. A bare
    # cron with no inputs once defaulted to empty and ran all-states-all-time; this
    # turns that silent default into a loud refusal. An explicit ALL with no lookback
    # is allowed but the heartbeat's scope line makes the window visible daily.
    # Fixtures/dry-run are exempt (TESTVILLE, never networked).
    if not dry_run and not config.scope_is_configured():
        raise RuntimeError(
            "launch scope unresolved: LAUNCH_STATES is unset. Refusing to run unscoped. "
            "Set LAUNCH_STATES=ALL (or a comma list) and LAUNCH_LOOKBACK_DAYS."
        )

    ledger: Ledger | None = None
    doc_outcomes: dict[str, str] = {}
    existing: list[dict[str, Any]] = []
    existing_urls: set[str] = set()
    staged_carryover: list[dict[str, Any]] = []
    if dry_run:
        raw_docs = fixtures.fixture_raw_documents()
        extractions = fixtures.fixture_extractions()
        report.estimated_usd = _illustrative_cost(raw_docs)
        _log(report, f"dry-run: {len(extractions)} fixture extractions (no network, no Gemini)")
    else:
        raw_docs = docs if docs is not None else _fetch_documents(run_date, court_only=is_refresh)
        # Skip documents already settled in prior runs so the budget goes to the
        # backlog TAIL — turns provider degradation into delay, not lost coverage.
        ledger = load_ledger(data_dir)
        # Canonicalise state codes (TS->TG, ...) on load so a state is never split across
        # two codes in ids/shards/scorecards. An existing record whose state changes has
        # its id cleared so write_shards re-mints a matching one (see _canonicalize_state).
        existing = [_canonicalize_state(r) for r in _load_existing_published(data_dir)]
        existing_urls = _record_urls(existing)  # canonical (stored URLs are sanitised)
        # Prior staged records persist even if their source rolled off the feed or
        # fails re-extraction — so a force-pushed staging branch never loses them.
        # Held (needs-review) records re-enter too. In STAGED mode the archive
        # (_load_staged_carryover, a superset of main) already restores the held queue;
        # in AUTO mode there is no archive, so the committed queue on main (data_dir) is
        # the only carryover path. Load exactly ONE source — loading both in staged mode
        # would double-feed each held record and spam _review with self-matches.
        staged_carryover = _load_staged_carryover()
        if not os.environ.get("STAGED_DIR", "").strip():
            staged_carryover += _load_needs_review_queue(data_dir)
        staged_carryover = [_canonicalize_state(r) for r in staged_carryover]
        # A staged_pending record that has since reached main settles now, so it is
        # not needlessly re-extracted; one that hasn't stays pending and re-surfaces.
        ledger.confirm_published(existing_urls, run_date)
        to_process = [d for d in raw_docs if ledger.should_process(d.url)]
        # Extract likely sexual-offence documents FIRST. Fetched feeds are mostly
        # non-crime city news, so a wall-clock-bounded run that truncates would
        # otherwise spend its whole budget on irrelevant docs and reach no cases. This
        # only REORDERS (no doc is dropped); the ledger processes the tail on later
        # runs. A stable sort keeps feed order within each group.
        to_process.sort(key=lambda d: 0 if _looks_offence_relevant(d) else 1)
        report.processed = len(to_process)
        report.skipped_settled = len(raw_docs) - len(to_process)
        _log(
            report,
            f"fetched {len(raw_docs)} documents ({report.processed} to process, "
            f"{report.skipped_settled} already settled)",
        )
        # MONTHLY BUDGET GATE: if this calendar month's cumulative spend already meets the
        # cap, abort the PAID work cleanly — make no new Gemini calls this run — rather than
        # silently doing a partial extraction. Existing records still regenerate/refresh
        # below (free); a new month resets the cap. The heartbeat + ops issue flag it.
        mtd_before = spend.month_to_date(data_dir, run_date)
        report.monthly_cap = config.monthly_max_usd()
        if to_process and mtd_before >= report.monthly_cap:
            report.budget_exhausted = True
            extractions = []
            _log(
                report,
                f"MONTHLY BUDGET EXHAUSTED: month-to-date ${mtd_before:.4f} >= cap "
                f"${report.monthly_cap:.2f}; made NO new Gemini calls (skipped "
                f"{len(to_process)} document(s)). Extraction resumes next month; posting "
                "to the ops issue.",
            )
            result = None
        else:
            result = extract(
                to_process, client=extract_client, cost_log_path=logs_dir / "gemini_cost.json"
            )
        if result is None:
            _log(report, "extracted 0 candidates (budget exhausted — extraction skipped)")
        else:
            doc_outcomes = dict(result.doc_outcomes)
            extractions = result.records
            report.estimated_usd = result.estimated_usd
            report.rejected_out_of_scope = result.rejected_out_of_scope
            detail = f"{result.failed} failed"
            if result.rejected_out_of_scope:
                detail += f", {result.rejected_out_of_scope} out-of-scope rejected"
            if result.failovers:
                detail += f", {result.failovers} model failover(s)"
            if result.truncated:
                detail += f", TRUNCATED ({result.truncated_reason})"
            if result.aborted:
                detail += ", ABORTED (all models exhausted / provider overload)"
            _log(
                report,
                f"extracted {len(extractions)} candidates ({detail}); "
                f"est ${result.estimated_usd:.6f}",
            )
            for sample in result.error_samples:
                _log(report, f"provider error: {sample}")

    report.fetched = len(raw_docs)
    report.submissions = sum(1 for d in raw_docs if d.publisher == "Community submission")
    report.extracted = len(extractions)

    # Canonicalise the model's state code (TS->TG, ...) BEFORE the scope filter reads it,
    # so a state is keyed one way everywhere (fresh extractions carry no id yet).
    extractions = [_canonicalize_state(record) for record in extractions]

    # A record with no model-extracted date falls back to the date the source was
    # retrieved — which IS the field's meaning ("date the case was publicly
    # reported/registered"): for a media item that is its publication date. Without
    # this a null date fails the schema's required string type and aborts the whole
    # write. Court records normally carry a real order/FIR date and are untouched.
    for _record in extractions:
        if not _record.get("incident_reported_date"):
            _retrieved = next(
                (str(s.get("retrieved")) for s in _record.get("sources", []) if s.get("retrieved")),
                None,
            )
            if _retrieved:
                _record["incident_reported_date"] = _retrieved

    # Bound this run to the configured states + lookback window FIRST, on the raw
    # extraction. Only state + date (both non-PII) are read here; nothing is written.
    # A record already STAGED (pending on the review branch, not yet on main) is kept
    # in scope regardless — otherwise a rolling lookback / narrowed states could drop
    # its only copy from the regenerated tree before a human merges it.
    def _is_staged(record: dict[str, Any]) -> bool:
        return ledger is not None and any(
            ledger.is_pending(str(s.get("url", ""))) for s in record.get("sources", [])
        )

    in_scope = [r for r in extractions if _in_scope(r, states, lookback, run_date) or _is_staged(r)]
    if len(in_scope) != len(extractions):
        _log(report, f"scope: {len(in_scope)}/{len(extractions)} in scope ({report.scope})")

    # VERIFICATION STAGE (guardrail L): a stronger, web-grounded model re-checks each
    # in-scope candidate against its source BEFORE it can publish, stamping `verified`.
    # Runs on raw (pre-sanitize) records so corrections are sanitised afterwards. Opt-in
    # (VERIFY_ENABLED) — the auto-flip turns it on; never runs in dry-run.
    # Source URLs (sanitised, to match the published records) of records the verifier
    # could not ASSESS — a transient provider error, missing source text, or exhausted
    # budget — as opposed to a genuine "not-a-case" demotion. A FRESH such record is HELD
    # for human review, not quarantined, so a legitimate case is never lost to a 503/504.
    verify_incomplete_urls: set[str] = set()
    if config.verification_enabled() and not dry_run and in_scope:
        source_text_by_url = {doc.url: doc.text for doc in raw_docs}
        client = verify_client or verify.default_verify_client(config.verification_model())
        vresult = verify.verify_records(
            in_scope, source_text_by_url, client, cost_log_path=logs_dir / "verify_cost.json"
        )
        in_scope = vresult.records
        verify_incomplete_urls = {sanitize_string(u) for u in vresult.incomplete_source_urls}
        report.verified = vresult.verified_count
        report.verify_demoted = vresult.demoted_count
        report.verify_usd = vresult.estimated_usd
        _log(
            report,
            f"verified {vresult.verified_count}, demoted {vresult.demoted_count} "
            f"(skipped {vresult.skipped_budget} over budget); est ${vresult.estimated_usd:.4f}",
        )
        for sample in vresult.error_samples:
            _log(report, f"verifier error: {sample}")
        # Surface WHY cases were declined so the bar is auditable (records stay private).
        for note in vresult.decline_notes[:10]:
            _log(report, f"verifier declined: {note}")

    # LAST GATE BEFORE DISK: sanitize every in-scope candidate (drop forbidden keys,
    # redact PII values, structurally project minor records), then project onto the
    # schema allow-list so no unknown key can survive to a shard OR the review queue.
    case_schema = load_schema()
    sanitized = [
        _drop_null_top_level(_finalize_for_disk(record, case_schema)) for record in in_scope
    ]
    # Route any freshly-extracted record that STILL fails the schema (a required field
    # the model could not supply, an out-of-enum value) to human review, rather than
    # letting one malformed record abort the entire write in write_shards. Existing and
    # carryover records were validated when written, so only fresh records are checked.
    invalid: list[dict[str, Any]] = []
    valid_sanitized: list[dict[str, Any]] = []
    for record in sanitized:
        # id + first_published are assigned later (write_shards), so probe with
        # placeholders to validate every OTHER field (date, status/category enums,
        # minor date granularity). A record that still fails is quarantined, so one
        # malformed record can never abort write_shards' validation of the whole batch.
        probe = {**record, "id": "SKS-2026-XX-000000", "first_published": run_date}
        try:
            validate_record(probe, case_schema)
        except Exception:  # jsonschema.ValidationError — quarantine, never crash
            invalid.append(record)
        else:
            valid_sanitized.append(record)
    if invalid:
        _log(report, f"schema_invalid: {len(invalid)} record(s) routed to review")

    # Fold in records already on main AND prior staged records (both loaded above),
    # so the whole tree regenerates and no staged record is lost by a force-push.
    # The staging branch is a SUPERSET of main (main + staged). A carryover record
    # already on main is MERGED into the main copy by id (not dropped): a prior staged
    # run may have ENRICHED an on-main case — a further-along status, an extra source —
    # and that update must survive even if its source doc has since rolled off the feed.
    # Merging by id also collapses each case to ONE input, so on-main records are not
    # double-fed into dedupe (which would spam the review queue with weak-anchor
    # self-matches). Carryover cases with a new id (staged-only) are folded in as-is.
    base_by_id = {str(r.get("id", "")): r for r in existing if r.get("id")}
    staged_only: list[dict[str, Any]] = []
    for carried in staged_carryover:
        cid = str(carried.get("id", ""))
        if cid and cid in base_by_id:
            base_by_id[cid] = merge_records(base_by_id[cid], carried)
        else:
            staged_only.append(carried)
    base = list(base_by_id.values()) + [r for r in existing if not r.get("id")]
    published, review = dedupe(base + staged_only + valid_sanitized)
    # Schema-invalid records are quarantined alongside dedupe's review queue.
    review = review + [{"reason": "schema_invalid", "record": r} for r in invalid]

    # JURISDICTION gate (§4a): the schema's state pattern is only ^[A-Z]{2}$, so a record
    # whose state the site does not recognise (e.g. "XX") would otherwise publish to a
    # phantom shard/scorecard. Every record here is already canonicalised, so a valid alias
    # like TL->TG is never wrongly caught — only a genuinely unknown code is diverted.
    published, diverted = _split_by_jurisdiction(published)
    review = review + diverted
    if diverted:
        _log(report, f"jurisdiction: {len(diverted)} record(s) routed to review (unknown state)")

    # READABILITY gate (§6a): a FRESH non-minor record with an unreadable summary is
    # quarantined to _review rather than published — the deterministic backstop behind the
    # extraction prompt, and what keeps the CI readability assertion from tripping on a fresh
    # record. Already-live records are grandfathered (never demoted by a newer rule).
    grandfathered_ids = {str(r.get("id", "")) for r in existing if r.get("id")}
    published, unreadable = _split_unreadable(published, grandfathered_ids)
    review = review + unreadable
    if unreadable:
        _log(report, f"readability: {len(unreadable)} fresh record(s) routed to review (§6a)")

    # CORRECTIONS (human-authored, corrections/<id>.yml): the reviewed escape hatch for fixes
    # the pipeline cannot make itself. A quarantined id is routed OUT to _review; a record
    # with field overrides has them applied and is RE-SANITISED (so a corrected value still
    # passes every gate), then marked `corrected`. Applied here, before the graduated gate.
    corrections = load_corrections()
    if corrections:
        q_ids = quarantined_ids(corrections)
        quarantined = [r for r in published if str(r.get("id", "")) in q_ids]
        published = [r for r in published if str(r.get("id", "")) not in q_ids]
        review = review + [{"reason": "operator_quarantine", "record": r} for r in quarantined]
        corrected_count = 0
        applied: list[dict[str, Any]] = []
        for record in published:
            fixed = apply_correction(record, corrections)
            if fixed is not record:
                fixed = _finalize_for_disk(fixed, case_schema)
                corrected_count += 1
            applied.append(fixed)
        published = applied
        if quarantined or corrected_count:
            _log(
                report,
                f"corrections: {len(quarantined)} quarantined, {corrected_count} field-corrected",
            )

    # REFRESH mode (§2): update-only. Keep just the records that correspond to one already on
    # the site (same id, or a shared exact anchor after the court re-query merged into it); any
    # brand-new case a court source surfaced is DROPPED here — discovery is the daily run's job.
    if is_refresh:
        existing_ids = {str(r["id"]) for r in existing if r.get("id")}
        existing_anchors: set[str] = set()
        for record in existing:
            existing_anchors |= exact_anchor_keys(record)
        kept = [
            r
            for r in published
            if str(r.get("id", "")) in existing_ids or (exact_anchor_keys(r) & existing_anchors)
        ]
        created = len(published) - len(kept)
        if created:
            _log(report, f"refresh: dropped {created} newly-discovered record(s) (update-only)")
        held_narrative = _preserve_refresh_narrative(kept, existing)
        if held_narrative:
            _log(report, f"refresh: held reviewed narrative on {held_narrative} record(s) (§1b)")
        published = kept

    # GRADUATED auto-publish gate: split the published set into what may ship
    # unattended (auto_eligible) and what a human must promote first (needs_review:
    # minors, named accused, live-blog-only, the 0.80..0.84 band). Only auto_eligible
    # is sharded onto the public site; needs_review is held in its own queue (carried
    # over so it is never lost). In staged mode both ride the review PR — the labels
    # tell the human which would auto-publish; in auto mode only auto_eligible lands.
    approved = _load_approved(data_dir)
    approved_only = config.publish_approved_only()
    verified_mode = config.verification_enabled()
    # Records already published on main were vetted before this run (human-approved in
    # the supervised phase, or verified in a prior auto run). They are GRANDFATHERED:
    # turning the verifier on must never unpublish an already-live record just because
    # its source doc has rolled off the feed and it cannot be re-verified this run.
    # Only genuinely FRESH cases (an id not already on the site) face the verified-gate.
    already_published_ids = {str(r.get("id", "")) for r in existing if r.get("id")}
    # Provenance of every record that existed BEFORE this run (already on a shard OR in
    # the carried-over held queue / staged archive). Only a record composed PURELY of
    # this run's FRESH extractions may be quarantined to _review; anything that carries
    # prior content MUST be held (never dropped) — the verifier only runs on fresh
    # candidates, so a carryover held record can never earn `verified` and would
    # otherwise be swept out of the queue and lost. Matched by id AND source URL (both
    # are in sanitised space at this point, so they align with the published records).
    prior_records = existing + staged_carryover
    nonfresh_ids = {str(r.get("id", "")) for r in prior_records if r.get("id")}
    nonfresh_urls = {
        url
        for r in prior_records
        for url in (str(s.get("url", "")).strip() for s in r.get("sources") or [])
        if url
    }

    def _has_carryover_content(rec: dict[str, Any]) -> bool:
        if str(rec.get("id", "")) in nonfresh_ids:
            return True
        return any(str(s.get("url", "")).strip() in nonfresh_urls for s in rec.get("sources") or [])

    auto_eligible: list[dict[str, Any]] = []
    needs_review_items: list[tuple[dict[str, Any], list[str]]] = []
    to_promote: list[dict[str, Any]] = []
    for record in published:
        if verified_mode:
            # A dedupe merge can flip minor_involved AFTER the per-candidate sanitize
            # pass, so re-run the FULL last gate here (idempotent otherwise) so any merged
            # minor is re-projected to the minimal non-identifying shape BEFORE publish.
            safe = _finalize_for_disk(record, case_schema)
            # 1. Already live on the site -> grandfathered: re-projected for safety but
            #    NEVER demoted. The verifier flip must not unpublish a live record whose
            #    source has rolled off the feed and cannot be re-verified this run.
            if str(safe.get("id", "")) in already_published_ids:
                auto_eligible.append(safe)
                continue
            # 2. Human-approved -> promote the already-safe form, exactly as in supervised
            #    mode. An explicit operator approval is honoured even under the verifier
            #    (else an approved-but-unverifiable record would be quarantined and lost).
            if _is_approved(record, approved):
                to_promote.append(record)
                continue
            # 3. A VERIFIED fresh candidate publishes if it clears the graduated gate
            #    (minus minor_involved — a verified minor's content is deterministic),
            #    else it is held for a human (named accused, POCSO mismatch, ...).
            if safe.get("verified"):
                holds = _verified_hold_reasons(safe)
                (needs_review_items.append((safe, holds)) if holds else auto_eligible.append(safe))
                continue
            # 4. NOT verified. HOLD it for a human (never lose it) when it carries prior
            #    content OR the verifier could not ASSESS it (a transient 503/504, missing
            #    source, or exhausted budget — `verify_incomplete_urls`). Only a purely-
            #    fresh candidate the verifier actually DECLINED is quarantined to _review.
            incomplete = any(
                str(s.get("url", "")).strip() in verify_incomplete_urls
                for s in record.get("sources") or []
            )
            if _has_carryover_content(record) or incomplete:
                reason = "verify_incomplete" if incomplete else "unverified_held"
                held = _verified_hold_reasons(safe) or [reason]
                needs_review_items.append((safe, held))
            else:
                review.append({"reason": "unverified", "record": safe})
            continue
        # Supervised phase (no verifier): graduated gate + approval allowlist. Even an
        # auto-eligible record is held until approved, so nothing publishes unapproved.
        ok, _reasons = auto_publish_eligible(record)
        if _is_approved(record, approved):
            to_promote.append(record)
        elif ok and not approved_only:
            auto_eligible.append(record)
        else:
            needs_review_items.append((record, _reasons or ["awaiting_approval"]))
    # Publish human-approved held records: merge same-article duplicates within the
    # approved set, then re-run the FULL last gate (coerce minor -> sanitize/project ->
    # withhold unsourced accused names) so a promoted minor is re-projected to the
    # minimal non-identifying shape and no unsourced name ships — approval never
    # weakens a guardrail; it only allows the already-safe form onto the site.
    promoted_records = [
        _finalize_for_disk(record, case_schema) for record in _dedup_approved_by_url(to_promote)
    ]
    auto_eligible.extend(promoted_records)
    promoted = len(promoted_records)
    needs_review_records = [record for record, _ in needs_review_items]
    _log(
        report,
        f"deduped: {len(published)} published "
        f"({len(auto_eligible)} auto-eligible incl. {promoted} human-approved, "
        f"{len(needs_review_items)} held for review), {len(review)} quarantined",
    )

    # Reserve the held records' ids so a fresh auto-eligible mint can never collide
    # with an off-shard held id and fuse two distinct cases.
    write_result: WriteResult = write_shards(
        auto_eligible, data_dir, run_date=run_date, reserve=needs_review_records
    )
    # Feed the recent list the FINALIZED records (write_result.records) — they carry the
    # assigned ids. auto_eligible's freshly-minted records have no id yet, which would
    # ship id=null to recent.json and break the feed's case links.
    _write_recent(write_result.records, data_dir)
    _write_needs_review(needs_review_items, data_dir)
    _write_review(review, data_dir, run_date)
    _write_merge_review(write_result.records, data_dir, run_date)
    _write_coverage(write_result.records, data_dir, run_date)

    # Update the processed-document ledger (real runs only). A record is settled
    # "published" only once it is on main; until then it is staged_pending and
    # re-surfaces each run — a force-pushed staging branch can never lose it. Held
    # (needs-review) and quarantined docs never settle, so they re-surface too.
    if ledger is not None:
        _update_ledger(
            ledger,
            doc_outcomes,
            auto_eligible,
            existing_urls,
            review,
            needs_review_records,
            run_date,
            report,
            data_dir,
        )

    # Fold this run's estimated spend (extraction + verification) into the month-to-date
    # ledger (real runs only) so the monthly cap is enforced across the month's runs. A
    # budget-exhausted run adds ~0 and stays idempotent. Written before the PII assertion
    # so the ledger file (aggregate dollars only, no case content) is scanned too.
    if not dry_run:
        report.month_to_date = spend.record_spend(
            data_dir, run_date, report.estimated_usd + report.verify_usd
        )

    # Independent final assertion over EVERY file just written (shards + review queue
    # + needs-review queue). A hit fails the run before any commit — not post-push CI.
    _assert_no_pii(data_dir)

    report.new = write_result.new
    report.material = write_result.material
    report.rechecked = write_result.rechecked
    report.review = len(review)
    report.published = write_result.published
    report.needs_review = len(needs_review_items)
    report.submissions_published = sum(
        1
        for r in write_result.records
        if any(str(s.get("publisher", "")) == "Community submission" for s in r.get("sources", []))
    )
    if report.submissions:
        _log(
            report,
            f"submissions (§6): {report.submissions} fetched, "
            f"{report.submissions_published} published",
        )
    report.state_counts = dict(
        sorted(Counter(str(r.get("state", "")) for r in auto_eligible).items())
    )
    report.source_counts = dict(
        sorted(
            Counter(
                str(s.get("publisher", "")) for r in auto_eligible for s in r.get("sources", [])
            ).items()
        )
    )
    report.review_reasons = dict(sorted(Counter(item["reason"] for item in review).items()))
    report.needs_review_reasons = dict(
        sorted(Counter(reason for _, reasons in needs_review_items for reason in reasons).items())
    )
    _write_logs(report, logs_dir, run_date)

    if dry_run:
        sharded = _first_sharded_record(data_dir)
        _print_journey(
            out,
            raw_docs,
            in_scope[0] if in_scope else {},
            sanitized[0] if sanitized else {},
            published[0] if published else {},
            sharded,
        )
        out.write("\n=== DRY-RUN RESULT ===\n")
        out.write(
            f"published={report.published} new={report.new} material={report.material} "
            f"rechecked={report.rechecked} review={report.review}\n"
        )
        out.write(
            f"Gemini: 0 live calls (fixtures). Illustrative cost estimate for these "
            f"documents at {config.gemini_models()[0]} rates: ${report.estimated_usd:.6f}\n"
        )
    return report


def _first_sharded_record(data_dir: Path) -> dict[str, Any] | None:
    index_path = data_dir / "index.json"
    if not index_path.exists():
        return None
    index = json.loads(index_path.read_text(encoding="utf-8"))
    shards = index.get("shards", [])
    if not shards:
        return None
    records = json.loads((data_dir / shards[0]["path"]).read_text(encoding="utf-8"))
    return records[0] if records else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline", description="Sakshi daily pipeline.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run offline against synthetic fixtures; write to a throwaway directory.",
    )
    parser.add_argument("--data-dir", type=Path, default=None, help="Output data directory.")
    parser.add_argument("--run-date", default=None, help="Override run date (YYYY-MM-DD).")
    parser.add_argument(
        "--mode",
        choices=("discover", "refresh"),
        default="discover",
        help="discover (daily, creates new records) or refresh (weekly, court-only, "
        "updates existing records' status — never creates).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    run_date = args.run_date or date.today().isoformat()

    if args.data_dir is not None:
        data_dir = args.data_dir
        logs_dir = config.LOGS_DIR
    elif args.dry_run:
        data_dir = Path(tempfile.mkdtemp(prefix="sakshi-dryrun-"))
        logs_dir = data_dir / "logs"
    else:
        data_dir = config.DATA_DIR
        logs_dir = config.LOGS_DIR

    try:
        run(
            dry_run=args.dry_run,
            data_dir=data_dir,
            logs_dir=logs_dir,
            run_date=run_date,
            out=sys.stdout,
            mode=args.mode,
        )
    except Exception as exc:  # pragma: no cover - top-level failure path
        print(f"pipeline run failed: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\nDry-run wrote to: {data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
