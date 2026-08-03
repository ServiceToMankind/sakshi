"""Tests for Wayback snapshot lookup (pipeline.archive) — read-only, never captures."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from pipeline import archive

_HIT = (
    '{"archived_snapshots": {"closest": {"available": true, '
    '"url": "https://web.archive.org/web/2026/https://ex.invalid/a"}}}'
)
_MISS = '{"archived_snapshots": {}}'


class _Resp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    async def get(self, url: str) -> Any:
        self.calls.append(url)
        return self.mapping.get(url)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _avail(url: str) -> str:
    from urllib.parse import quote

    return f"{archive.AVAILABILITY_ENDPOINT}?url={quote(url, safe='')}"


def test_snapshot_found_returns_wayback_url() -> None:
    client = _FakeClient({_avail("https://ex.invalid/a"): _Resp(200, _HIT)})
    got = _run(archive.wayback_snapshot_url(client, "https://ex.invalid/a"))
    assert got == "https://web.archive.org/web/2026/https://ex.invalid/a"


def test_no_snapshot_returns_none() -> None:
    client = _FakeClient({_avail("https://ex.invalid/b"): _Resp(200, _MISS)})
    assert _run(archive.wayback_snapshot_url(client, "https://ex.invalid/b")) is None


def test_error_and_non_200_return_none() -> None:
    client = _FakeClient({_avail("https://ex.invalid/c"): _Resp(503, "")})
    assert _run(archive.wayback_snapshot_url(client, "https://ex.invalid/c")) is None
    # a missing mapping -> get returns None -> None (never raises)
    assert _run(archive.wayback_snapshot_url(_FakeClient({}), "https://ex.invalid/d")) is None
    assert _run(archive.wayback_snapshot_url(_FakeClient({}), "")) is None


def test_annotate_sets_archive_url_and_skips_flagged_sources() -> None:
    records: list[dict[str, Any]] = [
        {
            "sources": [
                {"url": "https://ex.invalid/a"},  # clean -> annotated
                {"url": "https://ex.invalid/x", "url_carries_identifying_slug": True},  # skipped
            ]
        }
    ]
    client = _FakeClient(
        {
            _avail("https://ex.invalid/a"): _Resp(200, _HIT),
            _avail("https://ex.invalid/x"): _Resp(200, _HIT),  # would hit, but must be skipped
        }
    )
    considered, found = _run(archive.annotate_archive_urls(records, client))
    assert considered == 1 and found == 1  # only the clean source was considered
    assert records[0]["sources"][0]["archive_url"].startswith("https://web.archive.org/")
    assert "archive_url" not in records[0]["sources"][1]  # §5-flagged source untouched
    # the flagged URL was NEVER even queried
    assert _avail("https://ex.invalid/x") not in client.calls


def test_module_cannot_trigger_a_capture() -> None:
    # Structural guard: the module never references the Save Page Now endpoint.
    assert "/save/" not in inspect.getsource(archive)
    assert "web.archive.org/save" not in inspect.getsource(archive)
