"""Place facts, and the contract that keeps them readable.

The bug this module exists to prevent was not a parsing mistake: the cache wrote
one key and the guard read another, so a fact we had already paid for could not
be checked. The contract test below is therefore the important one — it fails
the moment the two halves disagree again.
"""

from __future__ import annotations

import pytest

from tripplanner import place_facts
from tripplanner.web import places_cache

# A Text Search response shaped exactly like the one the cache normalizes.
GOOGLE_PLACE = {
    "id": "abc123",
    "displayName": {"text": "Louvre Museum"},
    "formattedAddress": "Rue de Rivoli, Paris",
    "location": {"latitude": 48.8606, "longitude": 2.3376},
    "businessStatus": "OPERATIONAL",
    "currentOpeningHours": {"openNow": True},
    "regularOpeningHours": {
        "weekdayDescriptions": [
            "Monday: 9:00\u202fAM\u2009\u2013\u20096:00\u202fPM",
            "Tuesday: Closed",
            "Wednesday: 9:00\u202fAM\u2009\u2013\u20099:45\u202fPM",
            "Thursday: 9:00\u202fAM\u2009\u2013\u20096:00\u202fPM",
            "Friday: 9:00\u202fAM\u2009\u2013\u20099:45\u202fPM",
            "Saturday: 9:00\u202fAM\u2009\u2013\u20096:00\u202fPM",
            "Sunday: 9:00\u202fAM\u2009\u2013\u20096:00\u202fPM",
        ]
    },
}

# 2026-08-11 is a Tuesday; 2026-08-12 is the Wednesday after it.
TUESDAY = "2026-08-11"
WEDNESDAY = "2026-08-12"


@pytest.fixture
def louvre() -> place_facts.PlaceFacts:
    return place_facts.facts_from_summary(places_cache.normalize_place(GOOGLE_PLACE))


def test_the_cache_emits_every_key_the_fact_reader_needs() -> None:
    summary = places_cache.normalize_place(GOOGLE_PLACE)
    assert place_facts.REQUIRED_SUMMARY_KEYS <= set(summary)


def test_a_closed_weekday_is_known_to_be_closed(louvre: place_facts.PlaceFacts) -> None:
    assert louvre.closed_on(TUESDAY) is True
    assert louvre.closed_on(WEDNESDAY) is False


def test_an_unfetched_place_says_unknown_rather_than_closed() -> None:
    facts = place_facts.facts_from_summary({})
    assert facts.closed_on(TUESDAY) is False
    assert facts.hours_on(TUESDAY) is None
    assert facts.fits(TUESDAY, 600, 700) is None


def test_a_visit_is_measured_against_that_weekday_alone(
    louvre: place_facts.PlaceFacts,
) -> None:
    assert louvre.fits(WEDNESDAY, 19 * 60, 21 * 60) is True
    # The same evening on Thursday runs past a 6pm close.
    assert louvre.fits("2026-08-13", 19 * 60, 21 * 60) is False


def test_a_closed_day_never_fits(louvre: place_facts.PlaceFacts) -> None:
    assert louvre.fits(TUESDAY, 10 * 60, 11 * 60) is False


def test_a_split_schedule_keeps_both_windows() -> None:
    facts = place_facts.facts_from_summary(
        {"weekday_descriptions": ["Monday: 9:00 AM \u2013 12:00 PM, 1:00 \u2013 6:00 PM"]}
    )
    assert facts.hours_on("2026-08-10") == ((540, 720), (780, 1080))
    assert facts.fits("2026-08-10", 12 * 60 + 30, 13 * 60) is False
    assert facts.fits("2026-08-10", 14 * 60, 15 * 60) is True


def test_open_all_day_and_past_midnight_are_both_read() -> None:
    facts = place_facts.facts_from_summary(
        {
            "weekday_descriptions": [
                "Monday: Open 24 hours",
                "Tuesday: 6:00 PM \u2013 2:00 AM",
            ]
        }
    )
    assert facts.fits("2026-08-10", 0, 1440) is True
    assert facts.hours_on(TUESDAY) == ((1080, 1560),)


def test_wording_we_cannot_read_stays_unknown() -> None:
    facts = place_facts.facts_from_summary(
        {"weekday_descriptions": ["Monday: hours vary, call ahead"]}
    )
    assert facts.hours_on("2026-08-10") is None


def test_a_shut_place_is_unavailable_whatever_its_hours_say() -> None:
    assert place_facts.facts_from_summary(
        {"business_status": "CLOSED_PERMANENTLY"}
    ).unavailable
    assert not place_facts.facts_from_summary({"business_status": "OPERATIONAL"}).unavailable
    assert not place_facts.facts_from_summary({}).unavailable
