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
from tripplanner.tools.trip_guard import envelope
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


def test_origin_correction_restores_missing_selected_flight_legs() -> None:
    create_trip_plan.invoke(
        {
            "destination": "Goa",
            "departure_date": "2026-08-10",
            "return_date": "2026-08-12",
            "origin": "Delhi",
        }
    )
    update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "selected_flights": [{"airline": "IndiGo"}],
                    "day_wise_itinerary": [
                        {"day": 1, "stops": [{"name": "Goa Hotel", "kind": "hotel"}]},
                        {"day": 2, "stops": [{"name": "Goa Hotel", "kind": "hotel"}]},
                        {"day": 3, "stops": [{"name": "Goa Hotel", "kind": "hotel"}]},
                    ],
                }
            )
        }
    )

    result = update_trip_plan.invoke({"updates_json": json.dumps({"origin": "Bangalore"})})
    plan = json.loads(get_trip_plan.invoke({}))

    assert plan["origin"] == "Bangalore"
    assert _stops_on(plan, 1)[0]["name"] == "Flight: Bangalore to Goa"
    assert _stops_on(plan, 3)[-1]["name"] == "Flight: Goa to Bangalore"
    assert "Added missing trip legs" in result


def test_no_tool_result_ever_shows_the_traveller_a_number_for_the_trip() -> None:
    _round_trip()
    result = add_selection("attraction", {"name": "Patalpani Falls"})
    lowered = json.dumps(result.get("alerts", [])).lower()
    for token in ("score", "rating", "/100", "out of 10", "effort:"):
        assert token not in lowered


def _excursion_day() -> None:
    """Day 2 leaves Indore in the morning and drives back mid-afternoon."""
    update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 2,
                            "stops": [
                                {
                                    "name": "Drive Indore to Ujjain",
                                    "kind": "transport",
                                    "time": "09:00",
                                    "duration_min": 120,
                                    "booked": True,
                                },
                                {
                                    "name": "Mahakaleshwar Temple",
                                    "kind": "attraction",
                                    "time": "11:30",
                                    "duration_min": 120,
                                },
                                {
                                    "name": "Drive Ujjain to Indore",
                                    "kind": "transport",
                                    "time": "15:00",
                                    "duration_min": 120,
                                    "booked": True,
                                },
                            ],
                        }
                    ]
                }
            )
        }
    )


def _overlaps_a_drive(stops: list[dict]) -> list[str]:
    drives = [
        (
            trip_planner._parse_hhmm(str(stop.get("time") or "")),
            int(stop.get("duration_min") or 90),
            str(stop.get("name") or ""),
        )
        for stop in stops
        if str(stop.get("kind") or "") == "transport"
    ]
    clashes = []
    for stop in stops:
        if str(stop.get("kind") or "") == "transport":
            continue
        at = trip_planner._parse_hhmm(str(stop.get("time") or ""))
        if at is None:
            continue
        length = int(stop.get("duration_min") or 90)
        for start, minutes, name in drives:
            if start is not None and at < start + minutes and at + length > start:
                clashes.append(f"{stop.get('name')} overlaps {name}")
    return clashes


def test_a_stop_that_collides_with_a_drive_is_moved_off_it() -> None:
    """The reported failure, at the point it happened: a stop landed on Day 2
    carrying a time from another day, and that time was the moment the car
    pulled away from Ujjain."""
    stops = [
        {"name": "Hotel Sayaji", "kind": "hotel", "time": "08:00", "duration_min": 30},
        {
            "name": "Drive Indore to Ujjain",
            "kind": "transport",
            "time": "09:00",
            "duration_min": 120,
        },
        {
            "name": "Mahakaleshwar Temple",
            "kind": "attraction",
            "time": "11:30",
            "duration_min": 120,
        },
        {"name": "Kaanch Mandir", "kind": "attraction", "time": "15:00", "duration_min": 90},
        {
            "name": "Drive Ujjain to Indore",
            "kind": "transport",
            "time": "15:00",
            "duration_min": 120,
        },
    ]
    plan = {
        "origin": "Bangalore",
        "destination": "Indore",
        "day_wise_itinerary": [
            {"day": 1, "stops": []},
            {"day": 2, "stops": stops},
            {"day": 3, "stops": []},
        ],
    }
    settled = trip_planner._settle_around_legs(stops, 2, envelope(plan))
    trip_planner._retime_stops_in_order(settled)
    assert _overlaps_a_drive(settled) == []
    assert [stop["name"] for stop in settled].index("Kaanch Mandir") > [
        stop["name"] for stop in settled
    ].index("Drive Ujjain to Indore")


