"""The two defects the guard layer exists to close, tested end to end.

Both are silent failures rather than errors: a new place accepted onto a day the
traveller has already left, and a return flight deleted by an edit that never
mentioned flights. These tests drive the real tools against isolated storage.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from tripplanner.tools import trip_planner, user_preferences
from tripplanner.tools.trip_guard import envelope, validate_plan
from tripplanner.tools.trip_planner import (
    add_selection,
    create_trip_plan,
    get_trip_plan,
    update_trip_plan,
)
from tripplanner.web import places_cache

# Parallel sandboxes run this suite at the same time against one home
# directory, so a shared name means one run's teardown deletes another
# run's fixture mid-test. The pid keeps them disjoint.
_TEST_DIR = Path.home() / f".tripplanner_guard_test-{os.getpid()}"


@pytest.fixture(autouse=True)
def _no_machine_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read no place facts, so the result cannot depend on a developer's cache.

    ``places_cache`` persists to the home directory, so these tests were quietly
    scored against whatever coordinates and opening hours this machine happened
    to have fetched before. The guard's degraded mode is the honest baseline
    here; facts get their own tests.
    """
    monkeypatch.setattr(places_cache, "get_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(places_cache, "get_details", lambda *args, **kwargs: None)


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
                    "selected_flights": [{"airline": "Test Air"}],
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
                                    "name": "Hotel Sayaji",
                                    "kind": "hotel",
                                    "time": "08:00",
                                    "duration_min": 45,
                                },
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
                                    "name": "Hotel Sayaji checkout",
                                    "kind": "hotel",
                                    "time": "08:00",
                                    "duration_min": 45,
                                },
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


def test_an_update_without_a_required_nightly_stay_is_saved_with_a_warning() -> None:
    create_trip_plan.invoke(
        {
            "destination": "Spiti Valley",
            "departure_date": "2027-06-01",
            "return_date": "2027-06-03",
            "travel_scope": "destination_only",
        }
    )
    before = json.loads(get_trip_plan.invoke({}))

    result = update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "selected_hotels": [
                        {"name": "Spiti Valley Lodge", "city": "Spiti Valley"}
                    ],
                    "day_wise_itinerary": [
                        {
                            "day": 1,
                            "stops": [
                                {"name": "Drive to Narkanda", "kind": "transport"},
                                {"name": "Hatu Peak", "kind": "attraction"},
                            ],
                        },
                        {
                            "day": 2,
                            "stops": [{"name": "Tabo Monastery", "kind": "attraction"}],
                        },
                        {
                            "day": 3,
                            "stops": [{"name": "Return drive", "kind": "transport"}],
                        },
                    ],
                }
            )
        }
    )

    # The turn's only copy of the itinerary is saved rather than discarded, so the
    # missing stay is reported as a warning instead of rejecting the update.
    assert json.loads(get_trip_plan.invoke({})) != before
    assert "Day 1 has no concrete lodging anchor for the night" in result


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
                                    "name": "Hotel Sayaji checkout",
                                    "kind": "hotel",
                                    "time": "08:00",
                                    "duration_min": 45,
                                },
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
                        {
                            "day": 1,
                            "stops": [
                                {"name": "Holiday Inn Resort Goa", "kind": "hotel"}
                            ],
                        },
                        {
                            "day": 2,
                            "stops": [
                                {"name": "Holiday Inn Resort Goa", "kind": "hotel"}
                            ],
                        },
                        {
                            "day": 3,
                            "stops": [
                                {"name": "Holiday Inn Resort Goa", "kind": "hotel"}
                            ],
                        },
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


def test_backwards_transport_timeline_is_rejected_without_persistence() -> None:
    _round_trip()
    before = json.loads(get_trip_plan.invoke({}))

    result = update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 2,
                            "stops": [
                                {
                                    "name": "Hotel Sayaji checkout",
                                    "kind": "hotel",
                                    "time": "08:00",
                                    "duration_min": 45,
                                },
                                {
                                    "name": "Old Indore walk",
                                    "kind": "attraction",
                                    "time": "10:00",
                                    "duration_min": 90,
                                },
                                {
                                    "name": "Drive Indore to Ujjain",
                                    "kind": "transport",
                                    "time": "08:30",
                                    "duration_min": 120,
                                },
                            ],
                        }
                    ]
                }
            )
        }
    )

    assert result.startswith("Error: itinerary times must increase")
    assert json.loads(get_trip_plan.invoke({})) == before


