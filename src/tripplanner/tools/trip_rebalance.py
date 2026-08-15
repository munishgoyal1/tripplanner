"""Move the planner's own suggestions until the whole trip reads better.

``choose_placement`` answers "where may this stop go", one stop at a time and
one day at a time. That is enough to keep a trip legal and not enough to keep it
good: fixing Tuesday by overloading Wednesday satisfies every invariant and
produces a worse holiday. This module asks the other question -- given
everything the planner is still allowed to move, is there an arrangement of the
whole trip that costs the traveller less.

Three rules keep an optimiser from becoming a liability:

    It may never move what the traveller chose.
    It may never accept a plan with more contradictions than it started with.
    It must be able to say what each move bought, in minutes and days.

The search is a plain hill climb seeded from the current itinerary, accepting
only strict improvements, so it converges, never churns a plan the traveller is
happy with, and returns the plan unchanged when it has nothing to offer. It runs
on cached coordinates and parsed opening hours alone; verifying a candidate with
live routing would cost more than the whole search.
"""

from __future__ import annotations

import re
import time
from copy import deepcopy
from dataclasses import dataclass
from statistics import pstdev
from typing import Any

from tripplanner.tools import trip_guard
from tripplanner.tools.trip_common import _stop_kind, _stop_name

#: Enough slack before closing that the visit is not a race.
_COMFORT_MIN = 30
#: What clearing one contradiction is worth. Heavy enough to win almost every
#: trade, finite so it cannot buy an arrangement that ruins the rest of the
#: trip: an absolute ordering once moved a museum onto the departure day
#: because nothing was allowed to outrank a cleared fault.
_CONTRADICTION_COST = 240
#: Minutes of sightseeing a leaving day carries before it starts to hurt.
_DEPARTURE_ALLOWANCE = 90
#: Words in a day title that name no place.
_TITLE_NOISE = frozenset({
    "day", "arrival", "arrive", "departure", "depart", "free", "leisure", "and",
    "the", "trip", "tour", "explore", "exploring", "morning", "afternoon",
    "evening", "night", "rest", "travel", "transfer", "return", "home",
})

_MOVABLE_KINDS = frozenset({"attraction", "meal"})
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Score:
    """What an arrangement costs, in terms a traveller could check."""

    contradictions: int
    travel_min: int
    imbalance: float
    rushed: int
    misplaced: int
    departure_load: int

    @property
    def total(self) -> float:
        # Minutes are the unit; the rest are converted into minutes of regret.
        return (
            self.travel_min
            + self.contradictions * _CONTRADICTION_COST
            + self.imbalance * 0.5
            + self.rushed * 20
            + self.misplaced * 45
            + self.departure_load
        )


@dataclass(frozen=True)
class Move:
    name: str
    from_day: int
    to_day: int
    time: str
    saved_travel_min: int


@dataclass(frozen=True)
class Rebalance:
    plan: dict[str, Any]
    moves: tuple[Move, ...]
    before: Score
    after: Score
    rounds: int
    exhausted: bool

    @property
    def changed(self) -> bool:
        return bool(self.moves)

    def sentences(self) -> list[str]:
        out = []
        for move in self.moves:
            saved = (
                f", saving about {move.saved_travel_min} minutes of travel"
                if move.saved_travel_min > 0
                else ""
            )
            out.append(
                f"Moved {move.name} from Day {move.from_day} to Day {move.to_day} "
                f"at {move.time}{saved}."
            )
        return out


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        token
        for token in _TOKEN_RE.findall(str(text or "").casefold())
        if len(token) > 2 and token not in _TITLE_NOISE
    )


def _day_travel_min(stops: list[Any], destination: str) -> int:
    located = [
        coords
        for stop in sorted(
            (stop for stop in stops if trip_guard._time_of(stop) is not None),
            key=lambda stop: trip_guard._time_of(stop) or 0,
        )
        if _stop_kind(stop) not in {"flight", "transport"}
        and (coords := trip_guard._coords(stop, destination))
    ]
    return sum(
        trip_guard.travel_min(located[index], located[index + 1])
        for index in range(len(located) - 1)
    )


def _active_min(stops: list[Any]) -> int:
    return sum(
        trip_guard._duration_of(stop)
        for stop in stops
        if _stop_kind(stop) in _MOVABLE_KINDS
    )


