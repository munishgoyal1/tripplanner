"""A fact given once about the whole trip must hold on every day of it."""

from __future__ import annotations

from tripplanner.tools import trip_facts


def _trip(**extra: object) -> dict[str, object]:
    return {
        "destination": "Rameshwaram",
        "day_wise_itinerary": [
            {
                "day": 1,
                "summary": "Hire a cab for the temple circuit.",
                "stops": [
                    {"name": "Taxi: Hotel to Dhanushkodi", "kind": "transport"},
                    {"name": "Dhanushkodi", "kind": "attraction", "note": "No taxi needed"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Pamban Bridge", "kind": "attraction",
                     "note": "Take an auto-rickshaw from the hotel"},
                ],
            },
        ],
        **extra,
    }


def test_the_own_car_fact_is_read_from_the_trip_itself() -> None:
    assert trip_facts.local_road_mode(_trip()) == ""
    assert trip_facts.local_road_mode(
        _trip(trip_constraints=["Local travel: our own car, no taxis"])
    ) == "own_car"
    assert trip_facts.local_road_mode(_trip(notes="We will be driving all the way")) == "own_car"
    snapshot = {"transport_preferences": {"preferred_road_transport": "own_car"}}
    assert trip_facts.local_road_mode(_trip(preferences_snapshot=snapshot)) == "own_car"
    # A hired car with a driver is not the traveller's own car.
    assert trip_facts.local_road_mode(_trip(notes="Private car with driver")) == ""


def test_every_stale_taxi_mention_is_listed_once_the_trip_is_by_own_car() -> None:
    conflicts = trip_facts.fact_conflicts(_trip(trip_constraints=["Own car"]))

    assert len(conflicts) == 1
    text = conflicts[0]
    assert "Day 1 summary still says 'cab'" in text
    assert "Taxi: Hotel to Dhanushkodi" in text
    assert "Pamban Bridge" in text
    assert "Dhanushkodi (note)" not in text  # "No taxi needed" agrees with the fact


def test_a_trip_without_the_fact_reports_nothing() -> None:
    assert trip_facts.fact_conflicts(_trip()) == []
