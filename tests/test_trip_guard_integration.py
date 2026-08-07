"""The two defects the guard layer exists to close, tested end to end.

Both are silent failures rather than errors: a new place accepted onto a day the
traveller has already left, and a return flight deleted by an edit that never
mentioned flights. These tests drive the real tools against isolated storage.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tripplanner.tools import trip_planner, user_preferences
from tripplanner.tools.trip_planner import (
    add_selection,
    create_trip_plan,
    get_trip_plan,
    update_trip_plan,
)

_TEST_DIR = Path.home() / ".tripplanner_guard_test"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", _TEST_DIR)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", _TEST_DIR / "user_preferences.json")
    monkeypatch.setattr(trip_planner, "_TRIPS_DIR", _TEST_DIR)
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", _TEST_DIR / "active_trip.json")
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", _TEST_DIR / "trips")
    _TEST_DIR.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


def _round_trip() -> dict:
    create_trip_plan.invoke(
        {
            "destination": "Indore",
            "departure_date": "2026-08-10",
            "return_date": "2026-08-12",
            "origin": "Bangalore",
        }
    )
    update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 1,
                            "stops": [
                                {
                                    "name": "Flight Bangalore to Indore",
                                    "kind": "flight",
                                    "time": "09:00",
                                    "duration_min": 120,
                                },
                                {
                                    "name": "Hotel Sayaji",
                                    "kind": "hotel",
                                    "time": "13:00",
                                    "duration_min": 45,
                                },
                            ],
                        },
                        {
                            "day": 2,
                            "stops": [
                                {
                                    "name": "Rajwada Palace",
                                    "kind": "attraction",
                                    "time": "10:00",
                                    "duration_min": 90,
                                }
                            ],
                        },
                        {
                            "day": 3,
                            "stops": [
                                {
                                    "name": "Flight Indore to Bangalore",
                                    "kind": "flight",
                                    "time": "18:00",
                                    "duration_min": 120,
                                }
                            ],
                        },
                    ]
                }
            )
        }
    )
    return json.loads(get_trip_plan.invoke({}))


def _stops_on(plan: dict, day: int) -> list[dict]:
    for entry in plan["day_wise_itinerary"]:
        if entry.get("day") == day:
            return entry.get("stops", [])
    return []


def _names(plan: dict) -> list[str]:
    return [
        str(stop.get("name", ""))
        for entry in plan["day_wise_itinerary"]
        for stop in entry.get("stops", [])
    ]


def test_a_new_place_is_never_scheduled_after_the_flight_home() -> None:
    _round_trip()
    add_selection("attraction", {"name": "Patalpani Falls"})
    plan = json.loads(get_trip_plan.invoke({}))

    departure_day = _stops_on(plan, 3)
    names = [str(stop.get("name", "")) for stop in departure_day]
    if "Patalpani Falls" in names:
        assert names.index("Patalpani Falls") < names.index("Flight Indore to Bangalore")
    assert "Patalpani Falls" in _names(plan)


def test_changing_the_hotel_does_not_delete_the_return_flight() -> None:
    _round_trip()
    update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 3,
                            "stops": [
                                {
                                    "name": "Hotel Radisson Blu",
                                    "kind": "hotel",
                                    "time": "08:00",
                                    "duration_min": 45,
                                }
                            ],
                        }
                    ]
                }
            )
        }
    )
    plan = json.loads(get_trip_plan.invoke({}))
    assert "Flight Indore to Bangalore" in _names(plan)


def test_a_restored_leg_is_reported_rather_than_repaired_in_silence() -> None:
    _round_trip()
    result = update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 3,
                            "stops": [
                                {
                                    "name": "Hotel Radisson Blu",
                                    "kind": "hotel",
                                    "time": "08:00",
                                    "duration_min": 45,
                                }
                            ],
                        }
                    ]
                }
            )
        }
    )
    assert "Flight Indore to Bangalore" in result
    assert "selected_flights" in result


def test_an_update_that_declares_a_flight_change_is_allowed_to_change_it() -> None:
    _round_trip()
    update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "selected_flights": [
                        {"name": "Flight Indore to Bangalore 6E 456", "direction": "return"}
                    ],
                    "day_wise_itinerary": [
                        {
                            "day": 3,
                            "stops": [
                                {
                                    "name": "Flight Indore to Bangalore 6E 456",
                                    "kind": "flight",
                                    "time": "17:00",
                                    "duration_min": 120,
                                }
                            ],
                        }
                    ],
                }
            )
        }
    )
    names = _names(json.loads(get_trip_plan.invoke({})))
    assert "Flight Indore to Bangalore 6E 456" in names
    assert "Flight Indore to Bangalore" not in names


def test_no_tool_result_ever_shows_the_traveller_a_number_for_the_trip() -> None:
    _round_trip()
    result = add_selection("attraction", {"name": "Patalpani Falls"})
    lowered = json.dumps(result.get("alerts", [])).lower()
    for token in ("score", "rating", "/100", "out of 10", "effort:"):
        assert token not in lowered
