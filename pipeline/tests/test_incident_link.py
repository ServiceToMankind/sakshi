"""Tests for spotting adult records that may belong to a child's incident (issue #255).

All names and links are made up (TESTVILLE, "fakepurkunj").
"""

from __future__ import annotations

from typing import Any

from pipeline.incident_link import possible_child_cases


def _record(minor: bool, url: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "minor_involved": minor,
        "state": "TG",
        "district": "TESTVILLE",
        "incident_reported_date": "2026-09" if minor else "2026-09-20",
        "sources": [{"url": url}],
    }
    base.update(overrides)
    return base


CHILD = _record(True, "https://example.invalid/news/minor-assaulted-near-fakepurkunj-park-1")


def test_an_adult_record_sharing_a_rare_link_word_with_a_childs_case_is_flagged() -> None:
    adult = _record(False, "https://example.invalid/news/men-held-in-fakepurkunj-gangrape-2")
    assert possible_child_cases([CHILD, adult]) == {1}


def test_children_themselves_are_never_flagged() -> None:
    other_child = _record(True, "https://example.invalid/news/fakepurkunj-case-update-3")
    assert possible_child_cases([CHILD, other_child]) == set()


def test_no_link_across_states_or_far_apart_in_time() -> None:
    elsewhere = _record(False, "https://example.invalid/fakepurkunj-case", state="DL")
    months_later = _record(
        False, "https://example.invalid/fakepurkunj-case", incident_reported_date="2026-12-30"
    )
    assert possible_child_cases([CHILD, elsewhere, months_later]) == set()


def test_everyday_words_short_words_and_district_names_do_not_link() -> None:
    everyday = _record(False, "https://example.invalid/news/minor-assaulted-near-park-police")
    short = _record(False, "https://example.invalid/news/cops-held-fake")
    content = _record(False, "https://example.invalid/news/morphed-video-content-viral")
    child_content = _record(True, "https://example.invalid/news/explicit-content-shared")
    child_with_district = _record(True, "https://example.invalid/testville-otherdistrict-case")
    other = _record(
        False, "https://example.invalid/otherdistrict-case", district="Otherdistrict Rural"
    )
    assert possible_child_cases([CHILD, everyday, short]) == set()
    assert possible_child_cases([child_content, content]) == set()  # "content" is everyday
    assert possible_child_cases([child_with_district, other]) == set()


def test_a_word_shared_by_many_records_is_too_common_to_link() -> None:
    adults = [_record(False, f"https://example.invalid/fakepurkunj-story-{n}") for n in range(13)]
    assert possible_child_cases([CHILD, *adults]) == set()


def test_missing_or_bad_dates_never_link() -> None:
    undated = _record(False, "https://example.invalid/fakepurkunj-a", incident_reported_date=None)
    year_only_child = _record(
        True, "https://example.invalid/fakepurkunj-b", incident_reported_date="2026"
    )
    bad = _record(
        False, "https://example.invalid/fakepurkunj-c", incident_reported_date="2026-13-45"
    )
    assert possible_child_cases([CHILD, undated, bad]) == set()
    assert (
        possible_child_cases([year_only_child, _record(False, "https://x.invalid/fakepurkunj")])
        == set()
    )
