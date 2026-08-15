"""A rebalance is only trustworthy if it cannot do harm.

These tests are mostly about what the optimiser must refuse: moving a stop the
traveller chose, accepting an arrangement with more contradictions, or churning
a plan that was already fine. Improvement is the easy half.
"""

from __future__ import annotations

import pytest

from tripplanner.tools import trip_common, trip_effort, trip_guard, trip_rebalance

# Two tight clusters ~9 km apart, so mixing them across days costs real travel.
_WEST = {
    "Eiffel Tower": (48.8584, 2.2945),
    "Musee d'Orsay": (48.8600, 2.3266),
    "Rodin Museum": (48.8553, 2.3158),
}
_EAST = {
    "Le Marais": (48.8612, 2.3581),
    "Place des Vosges": (48.8555, 2.3655),
    "Pere Lachaise": (48.8614, 2.3922),
}
_COORDS = {**_WEST, **_EAST}

_OPEN_ALL_WEEK = [
    f"{day}: 9:00 AM - 8:00 PM"
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
]


@pytest.fixture(autouse=True)
def located(monkeypatch: pytest.MonkeyPatch) -> None:
    def summary(name: str, _destination: str = "") -> dict[str, object]:
        coords = _COORDS.get(name)
        if not coords:
            return {}
        return {
            "name": name,
            "lat": coords[0],
            "lng": coords[1],
            "business_status": "OPERATIONAL",
            "weekday_descriptions": _OPEN_ALL_WEEK,
        }

    for module in (trip_common, trip_guard, trip_effort):
        monkeypatch.setattr(module, "_summary_for_place", summary, raising=False)


def _stop(name: str, at: str, **extra: object) -> dict[str, object]:
    return {"name": name, "kind": "attraction", "time": at, "duration_min": 90, **extra}


def _plan(*days: list[dict[str, object]], titles: list[str] | None = None) -> dict[str, object]:
    itinerary = []
    for index, stops in enumerate(days):
        entry: dict[str, object] = {"day": index + 1, "stops": stops}
        if titles:
            entry["title"] = titles[index]
        itinerary.append(entry)
    return {
        "origin": "Bengaluru",
        "destination": "Paris",
        "departure_date": "2026-09-07",
        "day_wise_itinerary": itinerary,
    }


#: One stop from each cluster stranded on the wrong day.
_MIXED = _plan(
    [
        _stop("Eiffel Tower", "09:00"),
        _stop("Musee d'Orsay", "12:00"),
        _stop("Pere Lachaise", "15:00"),
    ],
    [
        _stop("Le Marais", "09:00"),
        _stop("Place des Vosges", "12:00"),
        _stop("Rodin Museum", "15:00"),
    ],
)


def test_it_reduces_travel_by_grouping_the_day() -> None:
    result = trip_rebalance.rebalance(_MIXED)
    assert result.changed
    assert result.after.travel_min < result.before.travel_min
    assert result.after.contradictions <= result.before.contradictions


def test_it_leaves_a_good_plan_alone() -> None:
    tidy = _plan(
        [_stop(name, at) for name, at in zip(_WEST, ("09:00", "12:00", "15:00"))],
        [_stop(name, at) for name, at in zip(_EAST, ("09:00", "12:00", "15:00"))],
    )
    result = trip_rebalance.rebalance(tidy)
    assert not result.changed
    assert result.plan == tidy


def test_it_never_moves_a_stop_the_traveller_chose() -> None:
    pinned = {(1, "Pere Lachaise"), (2, "Rodin Museum")}
    result = trip_rebalance.rebalance(_MIXED, pinned=pinned)
    moved = {move.name for move in result.moves}
    assert not moved & {"Pere Lachaise", "Rodin Museum"}


def test_pinning_everything_leaves_nothing_to_do() -> None:
    everything = {
        (day, trip_common._stop_name(stop))
        for day, _entry, stops in trip_guard.days_of(_MIXED)
        for stop in stops
    }
    result = trip_rebalance.rebalance(_MIXED, pinned=everything)
    assert not result.changed


def test_it_reports_each_move_in_plain_words() -> None:
    result = trip_rebalance.rebalance(_MIXED)
    sentences = result.sentences()
    assert sentences
    assert all(line.startswith("Moved ") and "Day" in line for line in sentences)


def test_a_move_never_adds_a_contradiction() -> None:
    result = trip_rebalance.rebalance(_MIXED)
    assert result.after.contradictions <= result.before.contradictions
    assert len(trip_guard.validate_plan(result.plan)) == result.after.contradictions


