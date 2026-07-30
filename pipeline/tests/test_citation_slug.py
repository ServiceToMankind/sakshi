"""Tests for the citation-URL slug scanner (§5)."""

from __future__ import annotations

import pytest

from pipeline.citation_slug import url_carries_identifying_slug


@pytest.mark.parametrize(
    "url",
    [
        # age (numeric + spelled)
        "https://example.invalid/article/rape-of-3-year-old-in-city",
        "https://example.invalid/news/four-year-old-girl-assaulted",
        "https://example.invalid/toddler-minor-rape-case",
        # gender
        "https://example.invalid/minor-girl-sexually-assaulted",
        "https://example.invalid/welfare-home-abuse-of-boys",
        # accused-victim relationship
        "https://example.invalid/maternal-uncle-booked-for-assault",
        "https://example.invalid/teacher-held-in-school-rape",
        # institution
        "https://example.invalid/hostel-warden-arrested",
    ],
)
def test_identifying_slugs_are_flagged(url: str) -> None:
    assert url_carries_identifying_slug(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://indiankanoon.org/doc/138118999/",  # court doc — clean
        "https://example.invalid/high-court-cancels-bail-in-pocso-case",  # case/response words
        "https://example.invalid/constable-arrested-chargesheet-filed",
        "https://example.invalid/article/cab-driver-convicted",  # accused occupation, not victim
        "",  # empty
        "not a url",  # unparseable -> no path tokens match
    ],
)
def test_clean_slugs_are_not_flagged(url: str) -> None:
    assert url_carries_identifying_slug(url) is False


def test_query_and_host_are_ignored() -> None:
    """Only the PATH is scanned — a host or query string never triggers the flag."""
    assert url_carries_identifying_slug("https://girl.example.invalid/doc/123") is False
    assert url_carries_identifying_slug("https://example.invalid/doc/123?ref=girl") is False