def score(plan: dict[str, Any]) -> Score:
    """Cost the whole arrangement. Lower is better; the unit is a minute."""
    destination = str(plan.get("destination") or "")
    dates = trip_guard.day_dates(plan)
    structured = trip_guard.days_of(plan)

    titles = {day: _tokens(entry.get("title")) for day, entry, _stops in structured}
    # Only a day the plan itself calls the end of the trip is a leaving day.
    # Guessing from "it is last" would penalise the final day of every fixture
    # and every open-ended trip that never said when it goes home.
    going_home = str(plan.get("return_date") or "").strip()
    last_day = next(
        (day for day, day_iso in dates.items() if going_home and day_iso == going_home),
        0,
    )
    travel = 0
    loads: list[int] = []
    rushed = 0
    misplaced = 0
    departure_load = 0

    for day, _entry, stops in structured:
        travel += _day_travel_min(stops, destination)
        active = _active_min(stops)
        loads.append(active)
        if day == last_day and day > 1:
            # Nothing anchors the end of a trip that never named a return leg,
            # so the leaving day otherwise looks like a day with free hours.
            departure_load += max(0, active - _DEPARTURE_ALLOWANCE)
        day_iso = dates.get(day, "")
        for stop in stops:
            name = _stop_name(stop)
            if _stop_kind(stop) not in _MOVABLE_KINDS or not name:
                continue
            start = trip_guard._time_of(stop)
            if start is not None:
                windows = trip_guard.facts_for(name, destination).hours_on(day_iso)
                ends = start + trip_guard._duration_of(stop)
                if windows and all(
                    closes - ends < _COMFORT_MIN for _opens, closes in windows
                ):
                    rushed += 1
            here = _tokens(name)
            if here and not (here & titles.get(day, frozenset())):
                # Named by another day's heading: that day is where it belongs.
                if any(here & other for key, other in titles.items() if key != day):
                    misplaced += 1

    return Score(
        contradictions=len(trip_guard.validate_plan(plan)),
        travel_min=travel,
        imbalance=pstdev(loads) if len(loads) > 1 else 0.0,
        rushed=rushed,
        misplaced=misplaced,
        departure_load=departure_load,
    )


def _detach(plan: dict[str, Any], day: int, name: str) -> dict[str, Any] | None:
    """A copy of the plan with one stop lifted out, or None if it is not there."""
    candidate = deepcopy(plan)
    for entry in candidate.get("day_wise_itinerary") or []:
        if not isinstance(entry, dict) or entry.get("day") != day:
            continue
        stops = entry.get("stops")
        if not isinstance(stops, list):
            return None
        for index, stop in enumerate(stops):
            if _stop_name(stop) == name:
                stops.pop(index)
                return candidate
    return None


def _attach(
    plan: dict[str, Any], day: int, index: int, stop: dict[str, Any], at: str
) -> dict[str, Any]:
    candidate = deepcopy(plan)
    for entry in candidate.get("day_wise_itinerary") or []:
        if not isinstance(entry, dict) or entry.get("day") != day:
            continue
        stops = entry.setdefault("stops", [])
        placed = deepcopy(stop)
        placed["time"] = at
        stops.insert(min(index, len(stops)), placed)
        break
    return candidate


def _movable(
    plan: dict[str, Any], pinned: set[tuple[int, str]]
) -> list[tuple[int, dict[str, Any]]]:
    out: list[tuple[int, dict[str, Any]]] = []
    for day, _entry, stops in trip_guard.days_of(plan):
        for stop in stops:
            name = _stop_name(stop)
            if not name or not isinstance(stop, dict):
                continue
            if _stop_kind(stop) not in _MOVABLE_KINDS:
                continue
            if (day, name) in pinned:
                continue
            out.append((day, stop))
    return sorted(out, key=lambda pair: (pair[0], _stop_name(pair[1])))


def _place(
    plan: dict[str, Any], stop: dict[str, Any], from_day: int, to_day: int
) -> tuple[dict[str, Any], Move] | None:
    """Put an already-lifted stop onto ``to_day``, or report that it cannot go."""
    name = _stop_name(stop)
    placement, _ = trip_guard.choose_placement(
        plan,
        name,
        _stop_kind(stop),
        duration_min=trip_guard._duration_of(stop),
        preferred_day=to_day,
    )
    if placement is None:
        return None
    return (
        _attach(plan, to_day, placement.index, stop, placement.time),
        Move(name, from_day, to_day, placement.time, 0),
    )


