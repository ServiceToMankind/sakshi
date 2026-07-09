"""eCourts / NJDG source.

Official/structured sources come first (Phase 0.3). This module fetches
NJDG-style JSON payloads for configured court establishments via the shared
:class:`PoliteClient` and turns each public case entry into a
:class:`RawDocument` of already-public text. Because it is an official source, the
dedupe stage lets records from here beat media on conflict.

Live NJDG / eCourts services gate bulk access behind a per-session token (and, on
some portals, a CAPTCHA). Supply the resolved endpoint URLs — already including
any required session token — via ``endpoints`` (or the ``ECOURTS_ENDPOINTS``
comma-separated env var). The fetch machinery, politeness, and JSON parsing here
are complete and tested; only session/token acquisition is deployment-specific
and left to the operator so no credential handling is hard-coded.
"""

from __future__ import annotations

import json
import os
from datetime import date

from pipeline.sources.base import RawDocument
from pipeline.sources.http import HttpGetter

__all__ = ["EcourtsSource", "parse_ecourts_json", "render_case_text"]

# NJDG-style case fields rendered into public text. Victim identity is not among
# them and is never requested; extraction + sanitize enforce that regardless.
_PUBLIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("cnr", "CNR"),
    ("case_number", "Case"),
    ("court", "Court"),
    ("police_station", "Police station"),
    ("fir_number", "FIR"),
    ("district", "District"),
    ("state", "State"),
    ("sections", "Sections"),
    ("status", "Status"),
    ("next_hearing", "Next hearing"),
)


def _configured_endpoints() -> tuple[str, ...]:
    raw = os.environ.get("ECOURTS_ENDPOINTS", "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def render_case_text(case: dict[str, object]) -> str:
    """Render one NJDG case dict into a compact line of already-public text."""
    parts: list[str] = []
    for key, label in _PUBLIC_FIELDS:
        value = case.get(key)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        parts.append(f"{label}: {value}")
    return ". ".join(parts)


def parse_ecourts_json(payload: str, publisher: str, fetched_at: str) -> list[RawDocument]:
    """Parse an NJDG-style JSON payload into RawDocuments.

    Accepts either a top-level list of case objects or an object with a
    ``"cases"`` list. Malformed JSON yields an empty list rather than raising.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        cases = data.get("cases", [])
    elif isinstance(data, list):
        cases = data
    else:
        cases = []

    docs: list[RawDocument] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        text = render_case_text(case)
        url = str(case.get("url") or case.get("case_url") or "")
        if not text or not url:
            continue
        docs.append(RawDocument(url=url, publisher=publisher, fetched_at=fetched_at, text=text))
    return docs


class EcourtsSource:
    """A :class:`~pipeline.sources.base.Source` over configured NJDG endpoints."""

    def __init__(
        self,
        client: HttpGetter,
        endpoints: tuple[str, ...] | None = None,
        publisher: str = "eCourts",
        fetched_at: str | None = None,
    ) -> None:
        self._client = client
        self._endpoints = endpoints if endpoints is not None else _configured_endpoints()
        self._publisher = publisher
        self._fetched_at = fetched_at or date.today().isoformat()

    async def fetch(self) -> list[RawDocument]:
        docs: list[RawDocument] = []
        for endpoint in self._endpoints:
            response = await self._client.get(endpoint)
            if response is None or response.status_code != 200:
                continue
            docs.extend(parse_ecourts_json(response.text, self._publisher, self._fetched_at))
        return docs
