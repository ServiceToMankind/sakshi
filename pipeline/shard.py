"""Sharded output writer.

Regenerates the ``data/`` tree from the given records: assigns deterministic,
never-reused IDs, validates every record against ``schemas/case.schema.json``,
and writes per-year/state shards plus ``summary.json`` and ``index.json``. Writes
are atomic (temp -> rename) and the run is validated in full before anything is
renamed into place, so a re-run is always safe.

IDs are stable across runs: the currently-committed shards act as the canonical
store. A record already carrying a valid ID keeps it; otherwise a case that was
seen in a previous run reuses its old ID, and only genuinely new cases mint a new
serial. ``scripts/pii_guard`` runs as the final assertion after this stage.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pipeline import config
from pipeline.validate import iter_shard_files, load_schema, validate_record

__all__ = [
    "SHARD_SPLIT_BYTES",
    "SUMMARY_MAX_BYTES",
    "WriteResult",
    "stable_case_key",
    "write_shards",
]

SUMMARY_MAX_BYTES = config.SUMMARY_MAX_BYTES
SHARD_SPLIT_BYTES = config.SHARD_SPLIT_BYTES

_ID_RE = re.compile(r"^SKS-\d{4}-[A-Z]{2}-\d{6}$")
_ACTIVE_STATUSES = frozenset({"FIR_FILED", "CHARGESHEETED", "UNDER_TRIAL", "APPEAL_PENDING"})


@dataclass
class WriteResult:
    """Outcome of a shard write: counts and the shard paths written."""

    published: int = 0
    new: int = 0
    updated: int = 0
    shards: list[str] = field(default_factory=list)


def stable_case_key(record: dict[str, Any]) -> str:
    """A stable identity key for a case, used to keep IDs constant across runs."""
    cnr = record.get("cnr")
    if cnr:
        return f"cnr:{str(cnr).strip().upper()}"
    fir = record.get("fir_ref") or {}
    station = str(fir.get("station", "")).strip().lower()
    number = str(fir.get("number", "")).strip()
    if station and number:
        return f"fir:{station}|{number}"
    sections = ",".join(sorted(record.get("offence_sections") or []))
    return (
        f"anon:{record.get('state', '')}|{record.get('district', '')}"
        f"|{record.get('incident_reported_date', '')}|{sections}"
    )


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
    """Return (case_key -> id, (year,state) -> max serial, set of all ids) from disk."""
    key_to_id: dict[str, str] = {}
    max_serial: dict[tuple[str, str], int] = {}
    all_ids: set[str] = set()
    if not data_dir.exists():
        return key_to_id, max_serial, all_ids
    for shard in iter_shard_files(data_dir):
        try:
            records = json.loads(shard.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for record in records:
            record_id = record.get("id", "")
            if not _ID_RE.match(record_id):
                continue
            all_ids.add(record_id)
            key_to_id.setdefault(stable_case_key(record), record_id)
            year, state, serial = record_id[4:8], record_id[9:11], int(record_id[12:])
            slot = (year, state)
            max_serial[slot] = max(max_serial.get(slot, 0), serial)
    return key_to_id, max_serial, all_ids


def _assign_ids(
    records: list[dict[str, Any]], data_dir: Path, run_date: str
) -> tuple[list[dict[str, Any]], int, int]:
    """Assign IDs, last_verified, and pending_days. Returns (records, new, updated)."""
    key_to_id, max_serial, existing_ids = _read_existing(data_dir)
    run_day = date.fromisoformat(run_date)
    new = updated = 0
    finalized: list[dict[str, Any]] = []
    for record in records:
        record = dict(record)
        year, state = _year(record, run_date), str(record["state"])
        case_key = stable_case_key(record)
        current = record.get("id", "")
        if _ID_RE.match(current):
            record_id = current
        elif case_key in key_to_id:
            record_id = key_to_id[case_key]
        else:
            slot = (year, state)
            serial = max_serial.get(slot, 0) + 1
            max_serial[slot] = serial
            record_id = f"SKS-{year}-{state}-{serial:06d}"
        record["id"] = record_id
        key_to_id.setdefault(case_key, record_id)
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
    # Date descending -> invert by using a value that sorts reversed; caller reverses.
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


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _clear_stale_shards(data_dir: Path, keep: set[Path]) -> None:
    """Remove year-dir shard files no longer produced, keeping _review untouched."""
    for shard in iter_shard_files(data_dir):
        if shard not in keep:
            shard.unlink()


def _build_summary(records: list[dict[str, Any]], run_date: str) -> dict[str, Any]:
    status_counts = Counter(str(r.get("status", "UNKNOWN")) for r in records)
    state_counts = Counter(str(r.get("state", "")) for r in records)

    months = _recent_months(run_date, config.MONTHLY_TREND_MONTHS)
    month_counts: Counter[str] = Counter()
    for record in records:
        reported = str(record.get("incident_reported_date", ""))
        if len(reported) >= 7:
            month_counts[reported[:7]] += 1
    monthly_trend = [{"month": m, "count": month_counts.get(m, 0)} for m in months]

    pending = [
        {"id": r["id"], "district": r.get("district", ""), "pending_days": int(r["pending_days"])}
        for r in records
        if r.get("status") in _ACTIVE_STATUSES and "pending_days" in r
    ]
    pending.sort(key=lambda p: p["pending_days"], reverse=True)

    return {
        "generated_at": f"{run_date}T00:00:00Z",
        "total": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "state_counts": dict(sorted(state_counts.items())),
        "monthly_trend": monthly_trend,
        "top_longest_pending": pending[: config.TOP_PENDING_COUNT],
    }


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
    records: list[dict[str, Any]], data_dir: Path, *, run_date: str | None = None
) -> WriteResult:
    """Write the full ``data/`` tree from ``records`` atomically and idempotently."""
    run_date = run_date or date.today().isoformat()
    finalized, new, updated = _assign_ids(records, data_dir, run_date)
    _validate_all(finalized)

    # Group by (year, state).
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in finalized:
        groups.setdefault((_year(record, run_date), str(record["state"])), []).append(record)

    written: set[Path] = set()
    manifest: list[dict[str, Any]] = []
    for (year, state), group in sorted(groups.items()):
        group.sort(key=_sort_key, reverse=True)
        chunks = _chunk_by_size(group)
        for index, chunk in enumerate(chunks):
            name = f"{state}.json" if index == 0 else f"{state}-p{index + 1}.json"
            path = data_dir / year / name
            text = _dumps(chunk)
            _atomic_write(path, text)
            written.add(path)
            manifest.append(
                {
                    "path": f"{year}/{name}",
                    "year": year,
                    "state": state,
                    "records": len(chunk),
                    "bytes": len(text.encode("utf-8")),
                }
            )

    _clear_stale_shards(data_dir, written)

    summary = _build_summary(finalized, run_date)
    summary_text = _dumps(summary)
    if len(summary_text.encode("utf-8")) > SUMMARY_MAX_BYTES:
        raise ValueError(
            f"summary.json is {len(summary_text.encode('utf-8'))} bytes "
            f"(budget {SUMMARY_MAX_BYTES})"
        )
    _atomic_write(data_dir / "summary.json", summary_text)

    manifest.sort(key=lambda entry: entry["path"])
    index_doc = {"generated_at": f"{run_date}T00:00:00Z", "shards": manifest}
    _atomic_write(data_dir / "index.json", _dumps(index_doc))

    return WriteResult(
        published=len(finalized),
        new=new,
        updated=updated,
        shards=[entry["path"] for entry in manifest],
    )