def test_hotel_checkout_is_fitted_before_the_drive_home() -> None:
    create_trip_plan.invoke(
        {
            "destination": "Meghalaya",
            "departure_date": "2027-11-02",
            "return_date": "2027-11-08",
            "origin": "Guwahati",
        }
    )

    result = update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 6,
                            "stops": [
                                {
                                    "name": "Hotel in Cherrapunji",
                                    "kind": "hotel",
                                    "time": "08:00",
                                    "note": "Check out",
                                },
                                {
                                    "name": "Drive: Cherrapunji to Guwahati",
                                    "kind": "transport",
                                    "time": "08:30",
                                    "duration_min": 300,
                                },
                                {
                                    "name": "Guwahati Airport",
                                    "kind": "transport",
                                    "time": "13:30",
                                },
                            ],
                        }
                    ]
                }
            )
        }
    )

    saved = json.loads(get_trip_plan.invoke({}))
    assert not result.startswith("Error:")
    assert _stops_on(saved, 6)[0]["time"] == "07:45"
    assert not [violation for violation in validate_plan(saved) if violation.code == "I1"]


def test_authoritative_closed_day_is_saved_with_a_repair_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_trip_plan.invoke(
        {
            "destination": "Paris",
            "departure_date": "2026-08-18",
            "return_date": "2026-08-18",
            "travel_scope": "destination_only",
        }
    )
    before = json.loads(get_trip_plan.invoke({}))
    monkeypatch.setattr(
        places_cache,
        "get_summary",
        lambda *_args, **_kwargs: {
            "name": "Louvre",
            "business_status": "OPERATIONAL",
            "weekday_descriptions": [
                "Monday: 9:00 AM - 6:00 PM",
                "Tuesday: Closed",
            ],
        },
    )

    result = update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 1,
                            "stops": [
                                {
                                    "name": "Louvre",
                                    "kind": "attraction",
                                    "time": "10:00",
                                    "duration_min": 120,
                                }
                            ],
                        }
                    ]
                }
            )
        }
    )

    # Losing the itinerary is worse than saving one that still needs a repair.
    assert "The itinerary was saved but is not yet consistent:" in result
    assert "Louvre is closed on Tuesdays" in result
    saved = json.loads(get_trip_plan.invoke({}))
    assert saved != before
    assert saved["day_wise_itinerary"][0]["stops"][0]["name"] == "Louvre"


def test_permanently_closed_place_update_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_trip_plan.invoke(
        {
            "destination": "Cape Town",
            "departure_date": "2027-11-15",
            "return_date": "2027-11-15",
            "travel_scope": "destination_only",
        }
    )
    before = json.loads(get_trip_plan.invoke({}))
    monkeypatch.setattr(
        places_cache,
        "get_summary",
        lambda *_args, **_kwargs: {
            "name": "The Company's Garden Restaurant",
            "business_status": "CLOSED_PERMANENTLY",
        },
    )

    result = update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 1,
                            "stops": [
                                {
                                    "name": "The Company's Garden Restaurant",
                                    "kind": "meal",
                                    "time": "12:00",
                                    "duration_min": 60,
                                }
                            ],
                        }
                    ]
                }
            )
        }
    )

    assert result.startswith("Error:")
    assert "reported closed for business" in result
    assert "Replace them with places that are still operating" in result
    assert json.loads(get_trip_plan.invoke({})) == before


def test_permanently_closed_place_selection_is_not_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _round_trip()
    before = json.loads(get_trip_plan.invoke({}))
    monkeypatch.setattr(
        places_cache,
        "get_summary",
        lambda *_args, **_kwargs: {
            "name": "Closed Museum",
            "business_status": "CLOSED_PERMANENTLY",
        },
    )

    result = add_selection("attraction", {"name": "Closed Museum"})

    assert result["ok"] is False
    assert "reported closed for business" in result["alerts"][0]
    assert json.loads(get_trip_plan.invoke({})) == before


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


