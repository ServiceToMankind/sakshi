"""Tests for the place and institution rule (issue #255) in pipeline.pii_constants.

Names are made up (TESTVILLE, Fakepur, Fakeland) except the short institution names the
rule itself lists, which are real by necessity.
"""

from __future__ import annotations

import pytest

from pipeline.pii_constants import matched_place_details, scrub_place_details

D = "TESTVILLE"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # A place used to name the case becomes the district.
        (
            "Five men jailed in Fakepur gang rape case",
            "Five men jailed in TESTVILLE gang rape case",
        ),
        (
            "Fakepur sexual exploitation case: man held",
            "TESTVILLE sexual exploitation case: man held",
        ),
        # A police-station area becomes the district.
        ("Fakepur police registered a case.", "TESTVILLE police registered a case."),
        # A neighbourhood-style name becomes the district.
        ("The attack happened in Fake Kunj park.", "The attack happened in TESTVILLE park."),
        ("Police searched Fakepur Nagar.", "Police searched TESTVILLE."),
        # "near" a named landmark.
        ("The men were seen near Fakeland Fort.", "The men were seen in TESTVILLE."),
        # Short institution names: with an article on their own, without one before a noun.
        ("JNU dismissed the accused.", "A university dismissed the accused."),
        ("Ten JNU students complained.", "Ten university students complained."),
        # Named institutions, including an "of ..." tail.
        ("Protests at Fakeland University grew.", "Protests at a university grew."),
        ("Staff of Fakeland Institute of Fake Studies spoke.", "Staff of an institute spoke."),
        ("Fakeland Medical College students marched.", "College students marched."),
    ],
)
def test_names_are_replaced(text: str, expected: str) -> None:
    assert scrub_place_details(text, D) == expected
    assert scrub_place_details(expected, D) == expected  # running it again changes nothing


@pytest.mark.parametrize(
    "text",
    [
        "No police or court actions are reported.",  # an everyday word, not a place
        "The Delhi High Court granted bail.",  # courts are fine
        "Delhi Police arrested two men in Hyderabad.",  # states and big cities are fine
        "Police in Gautam Buddh Nagar filed a charge sheet.",  # a district ending in "Nagar"
        "TESTVILLE police registered a TESTVILLE rape case.",  # the record's own district
        "The University said it would cooperate.",  # no name, nothing to remove
        "Police searched the Market.",  # a lone word is not a named locality
        "Arrest near Hyderabad station.",  # near a big city
    ],
)
def test_allowed_text_is_left_alone(text: str) -> None:
    assert scrub_place_details(text, D) == text
    assert matched_place_details(text, D) == []


def test_without_a_district_places_are_left_for_the_guard_to_report() -> None:
    """With no district to put in, we can't replace a place, so the text stays as it is."""
    text = "Fakepur police registered a case near Fakeland Fort in Fake Kunj."
    assert scrub_place_details(text, "") == text


def test_matched_names_are_reported() -> None:
    found = matched_place_details("Fakepur police and Fakeland University staff.", D)
    assert found == ["Fakeland University", "Fakepur"]