def _relocated(
    current: dict[str, Any], from_day: int, stop: dict[str, Any], to_day: int
) -> tuple[dict[str, Any], Move] | None:
    detached = _detach(current, from_day, _stop_name(stop))
    if detached is None:
        return None
    return _place(detached, stop, from_day, to_day)


def _exchanged(
    current: dict[str, Any],
    left: tuple[int, dict[str, Any]],
    right: tuple[int, dict[str, Any]],
) -> tuple[dict[str, Any], tuple[Move, Move]] | None:
    """Trade two stops between their days.

    Relocation alone cannot regroup a trip: taking one stop off Tuesday and
    adding it to Wednesday leaves one day heavy and one light, which costs more
    than the travel it saves. An exchange keeps both days the size they were.
    """
    left_day, left_stop = left
    right_day, right_stop = right
    stripped = _detach(current, left_day, _stop_name(left_stop))
    if stripped is None:
        return None
    stripped = _detach(stripped, right_day, _stop_name(right_stop))
    if stripped is None:
        return None

    first = _place(stripped, left_stop, left_day, right_day)
    if first is None:
        return None
    plan, left_move = first
    second = _place(plan, right_stop, right_day, left_day)
    if second is None:
        return None
    plan, right_move = second
    return plan, (left_move, right_move)


def _candidates(
    current: dict[str, Any], pinned: set[tuple[int, str]], deadline: float
) -> Any:
    """Every arrangement one step away, cheapest neighbourhood first."""
    movable = _movable(current, pinned)
    for from_day, stop in movable:
        for to_day, _entry, _stops in trip_guard.days_of(current):
            if to_day == from_day or time.perf_counter() > deadline:
                continue
            moved = _relocated(current, from_day, stop, to_day)
            if moved is not None:
                yield moved[0], (moved[1],)
    for index, left in enumerate(movable):
        for right in movable[index + 1 :]:
            if left[0] == right[0] or time.perf_counter() > deadline:
                continue
            traded = _exchanged(current, left, right)
            if traded is not None:
                yield traded[0], traded[1]


def _retitle(plan: dict[str, Any], touched: set[int]) -> None:
    """Stop a day's heading naming stops that have left it.

    "Day 3 - Louvre & Marais" holding neither is a plan lying about itself,
    which is worse than the crooked schedule the rebalance just fixed.
    """
    for day, entry, stops in trip_guard.days_of(plan):
        if day not in touched:
            continue
        heading = _tokens(entry.get("title"))
        if not heading:
            continue
        present = (
            frozenset().union(*(_tokens(_stop_name(stop)) for stop in stops))
            if stops
            else frozenset()
        )
        if heading <= present:
            continue
        named = [
            _stop_name(stop)
            for stop in stops
            if _stop_kind(stop) == "attraction" and _stop_name(stop)
        ][:2]
        entry["title"] = f"Day {day} \u00b7 {' & '.join(named)}" if named else f"Day {day}"


def rebalance(
    plan: dict[str, Any],
    *,
    pinned: set[tuple[int, str]] | frozenset[tuple[int, str]] = frozenset(),
    max_rounds: int = 8,
    budget_ms: int = 400,
) -> Rebalance:
    """Improve the arrangement without touching what the traveller chose."""
    current = deepcopy(plan)
    before = score(current)
    best_score = before
    moves: list[Move] = []
    deadline = time.perf_counter() + budget_ms / 1000
    rounds = 0
    exhausted = False

    while rounds < max_rounds:
        rounds += 1
        best: tuple[float, dict[str, Any], tuple[Move, ...]] | None = None

        for candidate, candidate_moves in _candidates(current, set(pinned), deadline):
            candidate_score = score(candidate)
            if candidate_score.contradictions > before.contradictions:
                continue
            if candidate_score.total >= best_score.total:
                continue
            if best is None or candidate_score.total < best[0]:
                saved = best_score.travel_min - candidate_score.travel_min
                best = (
                    candidate_score.total,
                    candidate,
                    tuple(
                        Move(move.name, move.from_day, move.to_day, move.time, saved)
                        for move in candidate_moves
                    ),
                )

        if time.perf_counter() > deadline:
            exhausted = True
        if best is None:
            break
        _total, current, accepted = best
        best_score = score(current)
        moves.extend(accepted)
        if exhausted:
            break

    if moves:
        _retitle(current, {move.from_day for move in moves} | {move.to_day for move in moves})

    return Rebalance(
        plan=current,
        moves=tuple(moves),
        before=before,
        after=best_score,
        rounds=rounds,
        exhausted=exhausted,
    )
