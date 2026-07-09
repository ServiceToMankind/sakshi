"""Tests for the polite async HTTP client (offline, via httpx.MockTransport)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pipeline.sources.http import PoliteClient


class _Sleeps:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        self.t += 1.0
        return self.t


def _client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: object) -> PoliteClient:
    transport = httpx.MockTransport(handler)
    inner = httpx.AsyncClient(transport=transport)
    return PoliteClient(inner, sleep=_Sleeps(), clock=_Clock(), **kwargs)  # type: ignore[arg-type]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_robots_allow_then_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text="hello")

    client = _client(handler)
    response = _run(client.get("https://example.invalid/page"))
    assert response is not None and response.status_code == 200
    _run(client.aclose())


def test_robots_disallow_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        return httpx.Response(200, text="should not reach")

    client = _client(handler)
    assert _run(client.get("https://example.invalid/blocked")) is None


def test_robots_missing_defaults_to_allow() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="ok")

    client = _client(handler)
    response = _run(client.get("https://example.invalid/page"))
    assert response is not None and response.status_code == 200


def test_rate_limit_sleeps_between_same_host_requests() -> None:
    sleeps = _Sleeps()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text="ok")

    inner = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = PoliteClient(inner, sleep=sleeps, clock=_Clock())

    async def go() -> None:
        await client.get("https://example.invalid/a")
        await client.get("https://example.invalid/b")

    _run(go())
    assert sleeps.calls  # the second same-host request was throttled


def test_conditional_headers_stored_and_sent() -> None:
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        seen_headers.append(request.headers.get("If-None-Match"))
        return httpx.Response(200, headers={"ETag": '"abc"'}, text="ok")

    client = _client(handler)

    async def go() -> None:
        await client.get("https://example.invalid/page")  # stores ETag
        await client.get("https://example.invalid/page")  # sends If-None-Match

    _run(go())
    assert seen_headers == [None, '"abc"']


def test_retry_on_429_then_success() -> None:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, text="ok")

    sleeps = _Sleeps()
    inner = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = PoliteClient(inner, sleep=sleeps, clock=_Clock())
    response = _run(client.get("https://example.invalid/page"))
    assert response is not None and response.status_code == 200
    assert 2.0 in sleeps.calls  # honored Retry-After


def test_retry_exhausted_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(503)

    client = _client(handler, max_retries=2)
    with pytest.raises(httpx.HTTPStatusError):
        _run(client.get("https://example.invalid/page"))


def test_no_robots_check_when_disabled_and_context_manager() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    async def go() -> int:
        async with PoliteClient(
            httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            sleep=_Sleeps(),
            clock=_Clock(),
            respect_robots=False,
        ) as client:
            response = await client.get("https://example.invalid/page")
            assert response is not None
            return response.status_code

    assert _run(go()) == 200


def test_robots_fetch_counts_toward_first_request_throttle() -> None:
    sleeps = _Sleeps()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text="ok")

    client = PoliteClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), sleep=sleeps, clock=_Clock()
    )
    _run(client.get("https://example.invalid/first"))
    assert sleeps.calls  # even the FIRST content request waited after the robots fetch


def test_backoff_honors_retry_after_http_date() -> None:
    future = httpx.Response(503, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"})
    assert PoliteClient._backoff_seconds(1, future) == 60.0  # capped at BACKOFF_MAX_S
    past = httpx.Response(503, headers={"Retry-After": "Wed, 21 Oct 2009 07:28:00 GMT"})
    assert PoliteClient._backoff_seconds(1, past) == 1.0  # elapsed -> exponential fallback
    malformed = httpx.Response(503, headers={"Retry-After": "soon-ish"})
    assert PoliteClient._backoff_seconds(1, malformed) == 1.0  # exponential fallback
