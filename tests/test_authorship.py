"""Ownership decides what a rebalance is allowed to touch.

The asymmetry under test: mistaking a suggestion for a commitment only makes the
planner timid, while mistaking a commitment for a suggestion moves a booking the
traveller already paid for. Every ambiguous signal therefore has to resolve to
"the planner's", and these tests exist to keep it that way.
"""

from __future__ import annotations

from tripplanner import authorship


def _trip(*days: list[dict[str, object]]) -> dict[str, object]:
    return {
        "day_wise_itinerary": [
            {"day": index + 1, "stops": stops} for index, stops in enumerate(days)
        ]
    }


def test_a_plain_suggestion_belongs_to_the_planner() -> None:
    stop = {"name": "Louvre Museum", "kind": "attraction"}
    assert authorship.stop_ownership(stop).owner == authorship.PLANNER
    assert not authorship.stop_ownership(stop).pinned


def test_a_booked_stop_is_the_travellers() -> None:
    owned = authorship.stop_ownership({"name": "Louvre Museum", "booked": True})
    assert owned.pinned
    assert owned.reason == "you booked it"


def test_a_paid_stop_counts_as_committed() -> None:
    assert authorship.stop_ownership({"name": "Versailles", "price": 27.0}).pinned
    assert not authorship.stop_ownership({"name": "Versailles", "price": 0}).pinned
    assert not authorship.stop_ownership({"name": "Versailles", "price": ""}).pinned


def test_an_overridden_decision_marks_the_stop_as_chosen() -> None:
    stop = {"name": "Hotel Chambiges", "decision_id": "dec_stay_paris"}
    assert not authorship.stop_ownership(stop).pinned
    owned = authorship.stop_ownership(stop, overridden_decisions={"dec_stay_paris"})
    assert owned.pinned
    assert owned.reason == "you picked this over the suggestion"


def test_a_confirmed_place_marks_the_stop_as_chosen() -> None:
    stop = {"name": "Le Consulat", "kind": "meal"}
    owned = authorship.stop_ownership(stop, confirmed_places={"le consulat"})
    assert owned.pinned
    assert owned.reason == "you confirmed which place this is"


def test_a_trip_nobody_touched_pins_nothing() -> None:
    plan = _trip(
        [{"name": "Louvre Museum"}, {"name": "Le Marais"}],
        [{"name": "Eiffel Tower"}],
    )
    assert authorship.pinned_stops(plan) == {}
    assert authorship.free_ratio(plan) == 1.0


def test_one_booking_does_not_freeze_the_rest() -> None:
    plan = _trip(
        [{"name": "Louvre Museum", "booked": True}, {"name": "Le Marais"}],
        [{"name": "Eiffel Tower"}],
    )
    pinned = authorship.pinned_stops(plan)
    assert list(pinned) == [(1, "Louvre Museum")]
    assert authorship.free_ratio(plan) == 2 / 3


def test_a_fully_booked_trip_leaves_nothing_to_move() -> None:
    plan = _trip(
        [{"name": "Louvre Museum", "booked": True}],
        [{"name": "Eiffel Tower", "booked": True}],
    )
    assert authorship.free_ratio(plan) == 0.0


def test_the_same_place_on_two_days_is_owned_per_day() -> None:
    plan = _trip(
        [{"name": "Hotel Chambiges", "booked": True}],
        [{"name": "Hotel Chambiges"}],
    )
    pinned = authorship.pinned_stops(plan)
    assert (1, "Hotel Chambiges") in pinned
    assert (2, "Hotel Chambiges") not in pinned


def test_an_empty_or_malformed_plan_is_safe() -> None:
    assert authorship.trip_ownership(None) == {}
    assert authorship.trip_ownership({"day_wise_itinerary": "nonsense"}) == {}
    assert authorship.free_ratio(None) == 0.0
