"""Who chose each stop: the planner, or the traveller.

The planner may rearrange its own suggestions freely. It may not quietly move
something the traveller committed to, because the cost of being wrong is not
symmetric: a suboptimal day is an inconvenience, a moved booking is a wasted
ticket and a lost afternoon.

Deliberately per stop rather than per trip. A trip is not "touched" or
"untouched" -- it is a mix, and the mix changes as the traveller engages. One
pinned restaurant should not freeze the other twenty stops, and a booked museum
should not be movable just because everything around it was suggested. Ownership
therefore enters the optimiser as a constraint, not as a mode switch, and the
two extremes fall out for free: a trip nobody has touched has nothing pinned,
and a trip where every stop is booked has nothing to move.

Only unambiguous signals count. ``selected_hotels`` and ``selected_activities``
are written by the agent as well as by the traveller, so they are not evidence
of a choice and are left out on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PLANNER = "planner"
USER = "user"


@dataclass(frozen=True)
class Ownership:
    """Who owns one stop, and the words to explain it with."""

    owner: str
    reason: str = ""

    @property
    def pinned(self) -> bool:
        return self.owner == USER


#: The planner's own suggestion, accepted by default rather than chosen.
SUGGESTED = Ownership(PLANNER)


def _name(stop: Any) -> str:
    if isinstance(stop, dict):
        return str(stop.get("name") or "").strip()
    return str(stop or "").strip()


def _is_committed(stop: dict[str, Any]) -> bool:
    if stop.get("booked"):
        return True
    price = stop.get("price") or stop.get("cost")
    return bool(price) and str(price).strip() not in {"", "0"}


def stop_ownership(
    stop: Any,
    *,
    confirmed_places: set[str] | frozenset[str] = frozenset(),
    overridden_decisions: set[str] | frozenset[str] = frozenset(),
) -> Ownership:
    """Classify one stop by the strongest evidence that the traveller chose it."""
    if not isinstance(stop, dict):
        return SUGGESTED
    if _is_committed(stop):
        return Ownership(USER, "you booked it")
    decision_id = str(stop.get("decision_id") or "").strip()
    if decision_id and decision_id in overridden_decisions:
        return Ownership(USER, "you picked this over the suggestion")
    if _name(stop).casefold() in confirmed_places:
        return Ownership(USER, "you confirmed which place this is")
    return SUGGESTED


def trip_ownership(
    plan: dict[str, Any] | None,
    *,
    confirmed_places: set[str] | frozenset[str] = frozenset(),
    overridden_decisions: set[str] | frozenset[str] = frozenset(),
) -> dict[tuple[int, str], Ownership]:
    """Ownership for every named stop, keyed by ``(day, name)``."""
    out: dict[tuple[int, str], Ownership] = {}
    itinerary = (plan or {}).get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return out
    for index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        day = raw_day if isinstance(raw_day, int) and raw_day > 0 else index + 1
        stops = entry.get("stops")
        for stop in stops if isinstance(stops, list) else []:
            name = _name(stop)
            if not name:
                continue
            out[(day, name)] = stop_ownership(
                stop,
                confirmed_places=confirmed_places,
                overridden_decisions=overridden_decisions,
            )
    return out


def pinned_stops(
    plan: dict[str, Any] | None,
    *,
    confirmed_places: set[str] | frozenset[str] = frozenset(),
    overridden_decisions: set[str] | frozenset[str] = frozenset(),
) -> dict[tuple[int, str], Ownership]:
    """The stops a rebalance must leave exactly where they are."""
    return {
        key: owned
        for key, owned in trip_ownership(
            plan,
            confirmed_places=confirmed_places,
            overridden_decisions=overridden_decisions,
        ).items()
        if owned.pinned
    }


def free_ratio(plan: dict[str, Any] | None, **kwargs: Any) -> float:
    """Share of stops the planner may still move, for deciding how much to say."""
    everything = trip_ownership(plan, **kwargs)
    if not everything:
        return 0.0
    free = sum(1 for owned in everything.values() if not owned.pinned)
    return free / len(everything)
