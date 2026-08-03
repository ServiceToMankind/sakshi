"""Citation permanence via EXISTING Internet Archive (Wayback) snapshots.

A source URL can rot or roll off a feed. Where the Wayback Machine already has a snapshot,
recording its ``archive_url`` gives the citation a durable second address. This module ONLY
LOOKS UP existing snapshots (the read-only availability API); it NEVER triggers a capture —
causing a permanent third-party copy of a page is an operator decision, not a side effect.

Guardrail (§5): a snapshot is recorded ONLY for a source whose URL does NOT carry the
identifying-slug flag. A flagged URL's slug states a withheld detail (a victim age, gender,
relationship, or institution); pinning a permanent third-party copy of THAT is a
re-identification vector, so flagged sources are skipped outright. Public-URL metadata only —
no case content, no PII.
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.parse import quote

__all__ = ["AVAILABILITY_ENDPOINT", "AsyncGetter", "annotate_archive_urls", "wayback_snapshot_url"]

# Read-only availability API. This module deliberately references NO capture endpoint
# (Save Page Now) anywhere — it is structurally incapable of triggering a snapshot.
AVAILABILITY_ENDPOINT = "https://archive.org/wayback/available"


class AsyncGetter(Protocol):
    """The async GET surface this module needs (satisfied by PoliteClient)."""

    async def get(self, url: str) -> Any: ...


def _parse_snapshot(body: str) -> str | None:
    """Extract the closest available snapshot URL from an availability API response."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None
    snapshot = (((data or {}).get("archived_snapshots") or {}).get("closest")) or {}
    if snapshot.get("available") is True:
        url = snapshot.get("url")
        return str(url) if isinstance(url, str) and url else None
    return None


async def wayback_snapshot_url(client: AsyncGetter, url: str) -> str | None:
    """Return an EXISTING Wayback snapshot URL for ``url``, or None if none exists / on error.

    Queries the availability API only. Never triggers a capture; never raises — a lookup
    failure just means "no snapshot recorded", so it can never break a run.
    """
    if not url:
        return None
    query = f"{AVAILABILITY_ENDPOINT}?url={quote(url, safe='')}"
    try:
        response = await client.get(query)
    except Exception:
        return None
    if response is None or getattr(response, "status_code", None) != 200:
        return None
    return _parse_snapshot(response.text)


async def annotate_archive_urls(
    records: list[dict[str, Any]], client: AsyncGetter
) -> tuple[int, int]:
    """Set ``archive_url`` on each NON-flagged source that has an existing snapshot.

    Skips any source with ``url_carries_identifying_slug`` (§5). Mutates ``records`` in place.
    Returns ``(sources_considered, snapshots_found)`` for a coverage report. Never triggers a
    capture.
    """
    considered = found = 0
    for record in records:
        for source in record.get("sources") or []:
            if source.get("url_carries_identifying_slug"):
                continue  # §5: never pin a permanent copy of an identifying URL
            considered += 1
            snapshot = await wayback_snapshot_url(client, str(source.get("url", "")))
            if snapshot:
                source["archive_url"] = snapshot
                found += 1
    return considered, found
