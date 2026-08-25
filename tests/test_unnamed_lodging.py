"""A stay must name somewhere you can actually book.

Every string here was taken from a corpus trip the planner shipped, so the
examples are what the model really writes rather than what it might write.
"""

from __future__ import annotations

import pytest

from tripplanner.tools.trip_common import unnamed_lodging
from tripplanner.tools.trip_validation import (
    _hotel_selection_warnings,
    persistence_sanity_errors,
)

CITIES = {
    "kochi", "kuala lumpur", "penang", "colombo", "galle", "shimla", "rome",
    "florence", "cherrapunji", "shillong", "amritsar", "chikmagalur", "udaipur",
    "nubra valley", "pangong lake",
}


@pytest.mark.parametrize(
    "name",
    [
        "Hotel in Kochi",
        "Hotel Kuala Lumpur",
        "Accessible Hotel Kuala Lumpur",
        "Colombo Hotel",
        "Galle Hotel",
        "Hotel in Cherrapunji",
        "Hotel in Rome",
        "Accessible Hotel Rome",
        "Premium Hotel",
        "A comfortable hotel near Shimla",
        "Budget accommodation in Udaipur",
        "Hotel/Camp in Nubra Valley",
        "Camp/Hotel at Pangong Lake",
        "",
    ],
)
def test_a_stay_that_names_no_property_is_unnamed(name: str) -> None:
    assert unnamed_lodging(name, CITIES)


@pytest.mark.parametrize(
    "name",
    [
        "Hotel Olathang",
        "Taj Swarna, Amritsar",
        "Ramada by Wyndham Amritsar",
        "The Serai Chikmagalur",
        "One&Only Cape Town",
        "Coorg Wilderness Resort",
        "The Elgin, Darjeeling",
        "SeaShell Port Blair",
        "Fortune Select Grand Ridge",
        "Alleppey Houseboat",
        "Nubra Delight Camp And Resort",
        "Pangong Retreat Camp",
    ],
)
def test_a_named_property_is_left_alone(name: str) -> None:
    assert not unnamed_lodging(name, CITIES)


def test_the_gap_names_the_days_whose_stay_cannot_be_booked() -> None:
    plan = {
        "destination": "Kochi, Kerala",
        "selected_hotels": [{"name": "Brunton Boatyard"}],
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Brunton Boatyard", "kind": "hotel"}]},
            {"day": 2, "stops": [{"name": "Hotel in Kochi", "kind": "hotel"}]},
            {"day": 3, "stops": [{"name": "Kochi Hotel", "kind": "hotel"}]},
        ],
    }

    gaps = _hotel_selection_warnings(plan)

    assert any("Day(s) 2, 3" in gap and "no bookable property" in gap for gap in gaps)
    assert not any("Day(s) 1" in gap for gap in gaps)


def test_the_gap_catches_slash_separated_generic_ladakh_stays() -> None:
    plan = {
        "destination": "Leh Ladakh",
        "selected_hotels": [{"name": "The Grand Dragon Ladakh"}],
        "day_wise_itinerary": [
            {
                "day": 4,
                "stops": [{"name": "Hotel/Camp in Nubra Valley", "kind": "hotel"}],
            },
            {
                "day": 5,
                "stops": [{"name": "Camp/Hotel at Pangong Lake", "kind": "hotel"}],
            },
            {
                "day": 6,
                "stops": [{"name": "The Grand Dragon Ladakh", "kind": "hotel"}],
            },
        ],
    }

    gaps = _hotel_selection_warnings(plan)

    assert any("Day(s) 4, 5" in gap and "no bookable property" in gap for gap in gaps)
    assert not any("Day(s) 6" in gap for gap in gaps)


def test_an_unnamed_stay_cannot_cross_persistence_without_an_origin() -> None:
    plan = {
        "destination": "Mussoorie",
        "selected_hotels": [],
        "day_wise_itinerary": [
            {
                "day": day,
                "stops": [{"name": "Hotel in Mussoorie", "kind": "hotel"}],
            }
            for day in range(1, 5)
        ],
    }

    errors = persistence_sanity_errors(plan)

    assert any(
        "Day(s) 1, 2, 3, 4" in error and "no bookable property" in error
        for error in errors
    )


def test_a_named_stay_everywhere_raises_no_lodging_gap() -> None:
    plan = {
        "destination": "Amritsar",
        "selected_hotels": [{"name": "Taj Swarna, Amritsar"}],
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Taj Swarna, Amritsar", "kind": "hotel"}]},
            {"day": 2, "stops": [{"name": "Ramada by Wyndham Amritsar", "kind": "hotel"}]},
        ],
    }

    assert _hotel_selection_warnings(plan) == []


def test_tbd_still_reports_as_a_placeholder_not_as_unnamed() -> None:
    plan = {
        "destination": "Udaipur",
        "selected_hotels": [],
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}]},
        ],
    }

    gaps = _hotel_selection_warnings(plan)

    assert any("placeholders remain on Day(s) 1" in gap for gap in gaps)
    assert not any("no bookable property" in gap for gap in gaps)
