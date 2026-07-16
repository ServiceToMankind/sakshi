"""Sharded output writer.

Regenerates the ``data/`` tree from the given records: assigns deterministic,
never-reused IDs, validates every record against ``schemas/case.schema.json``,
and writes per-year/state shards plus ``summary.json`` and ``index.json``.

Safety of a re-run:
- Every gate (unique IDs, schema validation, summary size budget) runs BEFORE any
  file is touched.
- All output is staged to ``.tmp`` files and only then renamed into place, so a
  mid-write error never leaves a half-updated tree.
- Stale shards are removed only after every rename has succeeded.

IDs are stable across runs: the committed shards are the canonical store. A record
already carrying a valid ID keeps it; a case seen in a previous run (matched on
ANY of its anchors — CNR or year-qualified FIR) reuses its old ID; only genuinely
new cases mint a new serial. ``scripts/pii_guard`` runs as the final assertion.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from pipeline import config
from pipeline.dedupe import exact_anchor_keys
from pipeline.severity import is_aggravated, severity_label
from pipeline.validate import iter_shard_files, load_schema, validate_record

# Accountability-layer summary bounds (keep summary.json within its byte budget).
_SCALE_DAYS = 120  # length of the daily-ingestion heat strip retained in summary.json
_MAX_JURISDICTIONS = 120  # cap the (worst-first) scorecard so summary.json can't overflow
_CLOSED_STATUSES = frozenset({"CONVICTED", "ACQUITTED", "QUASHED", "CLOSED"})

__all__ = ["SHARD_SPLIT_BYTES", "SUMMARY_MAX_BYTES", "WriteResult", "write_shards"]

SUMMARY_MAX_BYTES = config.SUMMARY_MAX_BYTES
SHARD_SPLIT_BYTES = config.SHARD_SPLIT_BYTES

_ID_RE = re.compile(r"^SKS-\d{4}-[A-Z]{2}-\d{6}$")
_ACTIVE_STATUSES = frozenset({"FIR_FILED", "CHARGESHEETED", "UNDER_TRIAL", "APPEAL_PENDING"})


@dataclass
class WriteResult:
    """Outcome of a shard write: counts, the shard paths, and the finalized records."""

    published: int = 0
    new: int = 0
    updated: int = 0
    shards: list[str] = field(default_factory=list)
    # The records AS WRITTEN — with their assigned ids / last_verified / pending_days.
    # Callers that need the canonical published form (e.g. the recent-feed writer) must
    # use this, NOT the pre-write input, whose freshly-minted records have no id yet.
    records: list[dict[str, Any]] = field(default_factory=list)


def _anchor_keys(record: dict[str, Any]) -> list[str]:
    """Every stable identity anchor for a case (for cross-run ID reuse).

    Exact anchors (CNR / year-qualified FIR) when available; otherwise an
    anonymous key that INCLUDES the court name so two distinct courts never
    collapse to one ID.
    """
    keys = sorted(exact_anchor_keys(record))
    if keys:
        return keys
    court = str((record.get("court") or {}).get("name", "")).strip().lower()
    sections = ",".join(sorted(record.get("offence_sections") or []))
    return [
        f"anon:{record.get('state', '')}|{record.get('district', '')}"
        f"|{record.get('incident_reported_date', '')}|{sections}|{court}"
    ]


def _year(record: dict[str, Any], run_date: str) -> str:
    reported = str(record.get("incident_reported_date", ""))
    if len(reported) >= 4 and reported[:4].isdigit():
        return reported[:4]
    return run_date[:4]


def _pending_days(record: dict[str, Any], run_day: date) -> int | None:
    try:
        reported = date.fromisoformat(str(record["incident_reported_date"]))
    except (KeyError, ValueError, TypeError):
        return None
    return max((run_day - reported).days, 0)


def _read_existing(data_dir: Path) -> tuple[dict[str, str], dict[tuple[str, str], int], set[str]]:
    """Return (anchor-key -> id, (year,state) -> max serial, all ids) from disk.

    An unreadable or corrupt existing shard is a HARD error — silently skipping it
    would risk re-minting an ID it already holds or dropping its cases.
    """
    key_to_id: dict[str, str] = {}
    max_serial: dict[tuple[str, str], int] = {}
    all_ids: set[str] = set()
    if not data_dir.exists():
        return key_to_id, max_serial, all_ids
    for shard in iter_shard_files(data_dir):
        try:
            records = json.loads(shard.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read existing shard {shard}: {exc}") from exc
        for record in records:
            record_id = record.get("id", "")
            if not _ID_RE.match(record_id):
                continue
            all_ids.add(record_id)
            for key in _anchor_keys(record):
                key_to_id.setdefault(key, record_id)
            year, state, serial = record_id[4:8], record_id[9:11], int(record_id[12:])
            slot = (year, state)
            max_serial[slot] = max(max_serial.get(slot, 0), serial)
    return key_to_id, max_serial, all_ids


def _seed_from_carryover(
    records: list[dict[str, Any]],
    key_to_id: dict[str, str],
    max_serial: dict[tuple[str, str], int],
    existing_ids: set[str],
    *,
    seed_anchors: bool = True,
) -> None:
    """Reserve serials (and, for carryover, anchors) for input records that carry a
    valid id.

    Staged carryover records were minted in a prior run and are NOT yet on main, so
    ``_read_existing`` (which reads the main checkout only) cannot see their serials.
    Pre-scan them here BEFORE the mint loop — order-independently, so a newly minted
    serial can never collide with a carried-over id regardless of list order. Without
    this, a new case in the same (year,state) slot as an unmerged staged record mints
    a duplicate serial and ``_assert_unique_ids`` crashes the run.

    ``seed_anchors=False`` (used for the off-shard held/``reserve`` records) reserves
    only the serial + id, NOT the anchor keys: seeding a held record's anchors would
    let a DISTINCT new case with a colliding weak anchor (e.g. an empty-district
    fallback key) reuse that held record's id — the very fusion we are preventing.
    """
    for record in records:
        record_id = record.get("id", "")
        if not _ID_RE.match(record_id):
            continue
        existing_ids.add(record_id)
        if seed_anchors:
            for key in _anchor_keys(record):
                key_to_id.setdefault(key, record_id)
        slot = (record_id[4:8], record_id[9:11])
        max_serial[slot] = max(max_serial.get(slot, 0), int(record_id[12:]))


def _assign_ids(
    records: list[dict[str, Any]],
    data_dir: Path,
    run_date: str,
    reserve: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Assign IDs, last_verified, and pending_days. Returns (records, new, updated).

    ``reserve`` records are NOT sharded, but their ids/serials/anchors are reserved so
    a newly minted serial can never collide with one — used to reserve the held
    (needs-review) records' ids, which live off-shard yet must never be re-minted for a
    distinct new case (id fusion). Reserve seeding does not affect the new/updated
    count (only ``records`` are counted).
    """
    key_to_id, max_serial, existing_ids = _read_existing(data_dir)
    if reserve:
        _seed_from_carryover(reserve, key_to_id, max_serial, existing_ids, seed_anchors=False)
    _seed_from_carryover(records, key_to_id, max_serial, existing_ids)
    run_day = date.fromisoformat(run_date)
    new = updated = 0
    finalized: list[dict[str, Any]] = []
    for record in records:
        record = dict(record)
        year, state = _year(record, run_date), str(record["state"])
        current = record.get("id", "")
        if _ID_RE.match(current):
            record_id = current
        else:
            anchors = _anchor_keys(record)
            reused = next((key_to_id[key] for key in anchors if key in key_to_id), None)
            if reused is not None:
                record_id = reused
            else:
                slot = (year, state)
                serial = max_serial.get(slot, 0) + 1
                max_serial[slot] = serial
                record_id = f"SKS-{year}-{state}-{serial:06d}"
                for key in anchors:
                    key_to_id.setdefault(key, record_id)
        record["id"] = record_id
        if record_id in existing_ids:
            updated += 1
        else:
            new += 1
            existing_ids.add(record_id)

        record["last_verified"] = run_date
        pending = _pending_days(record, run_day)
        if pending is not None:
            record["pending_days"] = pending
        finalized.append(record)
    return finalized, new, updated


