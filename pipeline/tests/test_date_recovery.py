"""Tests for deterministic month recovery of year-only incident dates (§2 / #124)."""

from __future__ import annotations

from typing import Any

from pipeline.date_recovery import recover_incident_month


def _rec(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"incident_reported_date": "2026", "sources": [], "first_published": ""}
    base.update(kw)
    return base


def test_recovers_from_url_path_when_year_matches() -> None:
    rec = _rec(sources=[{"url": "https://x.in/news/2026/07/story"}], first_published="2026-09-01")
    assert recover_incident_month(rec) == ("2026-07", "source_url")


def test_url_path_with_wrong_year_is_ignored() -> None:
    # A 2018 date in the URL must NOT stamp a 2026 incident (year-match guard).
    rec = _rec(sources=[{"url": "https://x.in/2018/03/old"}], first_published="2026-07-19")
    assert recover_incident_month(rec) == ("2026-07", "first_published")


def test_url_path_month_out_of_range_not_matched() -> None:
    rec = _rec(sources=[{"url": "https://x.in/2026/13/bad"}], first_published="2026-05-01")
    assert recover_incident_month(rec) == ("2026-05", "first_published")


def test_falls_back_to_first_published_month() -> None:
    rec = _rec(
        sources=[{"url": "https://indianexpress.com/article/cities/delhi/slug"}],
        first_published="2026-07-15",
    )
    assert recover_incident_month(rec) == ("2026-07", "first_published")


def test_first_published_wrong_year_stays_year_only() -> None:
    # The 2018 case: recorded 2026-07, but a 2026 month would invent a wrong-year date.
    rec = _rec(
        incident_reported_date="2018",
        sources=[{"url": "https://indiankanoon.org/doc/141261189/"}],
        first_published="2026-07-19",
    )
    assert recover_incident_month(rec) is None


def test_already_month_precise_returns_none() -> None:
    assert recover_incident_month(_rec(incident_reported_date="2026-06")) is None


def test_already_day_precise_returns_none() -> None:
    assert recover_incident_month(_rec(incident_reported_date="2026-06-01")) is None


def test_empty_date_returns_none() -> None:
    assert recover_incident_month(_rec(incident_reported_date="")) is None


def test_nothing_resolves_returns_none() -> None:
    rec = _rec(sources=[{"url": "https://x.in/no-date-here"}], first_published="")
    assert recover_incident_month(rec) is None


def test_url_precedence_beats_first_published() -> None:
    rec = _rec(sources=[{"url": "https://x.in/2026/03/a"}], first_published="2026-11-01")
    assert recover_incident_month(rec) == ("2026-03", "source_url")


# --- Wayback precedence (step 2) — the injected, optional lookup -----------------------------


def test_wayback_used_when_url_fails_and_year_matches() -> None:
    rec = _rec(sources=[{"url": "https://x.in/slug"}], first_published="2026-09-01")

    def wb(url: str, year: str) -> str | None:
        return "2026-04"  # earliest same-year snapshot

    assert recover_incident_month(rec, wayback=wb) == ("2026-04", "wayback")


def test_wayback_wrong_year_is_ignored() -> None:
    rec = _rec(sources=[{"url": "https://x.in/slug"}], first_published="2026-09-01")

    def wb(url: str, year: str) -> str | None:
        return "2025-12"  # different year -> not accepted; falls through to first_published

    assert recover_incident_month(rec, wayback=wb) == ("2026-09", "first_published")


def test_wayback_none_falls_through() -> None:
    rec = _rec(sources=[{"url": "https://x.in/slug"}], first_published="")

    def wb(url: str, year: str) -> str | None:
        return None

    assert recover_incident_month(rec, wayback=wb) is None


def test_url_precedence_beats_wayback() -> None:
    rec = _rec(sources=[{"url": "https://x.in/2026/02/a"}])

    def wb(url: str, year: str) -> str | None:  # pragma: no cover - URL wins before this runs
        return "2026-08"

    assert recover_incident_month(rec, wayback=wb) == ("2026-02", "source_url")
