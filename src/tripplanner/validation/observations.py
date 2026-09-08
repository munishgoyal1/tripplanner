"""What the planner actually does, across every trip we have.

Rules say what is broken. They cannot say that no trip ever chose a train, or
that arrival days are empty, because neither is a defect. Those are the gaps a
feature comes from, so they are counted here and never reported as findings.

Nothing in this module judges. It describes, and leaves the judgement to the
person reading it.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from tripplanner.validation.corpus import CorpusRecord

_PLACE_KINDS = frozenset({"attraction", "meal", "restaurant"})
_MEAL_KINDS = frozenset({"meal", "restaurant"})
_TRANSPORT_KINDS = frozenset({"flight", "transport"})


@dataclass(frozen=True)
class Observation:
    label: str
    value: str
    detail: str = ""


def _stops(day: Any) -> list[dict[str, Any]]:
    if not isinstance(day, dict):
        return []
    return [stop for stop in (day.get("stops") or []) if isinstance(stop, dict)]


def _kind(stop: dict[str, Any]) -> str:
    return str(stop.get("kind") or "").strip().lower()


def _days(record: CorpusRecord) -> list[dict[str, Any]]:
    itinerary = record.plan.get("day_wise_itinerary")
    return [day for day in (itinerary or []) if isinstance(day, dict)]


def _percentage(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):.0f}%" if whole else "n/a"


def observe(records: list[CorpusRecord]) -> list[Observation]:
    day_count = 0
    place_counts: list[int] = []
    days_with_meal = 0
    days_with_nothing = 0
    arrival_days_thin = 0
    arrival_days = 0
    modes: dict[str, int] = {}
    stays_per_trip: list[int] = []
    durations: list[int] = []
    scoped: dict[str, int] = {}

    for record in records:
        days = _days(record)
        if not days:
            continue
        durations.append(len(days))
        scope = str(record.plan.get("travel_scope") or "unset")
        scoped[scope] = scoped.get(scope, 0) + 1
        stays: set[str] = set()
        for index, day in enumerate(days):
            day_count += 1
            stops = _stops(day)
            places = [stop for stop in stops if _kind(stop) in _PLACE_KINDS]
            place_counts.append(len(places))
            if any(_kind(stop) in _MEAL_KINDS for stop in stops):
                days_with_meal += 1
            if not places:
                days_with_nothing += 1
            for stop in stops:
                if _kind(stop) == "hotel" and str(stop.get("name") or ""):
                    stays.add(str(stop["name"]).strip().lower())
                if _kind(stop) in _TRANSPORT_KINDS:
                    mode = _leg_mode(stop)
                    modes[mode] = modes.get(mode, 0) + 1
            # The arrival day is the one the traveller reaches the place on; a
            # day that is only a journey is a day of the trip nobody planned.
            if index == 0 and any(_kind(stop) in _TRANSPORT_KINDS for stop in stops):
                arrival_days += 1
                if len(places) < 2:
                    arrival_days_thin += 1
        stays_per_trip.append(len(stays))

    observations = [
        Observation("Trips", str(len(records)), f"{day_count} planned days"),
        Observation(
            "Trip length",
            f"{median(durations):.0f} days" if durations else "n/a",
            f"shortest {min(durations)}, longest {max(durations)}" if durations else "",
        ),
        Observation(
            "Places per day",
            f"{median(place_counts):.0f}" if place_counts else "n/a",
            f"busiest day holds {max(place_counts)}" if place_counts else "",
        ),
        Observation(
            "Days with a named meal",
            _percentage(days_with_meal, day_count),
            f"{day_count - days_with_meal} days name nowhere to eat",
        ),
        Observation(
            "Days with nothing planned",
            _percentage(days_with_nothing, day_count),
            "beyond the stay and any journey",
        ),
        Observation(
            "Arrival days with under two places",
            _percentage(arrival_days_thin, arrival_days),
            f"of {arrival_days} arrival days",
        ),
        Observation(
            "Stays per trip",
            f"{median(stays_per_trip):.0f}" if stays_per_trip else "n/a",
            "distinct hotels named across the trip",
        ),
        Observation(
            "How the journey is made",
            ", ".join(f"{mode} {count}" for mode, count in sorted(modes.items())) or "none",
            "legs by mode across every trip",
        ),
        Observation(
            "Travel scope",
            ", ".join(f"{scope} {count}" for scope, count in sorted(scoped.items())),
            "trips that say how the traveller gets there",
        ),
    ]
    return observations


def _leg_mode(stop: dict[str, Any]) -> str:
    from tripplanner.web.transport import _intercity_transfer_mode

    mode = _intercity_transfer_mode(str(stop.get("name") or ""), _kind(stop))
    return mode or "unnamed"