def test_a_relocated_stop_does_not_carry_its_old_clock_time() -> None:
    """A time earned on another day is what put the stop on top of the drive."""
    plan = {
        "origin": "Bangalore",
        "destination": "Indore",
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
                    {"name": "Hotel Sayaji", "kind": "hotel", "time": "13:00", "duration_min": 45},
                    {"name": "Kaanch Mandir", "kind": "attraction", "time": "15:00"},
                    {"name": "Rajwada Palace", "kind": "attraction", "time": "16:00"},
                    {"name": "Sarafa Bazaar", "kind": "attraction", "time": "18:00"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Hotel Sayaji", "kind": "hotel", "time": "08:00", "duration_min": 30},
                    {
                        "name": "Drive Ujjain to Indore",
                        "kind": "transport",
                        "time": "15:00",
                        "duration_min": 120,
                        "booked": True,
                    },
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
        ],
    }
    trip_planner._reflow_unbooked_attractions(plan)
    for day in (1, 2, 3):
        assert _overlaps_a_drive(_stops_on(plan, day)) == []


def test_a_place_is_never_scheduled_on_top_of_a_drive() -> None:
    _round_trip()
    _excursion_day()
    add_selection("attraction", {"name": "Kaanch Mandir"})
    plan = json.loads(get_trip_plan.invoke({}))
    assert _overlaps_a_drive(_stops_on(plan, 2)) == []


def test_displacing_an_earlier_choice_does_not_drop_it_onto_a_drive() -> None:
    _round_trip()
    _excursion_day()
    add_selection("attraction", {"name": "Kaanch Mandir"})
    add_selection("attraction", {"name": "Shree Bada Ganpati Mandir"})
    plan = json.loads(get_trip_plan.invoke({}))
    for day in (1, 2, 3):
        assert _overlaps_a_drive(_stops_on(plan, day)) == []


def test_a_place_the_user_chose_is_moved_not_deleted_when_the_day_fills() -> None:
    _round_trip()
    update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 2,
                            "stops": [
                                {"name": "Rajwada Palace", "kind": "attraction",
                                 "time": "09:00", "duration_min": 120},
                                {"name": "Lal Bagh Palace", "kind": "attraction",
                                 "time": "11:30", "duration_min": 120},
                                {"name": "Sarafa Bazaar", "kind": "attraction",
                                 "time": "14:00", "duration_min": 120},
                                {"name": "Kaanch Mandir", "kind": "attraction",
                                 "time": "16:30", "duration_min": 120},
                                {"name": "Shree Bada Ganpati Mandir", "kind": "attraction",
                                 "time": "19:00", "duration_min": 60},
                            ],
                        }
                    ]
                }
            )
        }
    )
    plan = json.loads(get_trip_plan.invoke({}))
    alerts = trip_planner._rebalance_day(plan, 1, "Shree Bada Ganpati Mandir", "attraction")

    assert alerts, "a day over its cap should say something"
    assert "removed" not in " ".join(alerts)
    assert "Shree Bada Ganpati Mandir" in _names(plan)
    assert "Kaanch Mandir" in _names(plan)
    assert len(_stops_on(plan, 2)) == 4


def test_resetting_keeps_the_brief_and_drops_the_plan() -> None:
    _round_trip()
    add_selection("attraction", {"name": "Rajwada Palace"})
    before = json.loads(get_trip_plan.invoke({}))
    after = trip_planner.reset_active_trip()

    assert after is not None
    assert after["destination"] == before["destination"]
    assert after["departure_date"] == before["departure_date"]
    assert after["return_date"] == before["return_date"]
    assert after["trip_id"] == before["trip_id"]
    assert after["day_wise_itinerary"] == []
    assert after["selected_activities"] == []
    assert after["selected_flights"] == []
    assert json.loads(get_trip_plan.invoke({}))["day_wise_itinerary"] == []