def test_a_return_leg_added_later_still_closes_a_regional_trip() -> None:
    """The reported defect: flights added after planning put the flight home in
    the middle of the last day, because a regional destination never matched."""
    plan = {
        "origin": "Bangalore",
        "destination": "Rajasthan",
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {
                        "name": "Flight Bangalore to Jaipur",
                        "kind": "flight",
                        "time": "09:00",
                        "duration_min": 150,
                    },
                    {"name": "Hotel Sayaji", "kind": "hotel", "time": "14:00", "duration_min": 45},
                ],
            },
            {
                "day": 2,
                "stops": [{"name": "Rajwada Palace", "kind": "attraction", "time": "10:00"}],
            },
            {
                "day": 3,
                "stops": [
                    {
                        "name": "Flight Udaipur to Bangalore",
                        "kind": "flight",
                        "time": "11:00",
                        "duration_min": 150,
                    },
                    {"name": "Kaanch Mandir", "kind": "attraction", "time": "15:00"},
                    {"name": "Mahakaleshwar Temple", "kind": "attraction", "time": "16:30"},
                ],
            },
        ],
    }
    trip_planner._reflow_unbooked_attractions(plan)
    assert [stop["name"] for stop in _stops_on(plan, 3)][-1] == "Flight Udaipur to Bangalore"


def test_flights_added_later_must_be_submitted_in_chronological_order() -> None:
    create_trip_plan.invoke(
        {
            "destination": "Rajasthan",
            "departure_date": "2026-09-01",
            "return_date": "2026-09-03",
            "origin": "Bangalore",
        }
    )
    planned_days = [
        {
            "day": 1,
            "stops": [
                {"name": "Hotel Sayaji", "kind": "hotel", "time": "14:00", "duration_min": 45}
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
                    "name": "Kaanch Mandir",
                    "kind": "attraction",
                    "time": "09:00",
                    "duration_min": 90,
                },
                {
                    "name": "Mahakaleshwar Temple",
                    "kind": "attraction",
                    "time": "11:00",
                    "duration_min": 90,
                },
            ],
        },
    ]
    update_trip_plan.invoke({"updates_json": json.dumps({"day_wise_itinerary": planned_days})})

    # "can you include the flight connections as we are based at bangalore"
    with_flights = json.loads(json.dumps(planned_days))
    with_flights[0]["stops"].insert(
        0,
        {
            "name": "Flight Bangalore to Jaipur",
            "kind": "flight",
            "time": "09:00",
            "duration_min": 150,
        },
    )
    with_flights[2]["stops"].insert(
        0,
        {
            "name": "Flight Udaipur to Bangalore",
            "kind": "flight",
            "time": "07:00",
            "duration_min": 150,
        },
    )
    result = update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "selected_flights": [{"airline": "Test Air"}],
                    "day_wise_itinerary": with_flights,
                }
            )
        }
    )

    plan = json.loads(get_trip_plan.invoke({}))
    assert result.startswith("Error: itinerary times must increase")
    assert _stops_on(plan, 3) == planned_days[2]["stops"]


def test_a_travel_infeasible_planner_update_is_retimed_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinates = {
        "Dubai Museum": (25.2635, 55.2972),
        "Dubai Marina Walk": (25.0805, 55.1403),
    }
    monkeypatch.setattr(
        places_cache,
        "get_summary",
        lambda name, _destination: {
            "lat": coordinates[name][0],
            "lng": coordinates[name][1],
        },
    )
    create_trip_plan.invoke(
        {
            "destination": "Dubai",
            "departure_date": "2026-11-20",
            "return_date": "2026-11-24",
            "travel_scope": "destination_only",
        }
    )

    result = update_trip_plan.invoke(
        {
            "updates_json": json.dumps(
                {
                    "day_wise_itinerary": [
                        {
                            "day": 1,
                            "stops": [
                                {
                                    "name": "Dubai Museum",
                                    "kind": "attraction",
                                    "time": "10:00",
                                    "duration_min": 90,
                                },
                                {
                                    "name": "Dubai Marina Walk",
                                    "kind": "attraction",
                                    "time": "12:00",
                                    "duration_min": 90,
                                },
                            ],
                        }
                    ]
                }
            )
        }
    )

    saved = json.loads(get_trip_plan.invoke({}))
    assert "Adjusted travel-infeasible visit times before saving" in result
    assert not [item for item in validate_plan(saved) if item.code == "I4"]


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
                                {"name": "Hotel Sayaji", "kind": "hotel"},
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
    assert len(_stops_on(plan, 2)) == 5


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


def test_resetting_keeps_destination_only_guard_coverage() -> None:
    create_trip_plan.invoke(
        {
            "destination": "Udaipur",
            "departure_date": "2026-11-07",
            "return_date": "2026-11-09",
            "travel_scope": "destination_only",
        }
    )

    after = trip_planner.reset_active_trip()

    assert after is not None
    assert after["origin"] == ""
    assert after["travel_scope"] == "destination_only"
    assert not [violation for violation in validate_plan(after) if violation.code == "I10"]
