"""A repair may clear the planner's mistakes and no one else's.

The line under test is ownership. When every stop is the planner's suggestion,
a contradiction is its to fix and it should just fix it. When the contradiction
sits inside something the traveller booked, every legal repair would move a
commitment, so the pass must stop and say so rather than quietly reshaping the
trip around it.
"""

from __future__ import annotations

import pytest

from tripplanner.tools import trip_common, trip_effort, trip_guard
from tripplanner.web import trip_repair

_OPEN = [
    f"{day}: 9:00 AM - 6:00 PM"
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
]
_SHUT_TUESDAY = ["Tuesday: Closed" if line.startswith("Tuesday") else line for line in _OPEN]

_PLACES = {
    "Louvre Museum": {"lat": 48.8606, "lng": 2.3376, "weekday_descriptions": _SHUT_TUESDAY},
    "Musee d'Orsay": {"lat": 48.8600, "lng": 2.3266, "weekday_descriptions": _OPEN},
    "Le Marais": {"lat": 48.8612, "lng": 2.3581, "weekday_descriptions": _OPEN},
}


@pytest.fixture(autouse=True)
def located(monkeypatch: pytest.MonkeyPatch) -> None:
    def summary(name: str, _destination: str = "") -> dict[str, object]:
        found = _PLACES.get(name)
        return {"name": name, "business_status": "OPERATIONAL", **found} if found else {}

    for module in (trip_common, trip_guard, trip_effort):
        monkeypatch.setattr(module, "_summary_for_place", summary, raising=False)


def _stop(name: str, at: str, **extra: object) -> dict[str, object]:
    return {"name": name, "kind": "attraction", "time": at, "duration_min": 90, **extra}


def _plan(*days: list[dict[str, object]]) -> dict[str, object]:
    # 2026-09-07 is a Monday, so Day 2 is the Tuesday the Louvre shuts.
    return {
        "origin": "Bengaluru",
        "destination": "Paris",
        "departure_date": "2026-09-07",
        "day_wise_itinerary": [
            {"day": index + 1, "stops": stops} for index, stops in enumerate(days)
        ],
    }


def _closed_day_codes(plan: dict[str, object]) -> list[str]:
    return [item.code for item in trip_guard.validate_plan(plan) if item.code == "I11"]


def test_it_clears_a_closed_day_it_owns() -> None:
    broken = _plan(
        [_stop("Musee d'Orsay", "10:00")],
        [_stop("Louvre Museum", "10:00")],
    )
    assert _closed_day_codes(broken) == ["I11"]

    outcome = trip_repair.repair(broken)
    assert outcome["changed"]
    assert _closed_day_codes(outcome["plan"]) == []
    assert outcome["blocked"] == []
    assert any("Louvre Museum" in line for line in outcome["sentences"])


def test_it_will_not_move_a_booking_to_clear_one() -> None:
    booked = _plan(
        [_stop("Musee d'Orsay", "10:00")],
        [_stop("Louvre Museum", "10:00", booked=True)],
    )
    outcome = trip_repair.repair(booked)
    assert not any(move["name"] == "Louvre Museum" for move in outcome["moves"])
    assert [item["stop"] for item in outcome["blocked"]] == ["Louvre Museum"]
    assert outcome["blocked"][0]["reason"] == "you booked it"


def test_a_sound_trip_is_left_alone() -> None:
    tidy = _plan(
        [_stop("Louvre Museum", "10:00")],
        [_stop("Musee d'Orsay", "10:00")],
    )
    outcome = trip_repair.repair(tidy)
    assert not outcome["changed"]
    assert outcome["moves"] == []
    assert outcome["blocked"] == []


def test_it_reports_the_before_and_after_it_acted_on() -> None:
    broken = _plan(
        [_stop("Musee d'Orsay", "10:00")],
        [_stop("Louvre Museum", "10:00")],
    )
    outcome = trip_repair.repair(broken)
    assert outcome["before"]["contradictions"] > outcome["after"]["contradictions"]


def test_a_confirmed_place_is_also_the_travellers() -> None:
    plan = _plan(
        [_stop("Musee d'Orsay", "10:00")],
        [_stop("Louvre Museum", "10:00")],
    )
    plan["place_bindings"] = {
        "Louvre Museum": {"lat": 48.8606, "lng": 2.3376, "name": "Louvre Museum"}
    }
    outcome = trip_repair.repair(plan)
    assert not any(move["name"] == "Louvre Museum" for move in outcome["moves"])
    assert outcome["blocked"][0]["reason"] == "you confirmed which place this is"
