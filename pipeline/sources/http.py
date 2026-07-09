"""Polite async HTTP client shared by every network source.

Enforces the Phase 0.3 conduct rules in one place so no source can forget them:

- Honest ``User-Agent`` naming the project and repo (from ``config.user_agent``).
- ``robots.txt`` honored per host (fetched once, cached).
- At most one request every ``MIN_REQUEST_INTERVAL_S`` seconds per host.
- Conditional requests (``ETag`` / ``Last-Modified``) so unchanged pages are cheap.
- Exponential backoff on 429 / 5xx, respecting ``Retry-After``.

The httpx client, the sleep function, and the clock are all injectable so the
whole thing is exercised in tests with ``httpx.MockTransport`` and no real waits.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from pipeline import config

SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]


class HttpGetter(Protocol):
    """The async GET surface sources depend on (satisfied by :class:`PoliteClient`)."""

    async def get(self, url: str) -> httpx.Response | None: ...


def _retry_after_date_seconds(value: str) -> float | None:
    """Seconds until the HTTP-date form of Retry-After, or None if unparseable."""
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = (when - datetime.now(UTC)).total_seconds()
    return max(delta, 0.0)


@dataclass
class _Validators:
    """Cached conditional-request validators for one URL."""

    etag: str | None = None
    last_modified: str | None = None


class PoliteClient:
    """A rate-limited, robots-respecting async HTTP GET client."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        user_agent: str | None = None,
        sleep: SleepFn = asyncio.sleep,
        clock: ClockFn = time.monotonic,
        respect_robots: bool = True,
        min_interval: float = config.MIN_REQUEST_INTERVAL_S,
        max_retries: int = config.MAX_RETRIES,
    ) -> None:
        self._user_agent = user_agent or config.user_agent()
        self._client = client or httpx.AsyncClient(
            timeout=config.REQUEST_TIMEOUT_S,
            headers={"User-Agent": self._user_agent},
            follow_redirects=True,
        )
        self._owns_client = client is None
        self._sleep = sleep
        self._clock = clock
        self._respect_robots = respect_robots
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._validators: dict[str, _Validators] = {}

    async def __aenter__(self) -> PoliteClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _host(url: str) -> str:
        return urlsplit(url).netloc

    async def get(self, url: str) -> httpx.Response | None:
        """GET ``url`` politely. Returns None if robots.txt disallows it.

        Raises ``httpx.HTTPStatusError`` if retries are exhausted on 429/5xx.
        A 304 Not Modified response is returned as-is for the caller to skip.
        """
        if not await self._allowed(url):
            return None

        host = self._host(url)
        headers = self._conditional_headers(url)
        attempt = 0
        while True:
            await self._throttle(host)
            response = await self._client.get(url, headers=headers)
            if response.status_code == 429 or 500 <= response.status_code < 600:
                attempt += 1
                if attempt > self._max_retries:
                    response.raise_for_status()
                await self._sleep(self._backoff_seconds(attempt, response))
                continue
            self._store_validators(url, response)
            return response

    async def _allowed(self, url: str) -> bool:
        if not self._respect_robots:
            return True
        host = self._host(url)
        if host not in self._robots:
            self._robots[host] = await self._load_robots(url)
        parser = self._robots[host]
        if parser is None:
            return True  # robots.txt unavailable -> default allow
        return parser.can_fetch(self._user_agent, url)

    async def _load_robots(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            response = await self._client.get(robots_url)
        except httpx.HTTPError:
            self._last_request[parts.netloc] = self._clock()
            return None
        # The robots fetch is itself a request to the host — record it so the first
        # content request still honors the >=2s inter-request interval.
        self._last_request[parts.netloc] = self._clock()
        if response.status_code != 200:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser

    def _conditional_headers(self, url: str) -> dict[str, str]:
        entry = self._validators.get(url)
        if entry is None:
            return {}
        headers: dict[str, str] = {}
        if entry.etag:
            headers["If-None-Match"] = entry.etag
        if entry.last_modified:
            headers["If-Modified-Since"] = entry.last_modified
        return headers

    async def _throttle(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            wait = self._min_interval - (self._clock() - last)
            if wait > 0:
                await self._sleep(wait)
        self._last_request[host] = self._clock()

    @staticmethod
    def _backoff_seconds(attempt: int, response: httpx.Response) -> float:
        retry_after = response.headers.get("Retry-After", "").strip()
        if retry_after.isdigit():
            return min(float(retry_after), config.BACKOFF_MAX_S)
        if retry_after:
            seconds = _retry_after_date_seconds(retry_after)
            if seconds is not None:
                return min(seconds, config.BACKOFF_MAX_S)
        return min(config.BACKOFF_BASE_S * 2.0 ** (attempt - 1), config.BACKOFF_MAX_S)

    def _store_validators(self, url: str, response: httpx.Response) -> None:
        if response.status_code == 304:
            return
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if etag or last_modified:
            self._validators[url] = _Validators(etag=etag, last_modified=last_modified)
