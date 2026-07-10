"""Tests for the Indian Kanoon court-record source (offline, via a fake poster)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from pipeline.sources.indiankanoon import (
    IndianKanoonSource,
    parse_search_response,
    render_doc_text,
)

_SEARCH_JSON = json.dumps(
    {
        "docs": [
            {
                "tid": 12345,
                "title": "State vs Accused",
                "docsource": "Delhi High Court",
                "publishdate": "2026-07-05",
                "headline": "conviction under BNS 64",
            },
            {"title": "no tid here"},  # skipped: no id
        ]
    }
)


class _FakePoster:
    def __init__(self, payload: str, status: int = 200) -> None:
        self._payload = payload
        self.status = status
        self.calls: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self.calls.append({"url": url, "data": data, "headers": headers})
        return httpx.Response(self.status, text=self._payload)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_render_doc_text_omits_empty_fields() -> None:
    text = render_doc_text({"title": "T", "docsource": "Delhi HC", "headline": ""})
    assert "Title: T" in text and "Court: Delhi HC" in text and "Excerpt" not in text


def test_parse_search_response_builds_doc_urls_and_skips_untitled() -> None:
    docs = parse_search_response(_SEARCH_JSON, "Indian Kanoon", "2026-07-10")
    assert len(docs) == 1  # the tid-less hit is dropped
    assert docs[0].url == "https://indiankanoon.org/doc/12345/"
    assert docs[0].publisher == "Indian Kanoon"
    assert "Delhi High Court" in docs[0].text


def test_parse_search_response_malformed_is_empty() -> None:
    assert parse_search_response("{bad", "Indian Kanoon", "2026-07-10") == []


def test_fetch_without_token_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INDIANKANOON_API_TOKEN", raising=False)
    poster = _FakePoster(_SEARCH_JSON)
    source = IndianKanoonSource(poster, queries=("rape doctypes:delhi",), fetched_at="2026-07-10")
    assert _run(source.fetch()) == []
    assert poster.calls == []  # never even calls the API without a token


def test_fetch_with_token_queries_and_parses() -> None:
    poster = _FakePoster(_SEARCH_JSON)
    source = IndianKanoonSource(
        poster,
        queries=("rape doctypes:delhi", "POCSO doctypes:telangana"),
        fetched_at="2026-07-10",
        token="secret-token",
    )
    docs = _run(source.fetch())
    assert len(docs) == 2  # one hit per query
    assert len(poster.calls) == 2
    assert poster.calls[0]["headers"]["Authorization"] == "Token secret-token"
    assert poster.calls[0]["data"]["formInput"] == "rape doctypes:delhi"


def test_fetch_skips_non_200() -> None:
    poster = _FakePoster(_SEARCH_JSON, status=503)
    source = IndianKanoonSource(
        poster, queries=("rape doctypes:delhi",), fetched_at="2026-07-10", token="t"
    )
    assert _run(source.fetch()) == []
