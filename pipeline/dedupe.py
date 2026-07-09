"""Case-anchored deduplication and merging.

Deduplication is CASE-ANCHORED, never identity-anchored: cases match on FIR
number, CNR, police station, district, date, and court — NEVER on victim
identity (which is never ingested).

Matching:
- Exact: same CNR, or same (police station, FIR number).
- Fuzzy: same district AND date within +-3 days AND overlapping offence sections
  AND similar court name (rapidfuzz). Two or more of those signals present is a
  confident merge; exactly one is AMBIGUOUS and routed to review, not merged.

Merge policy: court records beat media; the further-along status wins; offence
sections, status history, accused, and sources[] are unioned. Records below the
confidence threshold, and ambiguous fuzzy matches, are routed to ``data/_review/``
(excluded from the published site).
"""

from __future__ import annotations

import re
from datetime import date
from functools import reduce
from typing import Any

from rapidfuzz import fuzz

from pipeline import config

__all__ = [
    "dedupe",
    "exact_anchor_keys",
    "is_court_record",
    "is_same_case",
    "match_strength",
    "merge_records",
]

# Publishers we treat as official/authoritative (case-insensitive substring match).
OFFICIAL_PUBLISHERS: frozenset[str] = frozenset(
    {"ecourts", "njdg", "high court", "supreme court", "indian kanoon", "district court"}
)

# Progression order; a higher rank is "further along" and wins on conflict.
STATUS_RANK: dict[str, int] = {
    "UNKNOWN": 0,
    "FIR_FILED": 1,
    "CHARGESHEETED": 2,
    "UNDER_TRIAL": 3,
    "APPEAL_PENDING": 4,
    "CONVICTED": 5,
    "ACQUITTED": 5,
    "QUASHED": 5,
    "CLOSED": 5,
}

COURT_NAME_SIMILARITY = 85.0
FUZZY_DATE_WINDOW_DAYS = 3


def is_court_record(record: dict[str, Any]) -> bool:
    """True if any source publisher is an official/court publisher."""
    for source in record.get("sources", []):
        publisher = str(source.get("publisher", "")).lower()
        if any(official in publisher for official in OFFICIAL_PUBLISHERS):
            return True
    return False


def _fir_year(number: str, incident_date: Any) -> str:
    """Best-effort FIR year: the /YYYY suffix if present, else the incident year."""
    match = re.search(r"/(\d{4})\b", str(number))
    if match:
        return match.group(1)
    reported = str(incident_date or "")
    return reported[:4] if len(reported) >= 4 and reported[:4].isdigit() else ""


def exact_anchor_keys(record: dict[str, Any]) -> set[str]:
    """All exact case anchors (CNR and/or year-qualified FIR). Shared by dedupe + shard.

    The FIR key carries a year so a same-numbered FIR at the same station in a
    different year is a distinct case, not a false merge.
    """
    keys: set[str] = set()
    cnr = record.get("cnr")
    if cnr:
        keys.add(f"cnr:{str(cnr).strip().upper()}")
    fir = record.get("fir_ref") or {}
    station = str(fir.get("station", "")).strip().lower()
    number = str(fir.get("number", "")).strip()
    if station and number:
        keys.add(
            f"fir:{station}|{number}|{_fir_year(number, record.get('incident_reported_date'))}"
        )
    return keys


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _anchor_types(keys: set[str]) -> set[str]:
    return {key.split(":", 1)[0] for key in keys}