def _assert_unique_ids(records: list[dict[str, Any]]) -> None:
    ids = [str(r["id"]) for r in records]
    if len(set(ids)) != len(ids):
        dupes = sorted({rid for rid in ids if ids.count(rid) > 1})
        raise ValueError(f"duplicate ids assigned to distinct cases: {dupes}")


def _validate_all(records: list[dict[str, Any]]) -> None:
    schema = load_schema()
    errors: list[str] = []
    for record in records:
        try:
            validate_record(record, schema)
        except Exception as exc:  # jsonschema.ValidationError
            errors.append(f"{record.get('id', '<no-id>')}: {exc}")
    if errors:
        raise ValueError("shard validation failed:\n  " + "\n  ".join(errors))


def _sort_key(record: dict[str, Any]) -> str:
    return str(record.get("incident_reported_date", ""))


def _chunk_by_size(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split a sorted record list so each chunk serializes within SHARD_SPLIT_BYTES."""
    chunks: list[list[dict[str, Any]]] = [[]]
    for record in records:
        chunks[-1].append(record)
        if len(_dumps(chunks[-1]).encode("utf-8")) > SHARD_SPLIT_BYTES and len(chunks[-1]) > 1:
            spill = chunks[-1].pop()
            chunks.append([spill])
    return chunks


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _clear_stale_shards(data_dir: Path, keep: set[Path]) -> None:
    """Remove year-dir shard files no longer produced, keeping _review untouched."""
    for shard in iter_shard_files(data_dir):
        if shard not in keep:
            shard.unlink()


def _build_summary(
    records: list[dict[str, Any]], run_date: str, data_dir: Path, new_count: int
) -> dict[str, Any]:
    status_counts = Counter(str(r.get("status", "UNKNOWN")) for r in records)
    state_counts = Counter(str(r.get("state", "")) for r in records)

    months = _recent_months(run_date, config.MONTHLY_TREND_MONTHS)
    month_counts: Counter[str] = Counter()
    for record in records:
        reported = str(record.get("incident_reported_date", ""))
        if len(reported) >= 7:
            month_counts[reported[:7]] += 1
    monthly_trend = [{"month": m, "count": month_counts.get(m, 0)} for m in months]

    # Day-precise pendency is NON-MINOR only (a minor carries no day-precise date by
    # projection) — mirror the jurisdiction filter. The isinstance guard also avoids an
    # int(None) crash if a legacy shard ever carried pending_days: null.
    pending = [
        {"id": r["id"], "district": r.get("district", ""), "pending_days": int(r["pending_days"])}
        for r in records
        if r.get("status") in _ACTIVE_STATUSES
        and not r.get("minor_involved")
        and isinstance(r.get("pending_days"), int)
    ]
    pending.sort(key=lambda p: p["pending_days"], reverse=True)

    severity_counts, aggravated_total = _severity_summary(records)
    return {
        "generated_at": f"{run_date}T00:00:00Z",
        "total": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "state_counts": dict(sorted(state_counts.items())),
        "monthly_trend": monthly_trend,
        "top_longest_pending": pending[: config.TOP_PENDING_COUNT],
        # --- accountability layer (aggregate/public only; see CLAUDE.md §1a) ---
        "severity_counts": severity_counts,
        "aggravated_total": aggravated_total,
        "jurisdictions": _jurisdiction_scorecards(records),
        "scale": _scale_block(data_dir, run_date, new_count, len(records)),
    }


def _severity_summary(records: list[dict[str, Any]]) -> tuple[dict[str, int], int]:
    """Case counts by charge-derived severity label + count of aggravated cases."""
    counts: Counter[str] = Counter()
    aggravated = 0
    for record in records:
        label = severity_label(record.get("offence_sections"))
        if label:
            counts[label] += 1
        if is_aggravated(record.get("offence_sections")):
            aggravated += 1
    ranked = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return ranked, aggravated


def _jurisdiction_scorecards(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-(state, district) accountability scorecard — aggregate/public only.

    Pendency (median + longest) is derived ONLY from NON-MINOR active cases: a minor
    carries no day-precise date by projection, so an all-minor jurisdiction reports
    ``median_pending_days: null`` and ``longest_pending: null`` — a guardrail, not a gap.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (str(record.get("state", "")), str(record.get("district", "")))
        groups.setdefault(key, []).append(record)

    cards: list[dict[str, Any]] = []
    for (state, district), recs in groups.items():
        by_status = Counter(str(r.get("status", "UNKNOWN")) for r in recs)
        total = len(recs)
        under_trial = by_status.get("UNDER_TRIAL", 0)
        active_pending = [
            int(r["pending_days"])
            for r in recs
            if r.get("status") in _ACTIVE_STATUSES
            and not r.get("minor_involved")
            and isinstance(r.get("pending_days"), int)
        ]
        longest = max(
            (
                (int(r["pending_days"]), str(r.get("id", "")))
                for r in recs
                if r.get("status") in _ACTIVE_STATUSES
                and not r.get("minor_involved")
                and isinstance(r.get("pending_days"), int)
            ),
            default=None,
        )
        cards.append(
            {
                "state": state,
                "district": district,
                "total": total,
                "under_trial": under_trial,
                "under_trial_pct": round(100 * under_trial / total) if total else 0,
                "convictions": by_status.get("CONVICTED", 0),
                "acquittals": by_status.get("ACQUITTED", 0) + by_status.get("QUASHED", 0),
                "median_pending_days": int(median(active_pending)) if active_pending else None,
                "longest_pending": {"id": longest[1], "days": longest[0]} if longest else None,
            }
        )
    # Worst-first, then CAP: jurisdictions is the only unbounded summary section, so an
    # uncapped list would eventually push summary.json past SUMMARY_MAX_BYTES and abort
    # the whole run. The cap keeps the highest-caseload ("shame table") districts.
    cards.sort(key=lambda c: (-int(c["total"]), str(c["state"]), str(c["district"])))
    return cards[:_MAX_JURISDICTIONS]


def _scale_block(data_dir: Path, run_date: str, new_count: int, total: int) -> dict[str, Any]:
    """The awareness scale: cumulative total + a persistent daily-INGESTION histogram.

    "Entered the record" is an INGESTION date (when we recorded a case), never the
    incident date — so it is non-identifying and works for minors too. The histogram
    persists in summary.json itself: read the prior file, add this run's newly-minted
    count to today's bucket (multiple same-day runs accumulate only genuine new ids,
    since a re-run mints 0 new), and keep the last ``_SCALE_DAYS`` days.
    """
    prior: dict[str, int] = {}
    existing = data_dir / "summary.json"
    if existing.exists():
        try:
            prior_daily = json.loads(existing.read_text(encoding="utf-8")).get("scale", {})
            prior = {str(d["date"]): int(d["count"]) for d in prior_daily.get("daily", [])}
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            prior = {}
    prior[run_date] = prior.get(run_date, 0) + int(new_count)

    window = _recent_days(run_date, _SCALE_DAYS)
    daily = [{"date": d, "count": prior.get(d, 0)} for d in window]
    this_week = sum(prior.get(d, 0) for d in _recent_days(run_date, 7))
    return {"cumulative_total": total, "this_week": this_week, "daily": daily}


def _recent_days(run_date: str, count: int) -> list[str]:
    """The last ``count`` calendar days ending at run_date, oldest first (YYYY-MM-DD)."""
    end = date.fromisoformat(run_date)
    return [(end.fromordinal(end.toordinal() - i)).isoformat() for i in range(count - 1, -1, -1)]


def _recent_months(run_date: str, count: int) -> list[str]:
    year, month = int(run_date[:4]), int(run_date[5:7])
    months: list[str] = []
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def write_shards(
    records: list[dict[str, Any]],
    data_dir: Path,
    *,
    run_date: str | None = None,
    reserve: list[dict[str, Any]] | None = None,
) -> WriteResult:
    """Write the full ``data/`` tree from ``records`` atomically and idempotently.

    ``reserve`` records are not written but their ids/serials are reserved so a minted
    serial cannot collide with one — pass the held (needs-review) records so their
    off-shard ids are never re-minted for a distinct new case.
    """
    run_date = run_date or date.today().isoformat()
    finalized, new, updated = _assign_ids(records, data_dir, run_date, reserve=reserve)

    # --- All gates run BEFORE any file is written. ---
    _assert_unique_ids(finalized)
    _validate_all(finalized)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in finalized:
        groups.setdefault((_year(record, run_date), str(record["state"])), []).append(record)

    files: list[tuple[Path, str]] = []
    manifest: list[dict[str, Any]] = []
    for (year, state), group in sorted(groups.items()):
        group.sort(key=_sort_key, reverse=True)
        for index, chunk in enumerate(_chunk_by_size(group)):
            name = f"{state}.json" if index == 0 else f"{state}-p{index + 1}.json"
            text = _dumps(chunk)
            files.append((data_dir / year / name, text))
            manifest.append(
                {
                    "path": f"{year}/{name}",
                    "year": year,
                    "state": state,
                    "records": len(chunk),
                    "bytes": len(text.encode("utf-8")),
                }
            )

    summary_text = _dumps(_build_summary(finalized, run_date, data_dir, new))
    summary_bytes = len(summary_text.encode("utf-8"))
    if summary_bytes > SUMMARY_MAX_BYTES:
        raise ValueError(f"summary.json is {summary_bytes} bytes (budget {SUMMARY_MAX_BYTES})")
    files.append((data_dir / "summary.json", summary_text))

    manifest.sort(key=lambda entry: entry["path"])
    index_doc = {"generated_at": f"{run_date}T00:00:00Z", "shards": manifest}
    files.append((data_dir / "index.json", _dumps(index_doc)))

    # --- Stage every file as .tmp, then rename all into place. ---
    staged: list[tuple[Path, Path]] = []
    for path, text in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        staged.append((tmp, path))
    for tmp, path in staged:
        tmp.replace(path)

    _clear_stale_shards(data_dir, {data_dir / entry["path"] for entry in manifest})

    return WriteResult(
        published=len(finalized),
        new=new,
        updated=updated,
        shards=[entry["path"] for entry in manifest],
        records=finalized,
    )
