"""Deterministic MONTH recovery for year-only incident dates (§2 / issue #124).

§2 narrowed a minor's incident date to the MONTH (``YYYY-MM``). Records ingested before
that landed retain a bare YEAR, because the month was dropped at projection time, not
stored — so it cannot simply be re-projected. This module recovers the month
DETERMINISTICALLY (never invented) from evidence already attached to the record, in a
fixed precedence:

  1. a ``/YYYY/MM/`` date in a source URL path (the outlet's own dating of the report),
  2. the Wayback first-seen snapshot month (an OPTIONAL injected lookup — the pipeline runs
     offline, so it is normally absent; the hook keeps the precedence real + testable),
  3. the record's ``first_published`` month (when the project first recorded the case).

Each candidate is accepted ONLY when its YEAR equals the incident year: borrowing a
different year's month would INVENT a date in the wrong context (e.g. stamping a 2018 case
with the 2026 month we happened to ingest it). If nothing resolves, the date stays
year-only. The evidence that supplied the month is recorded in ``incident_date_provenance``
so a derived date is always transparent, never silently precise.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

__all__ = ["WaybackLookup", "recover_incident_month"]

# A bare year, e.g. "2026" — the only shape this recovers (a month/day date is left alone).
_BARE_YEAR_RE = re.compile(r"\d{4}")
# A /YYYY/MM/ or /YYYY-MM/ date embedded in a URL path; MM bounded to 01-12, and a trailing
# separator required so a bare /YYYY/ or a 4-digit id is not misread as a month.
_URL_MONTH_RE = re.compile(r"/(\d{4})[/-](0[1-9]|1[0-2])(?=[/-])")
# A leading YYYY-MM in an ISO date/datetime (first_published, or a Wayback YYYY-MM result).
_LEADING_YM_RE = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")

# (url, year) -> "YYYY-MM" for the earliest same-year snapshot, or None. Injected so the
# network call lives with the caller; recovery itself stays pure + deterministic.
WaybackLookup = Callable[[str, str], str | None]


def recover_incident_month(
    record: dict[str, Any], *, wayback: WaybackLookup | None = None
) -> tuple[str, str] | None:
    """Recover ``(YYYY-MM, provenance)`` for a year-only incident date, or ``None``.

    ``provenance`` is ``source_url`` / ``wayback`` / ``first_published`` — the evidence that
    supplied the month. Returns ``None`` when the date is already month/day-precise (or
    empty), or when no same-year evidence resolves (the date then stays year-only). Pure and
    deterministic; ``month`` precision only — a day is never recovered, a month never invented.
    """
    reported = str(record.get("incident_reported_date", "")).strip()
    if _BARE_YEAR_RE.fullmatch(reported) is None:
        return None  # already has month/day precision (or is empty) — nothing to recover
    year = reported
    sources = record.get("sources") or []

    # 1. A date in a source URL path — the outlet's own dating of the report.
    for source in sources:
        match = _URL_MONTH_RE.search(str(source.get("url", "")))
        if match is not None and match.group(1) == year:
            return f"{year}-{match.group(2)}", "source_url"

    # 2. Wayback first-seen month (optional; absent in the offline pipeline).
    if wayback is not None:
        for source in sources:
            month = wayback(str(source.get("url", "")), year)
            if month is not None:
                ym = _LEADING_YM_RE.fullmatch(month)
                if ym is not None and ym.group(1) == year:
                    return f"{year}-{ym.group(2)}", "wayback"

    # 3. first_published month — the coarsest evidence (when we first recorded the case).
    fp = _LEADING_YM_RE.match(str(record.get("first_published", "")))
    if fp is not None and fp.group(1) == year:
        return f"{year}-{fp.group(2)}", "first_published"

    return None  # unresolved -> stays year-only (a month is never invented)