def match_strength(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Return 'exact', 'strong', 'weak', or 'none' for the a/b pairing."""
    keys_a, keys_b = exact_anchor_keys(a), exact_anchor_keys(b)
    if keys_a & keys_b:
        return "exact"
    # Only decide "distinct" when they share an anchor TYPE (cnr vs cnr, fir vs fir)
    # yet the values differ. If the anchor types are disjoint (one CNR-only, the
    # other FIR-only), fall through to the fuzzy signals so the same case can match.
    if _anchor_types(keys_a) & _anchor_types(keys_b):
        return "none"

    district_a = str(a.get("district", "")).strip().lower()
    district_b = str(b.get("district", "")).strip().lower()
    if not district_a or district_a != district_b:
        return "none"

    date_a, date_b = (
        _parse_date(a.get("incident_reported_date")),
        _parse_date(b.get("incident_reported_date")),
    )
    if date_a and date_b and abs((date_a - date_b).days) > FUZZY_DATE_WINDOW_DAYS:
        return "none"

    sections_a = set(a.get("offence_sections") or [])
    sections_b = set(b.get("offence_sections") or [])
    if sections_a and sections_b and not (sections_a & sections_b):
        return "none"

    court_a = str((a.get("court") or {}).get("name", "")).lower()
    court_b = str((b.get("court") or {}).get("name", "")).lower()
    if court_a and court_b and fuzz.ratio(court_a, court_b) < COURT_NAME_SIMILARITY:
        return "none"

    signals = 0
    if date_a and date_b:
        signals += 1
    if sections_a and sections_b and (sections_a & sections_b):
        signals += 1
    if court_a and court_b and fuzz.ratio(court_a, court_b) >= COURT_NAME_SIMILARITY:
        signals += 1

    if signals >= 2:
        return "strong"
    if signals == 1:
        return "weak"
    return "none"


def is_same_case(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True if a and b are confidently the same case (exact or strong match)."""
    return match_strength(a, b) in ("exact", "strong")


def _order(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Primary first: court beats media, then higher confidence, else a."""
    court_a, court_b = is_court_record(a), is_court_record(b)
    if court_a != court_b:
        return (a, b) if court_a else (b, a)
    if float(b.get("confidence", 0)) > float(a.get("confidence", 0)):
        return (b, a)
    return (a, b)


def _higher_status(status_a: str, status_b: str) -> str:
    return status_a if STATUS_RANK.get(status_a, 0) >= STATUS_RANK.get(status_b, 0) else status_b


def _union_sources(
    primary: dict[str, Any], secondary: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[int, int], dict[int, int]]:
    """Union sources[] by URL, returning the list and per-record index remaps."""
    sources: list[dict[str, Any]] = []
    by_url: dict[str, int] = {}

    def add(record: dict[str, Any]) -> dict[int, int]:
        remap: dict[int, int] = {}
        for old_index, source in enumerate(record.get("sources", [])):
            url = str(source.get("url", ""))
            if url not in by_url:
                by_url[url] = len(sources)
                sources.append(source)
            remap[old_index] = by_url[url]
        return remap

    return sources, add(primary), add(secondary)


def _union_status_history(
    primary: dict[str, Any],
    secondary: dict[str, Any],
    remap_p: dict[int, int],
    remap_s: dict[int, int],
) -> list[dict[str, Any]]:
    """Union status_history, remapping each entry's source index to the merged list."""
    history: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for record, remap in ((primary, remap_p), (secondary, remap_s)):
        for entry in record.get("status_history", []):
            old_source = int(entry.get("source", 0))
            if old_source not in remap:
                continue  # out-of-range source index: drop, never misattribute to sources[0]
            new_entry = {
                "status": entry["status"],
                "date": entry["date"],
                "source": remap[old_source],
            }
            key = (new_entry["status"], new_entry["date"], new_entry["source"])
            if key not in seen:
                seen.add(key)
                history.append(new_entry)
    return history


def _merge_accused(
    primary: list[dict[str, Any]], secondary: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Union accused by label, preferring a court-record name and the higher status."""
    merged: dict[str, dict[str, Any]] = {}
    for accused in [*primary, *secondary]:
        label = str(accused.get("label", ""))
        if label not in merged:
            merged[label] = dict(accused)
            continue
        current = merged[label]
        if accused.get("name_public_court_record") and not current.get("name_public_court_record"):
            current["name_public_court_record"] = accused["name_public_court_record"]
        current["status"] = _higher_status(
            str(current.get("status", "UNKNOWN")), str(accused.get("status", "UNKNOWN"))
        )
    return list(merged.values())


def merge_records(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge two same-case records per the merge policy."""
    primary, secondary = _order(a, b)
    sources, remap_p, remap_s = _union_sources(primary, secondary)

    merged: dict[str, Any] = dict(primary)
    merged["sources"] = sources
    merged["status"] = _higher_status(
        str(primary.get("status", "UNKNOWN")), str(secondary.get("status", "UNKNOWN"))
    )
    merged["confidence"] = max(
        float(primary.get("confidence", 0)), float(secondary.get("confidence", 0))
    )
    merged["minor_involved"] = bool(
        primary.get("minor_involved") or secondary.get("minor_involved")
    )

    sections = list(
        dict.fromkeys(
            (primary.get("offence_sections") or []) + (secondary.get("offence_sections") or [])
        )
    )
    if sections:
        merged["offence_sections"] = sections

    history = _union_status_history(primary, secondary, remap_p, remap_s)
    if history:
        merged["status_history"] = history

    accused = _merge_accused(primary.get("accused", []), secondary.get("accused", []))
    if accused:
        merged["accused"] = accused

    # Fill any anchor/detail the primary lacks from the secondary.
    for field in ("cnr", "fir_ref", "court", "incident_reported_date", "summary", "category"):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]

    return merged


def _review_entry(record: dict[str, Any], reason: str) -> dict[str, Any]:
    """Wrap a record for the review queue with the reason it was quarantined."""
    return {"reason": reason, "record": record}


def dedupe(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deduplicate ``records`` case-anchored.

    Returns ``(published, review)``. ``review`` holds low-confidence records and
    ambiguous fuzzy matches (each ``{"reason": ..., "record": ...}``) destined for
    ``data/_review/`` rather than the published site.
    """
    review: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for record in records:
        if float(record.get("confidence", 0)) < config.CONFIDENCE_REVIEW_THRESHOLD:
            review.append(_review_entry(record, "low_confidence"))
        else:
            kept.append(record)

    clusters: list[list[dict[str, Any]]] = []
    for record in kept:
        target: list[dict[str, Any]] | None = None
        ambiguous = False
        for cluster in clusters:
            strengths = [match_strength(record, member) for member in cluster]
            if any(s in ("exact", "strong") for s in strengths):
                target = cluster
                break
            if any(s == "weak" for s in strengths):
                ambiguous = True
        if target is not None:
            target.append(record)
        elif ambiguous:
            review.append(_review_entry(record, "ambiguous_match"))
        else:
            clusters.append([record])

    published = [reduce(merge_records, cluster) for cluster in clusters]
    return published, review