def test_a_stop_named_by_another_days_title_counts_as_misplaced() -> None:
    titled = _plan(
        [_stop("Eiffel Tower", "09:00"), _stop("Le Marais", "12:00")],
        [_stop("Place des Vosges", "09:00")],
        titles=["Day 1 · Eiffel Tower", "Day 2 · Le Marais"],
    )
    assert trip_rebalance.score(titled).misplaced == 1


def test_it_stays_within_its_time_budget() -> None:
    result = trip_rebalance.rebalance(_MIXED, budget_ms=0)
    assert result.exhausted
    assert result.rounds <= 1


def test_an_empty_plan_is_safe() -> None:
    result = trip_rebalance.rebalance({"destination": "Paris"})
    assert not result.changed
    assert result.before.travel_min == 0


# --------------------------------------------------------------------------- #
# what a cleared contradiction may and may not buy                             #
# --------------------------------------------------------------------------- #


def test_clearing_a_contradiction_is_worth_a_lot_but_not_everything() -> None:
    """It must beat ordinary travel savings, and lose to wrecking the trip."""
    one_fault = trip_rebalance.Score(1, 0, 0.0, 0, 0, 0)
    long_drive = trip_rebalance.Score(0, 200, 0.0, 0, 0, 0)
    assert long_drive.total < one_fault.total

    ruined = trip_rebalance.Score(0, 0, 0.0, 0, 0, 400)
    assert one_fault.total < ruined.total


def test_the_leaving_day_is_not_free_time() -> None:
    leaving = _plan(
        [_stop("Eiffel Tower", "09:00")],
        [_stop("Musee d'Orsay", "09:00"), _stop("Rodin Museum", "12:00")],
    )
    leaving["return_date"] = "2026-09-08"
    assert trip_rebalance.score(leaving).departure_load > 0

    early = _plan(
        [_stop("Eiffel Tower", "09:00"), _stop("Musee d'Orsay", "12:00")],
        [_stop("Rodin Museum", "09:00")],
    )
    early["return_date"] = "2026-09-08"
    assert trip_rebalance.score(early).departure_load == 0


def test_a_trip_that_never_said_when_it_goes_home_is_not_penalised() -> None:
    open_ended = _plan(
        [_stop("Eiffel Tower", "09:00")],
        [_stop("Musee d'Orsay", "09:00"), _stop("Rodin Museum", "12:00")],
    )
    assert trip_rebalance.score(open_ended).departure_load == 0


def test_a_heading_that_no_longer_describes_its_day_is_rewritten() -> None:
    stale = _plan(
        [_stop("Eiffel Tower", "09:00"), _stop("Musee d'Orsay", "12:00")],
        [_stop("Le Marais", "09:00")],
        titles=["Day 1 · Eiffel Tower & Pere Lachaise", "Day 2 · Le Marais"],
    )
    trip_rebalance._retitle(stale, {1, 2})
    titles = {day: entry.get("title") for day, entry, _ in trip_guard.days_of(stale)}
    assert titles[1] == "Day 1 · Eiffel Tower & Musee d'Orsay"
    assert titles[2] == "Day 2 · Le Marais"


def test_a_day_left_with_nothing_named_loses_its_heading() -> None:
    emptied = _plan([], titles=["Day 1 · Eiffel Tower"])
    trip_rebalance._retitle(emptied, {1})
    assert trip_guard.days_of(emptied)[0][1]["title"] == "Day 1"


def test_a_stop_named_in_its_own_heading_is_not_traded_away() -> None:
    """The theme term has to outweigh a few minutes of driving."""
    anchored = _plan(
        [
            _stop("Eiffel Tower", "09:00"),
            _stop("Musee d'Orsay", "12:00"),
            _stop("Pere Lachaise", "15:00"),
        ],
        [
            _stop("Le Marais", "09:00"),
            _stop("Place des Vosges", "12:00"),
            _stop("Rodin Museum", "15:00"),
        ],
        titles=["Day 1 · Eiffel Tower & Pere Lachaise", "Day 2 · Le Marais"],
    )
    result = trip_rebalance.rebalance(anchored)
    assert "Pere Lachaise" not in {move.name for move in result.moves}


def test_a_heading_still_true_after_the_move_is_left_alone() -> None:
    result = trip_rebalance.rebalance(
        _plan(
            [
                _stop("Eiffel Tower", "09:00"),
                _stop("Musee d'Orsay", "12:00"),
                _stop("Pere Lachaise", "15:00"),
            ],
            [
                _stop("Le Marais", "09:00"),
                _stop("Place des Vosges", "12:00"),
                _stop("Rodin Museum", "15:00"),
            ],
            titles=["Day 1 · Eiffel Tower", "Day 2 · Le Marais"],
        )
    )
    titles = {day: entry.get("title") for day, entry, _ in trip_guard.days_of(result.plan)}
    assert titles[1] == "Day 1 · Eiffel Tower"
