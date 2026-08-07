"""How much a day actually costs the people taking it.

This is the second authority, and deliberately the weaker one. ``trip_guard``
decides what is possible; nothing here may refuse a change. What it may do is
rank the options the guard already permitted, and — rarely — say what a day cost.

    The invariant may block but never speaks in numbers.
    The score may speak but never blocks.

Two constraints shape the whole module.

*No composite ever reaches the owner.* Not a score, not a percentage, not a bar
or a rating. Every sentence produced here names a quantity that can be checked
against the itinerary: kilometres, hours, a start time. The vector below is an
engine internal.

*Only measured facts are used.* Minutes, distances between cached coordinates,
clock times, and party composition. Terrain, crowds and review sentiment would
all sharpen this, and all of them would also let a wrong guess speak with
confidence. The model degrades to less insightful, never to wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tripplanner.tools.trip_common import (
    _coords_from_summary,
    _fmt_hhmm,
    _haversine_km,
    _stop_kind,
    _stop_name,
    _summary_for_place,
)
from tripplanner.tools.trip_guard import (
    _duration_of,
    _time_of,
    days_of,
    travel_min,
)

CURRENCIES = ("physical", "transit", "logistical", "circadian")

CURRENCY_LABEL = {
    "physical": "on your feet",
    "transit": "in transit",
    "logistical": "packing up and moving on",
    "circadian": "against the clock",
}

# Every tunable lives here, so retuning the model is one edit rather than a hunt.
MODE_FACTOR = {"train": 0.7, "flight": 1.3, "bus": 1.35, "boat": 1.25, "road": 1.0}
LOCAL_HOP_FACTOR = 1.2
ACTIVE_FACTOR = 0.6
TRANSITION_COST = 12
CHECK_COST = 25
AIRPORT_COST = 45
EARLY_HOUR = 7 * 60
LATE_HOUR = 22 * 60
EARLY_FACTOR = 1.4
LATE_FACTOR = 1.2
RECOVERY = {"physical": 0.55, "transit": 0.8, "logistical": 0.95, "circadian": 0.35}
BASE_CAPACITY_MIN = 480

# A statement only earns its place when the debt is large and sustained.
DEBT_THRESHOLD = 0.25
CONSECUTIVE_HEAVY_DAYS = 2

_TRAIN_RE = re.compile(r"\b(train|rail|express|shatabdi|vande)\b", re.I)
_BUS_RE = re.compile(r"\b(bus|coach)\b", re.I)
_BOAT_RE = re.compile(r"\b(ferry|boat|cruise)\b", re.I)

Effort = dict[str, float]


def zero_effort() -> Effort:
    return {currency: 0.0 for currency in CURRENCIES}


def add_effort(left: Effort, right: Effort) -> Effort:
    return {currency: left[currency] + right[currency] for currency in CURRENCIES}


def total_effort(effort: Effort) -> float:
    return sum(effort.values())


def _mode_factor(stop: Any) -> float:
    if _stop_kind(stop) == "flight":
        return MODE_FACTOR["flight"]
    name = _stop_name(stop)
    if _TRAIN_RE.search(name):
        return MODE_FACTOR["train"]
    if _BUS_RE.search(name):
        return MODE_FACTOR["bus"]
    if _BOAT_RE.search(name):
        return MODE_FACTOR["boat"]
    return MODE_FACTOR["road"]


# --------------------------------------------------------------------------- #
# capacity                                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Capacity:
    minutes: float
    limited_by: str


def capacity_for(plan: dict[str, Any]) -> Capacity:
    """The party's daily capacity, taken as the minimum across its members.

    A party moves at the pace of its most limited member, so the average would
    be the wrong statistic and would quietly overstate what a day can hold.
    """
    preferences = plan.get("preferences_snapshot")
    family = plan.get("family")
    if not isinstance(family, dict) and isinstance(preferences, dict):
        family = preferences.get("family")
    family = family if isinstance(family, dict) else {}

    style = str(plan.get("trip_style") or "").strip().lower()
    pace = 1.25 if style in {"packed", "packed_sightseeing", "adventure", "adventurous"} else (
        0.8 if style in {"relaxed", "leisure"} else 1.0
    )

    members: list[tuple[float, str]] = [(1.0, "you")]
    ages = family.get("child_ages")
    for age in ages if isinstance(ages, list) else []:
        if not isinstance(age, (int, float)):
            continue
        factor = 0.6 if age <= 4 else 0.72 if age <= 8 else 0.85 if age <= 12 else 1.0
        members.append((factor, f"a {int(age)}-year-old"))
    children = family.get("children")
    if isinstance(children, int) and children > len(ages if isinstance(ages, list) else []):
        members.append((0.72, "a young child"))
    elderly = family.get("elderly")
    if isinstance(elderly, int) and elderly > 0:
        members.append((0.8, "an older traveller"))

    factor, who = min(members, key=lambda member: member[0])
    return Capacity(BASE_CAPACITY_MIN * factor * pace, who)


# --------------------------------------------------------------------------- #
# per-day effort                                                                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DayEffort:
    day: int
    effort: Effort
    total: float
    transit_min: int
    route_km: float
    first_start: int | None
    last_end: int | None


def day_efforts(plan: dict[str, Any]) -> list[DayEffort]:
    destination = str(plan.get("destination") or "")
    out: list[DayEffort] = []

    for day, _entry, stops in days_of(plan):
        effort = zero_effort()
        transit = 0
        route_km = 0.0
        timed = sorted(
            ((stop, at) for stop in stops if (at := _time_of(stop)) is not None),
            key=lambda pair: pair[1],
        )

        for stop, _at in timed:
            kind = _stop_kind(stop)
            duration = _duration_of(stop)
            if kind in {"flight", "transport"}:
                effort["transit"] += duration * _mode_factor(stop)
                effort["logistical"] += AIRPORT_COST if kind == "flight" else TRANSITION_COST
                transit += duration
            elif kind == "hotel":
                effort["logistical"] += CHECK_COST
            else:
                effort["physical"] += duration * ACTIVE_FACTOR

        located = [
            (stop, coords)
            for stop, _at in timed
            if _stop_kind(stop) not in {"flight", "transport"}
            and (coords := _coords_from_summary(_summary_for_place(_stop_name(stop), destination)))
        ]
        for index in range(len(located) - 1):
            here = located[index][1]
            there = located[index + 1][1]
            route_km += _haversine_km(here, there)
            hop = travel_min(here, there)
            effort["transit"] += hop * LOCAL_HOP_FACTOR
            effort["logistical"] += TRANSITION_COST
            transit += hop

        first_start = timed[0][1] if timed else None
        last_end = max(at + _duration_of(stop) for stop, at in timed) if timed else None
        if first_start is not None and first_start < EARLY_HOUR:
            effort["circadian"] += (EARLY_HOUR - first_start) * EARLY_FACTOR
        if last_end is not None and last_end > LATE_HOUR:
            effort["circadian"] += (last_end - LATE_HOUR) * LATE_FACTOR

        out.append(
            DayEffort(day, effort, total_effort(effort), transit, route_km, first_start, last_end)
        )
    return out


# --------------------------------------------------------------------------- #
# the reserve                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReserveDay:
    day: int
    spend: Effort
    carried_in: Effort
    load: float
    capacity: float
    over_capacity: bool
    dominant_debt: str


def reserve_curve(plan: dict[str, Any]) -> list[ReserveDay]:
    """Fatigue as a stock rather than a flow.

    Per-day scoring rates three consecutive heavy days better than one brutal day
    with a light one either side, which is backwards. Each night repays part of
    the debt, unevenly by currency, and what is left starts the next day.
    """
    capacity = capacity_for(plan)
    carried = zero_effort()
    curve: list[ReserveDay] = []

    for entry in day_efforts(plan):
        spend = entry.effort
        load = total_effort(spend) + total_effort(carried)
        strain = max(0.0, load - capacity.minutes)
        combined = {c: spend[c] + carried[c] for c in CURRENCIES}
        dominant = max(CURRENCIES, key=lambda c: combined[c])
        curve.append(
            ReserveDay(
                entry.day,
                dict(spend),
                dict(carried),
                load,
                capacity.minutes,
                load > capacity.minutes,
                dominant,
            )
        )
        if load <= 0:
            carried = zero_effort()
            continue
        carried = {
            c: strain * (combined[c] / load) * (1 - RECOVERY[c]) for c in CURRENCIES
        }
    return curve


def pacing_statement(plan: dict[str, Any]) -> dict[str, Any] | None:
    """At most one pacing observation for the whole trip, or nothing at all.

    The recovery coefficients are invented; there is no ground truth for them,
    and a compounding model gets progressively wronger. So the model informs
    every ranking but is allowed to speak only at the single worst point, and
    only when the debt is both large and sustained. Silence is the default.
    """
    curve = reserve_curve(plan)
    capacity = curve[0].capacity if curve else 0.0
    if not capacity:
        return None

    worst: tuple[float, ReserveDay] | None = None
    for index, entry in enumerate(curve):
        if index < CONSECUTIVE_HEAVY_DAYS:
            continue
        recent = curve[index - CONSECUTIVE_HEAVY_DAYS:index]
        if not all(day.over_capacity for day in recent):
            continue
        debt = total_effort(entry.carried_in)
        if debt < capacity * DEBT_THRESHOLD:
            continue
        if worst is None or debt > worst[0]:
            worst = (debt, entry)

    if worst is None:
        return None

    _debt, entry = worst
    heavier = max(
        (day for day in curve if day.day < entry.day),
        key=lambda day: total_effort(day.spend),
    )
    return {
        "day": entry.day,
        "remedy_day": heavier.day,
        "statement": (
            f"Day {entry.day} arrives on the back of two full days. "
            f"{CURRENCY_LABEL[entry.dominant_debt].capitalize()} is what has built up."
        ),
        "remedy": f"A slower start on Day {heavier.day} would take the pressure off it.",
    }


# --------------------------------------------------------------------------- #
# coherence                                                                     #
# --------------------------------------------------------------------------- #


def _nearest_neighbour_km(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    remaining = points[1:]
    here = points[0]
    total = 0.0
    while remaining:
        nearest = min(remaining, key=lambda point: _haversine_km(here, point))
        total += _haversine_km(here, nearest)
        here = nearest
        remaining = [point for point in remaining if point is not nearest]
    return total


def coherence_notes(plan: dict[str, Any]) -> list[str]:
    """Things that read as wrong without being infeasible.

    Only the checks that measured data can answer honestly are here. Time-of-day
    fit and under-timed visits need place metadata and review evidence this
    module does not have, so it says nothing about them rather than guessing.
    """
    destination = str(plan.get("destination") or "")
    notes: list[str] = []
    previous_end: tuple[int, int] | None = None

    for day, _entry, stops in days_of(plan):
        timed = sorted(
            ((stop, at) for stop in stops if (at := _time_of(stop)) is not None),
            key=lambda pair: pair[1],
        )
        if not timed:
            continue
        first = timed[0][1]
        last = max(at + _duration_of(stop) for stop, at in timed)

        # C2 — a day that runs through the middle of the day with nowhere to eat.
        if first <= 11 * 60 + 30 and last >= 15 * 60:
            has_meal = any(
                _stop_kind(stop) == "meal" and 11 * 60 + 30 <= at <= 15 * 60 for stop, at in timed
            )
            longest_gap = 0
            for index in range(len(timed) - 1):
                gap = timed[index + 1][1] - (timed[index][1] + _duration_of(timed[index][0]))
                if 11 * 60 + 30 <= timed[index + 1][1] <= 15 * 60:
                    longest_gap = max(longest_gap, gap)
            if not has_meal and longest_gap < 45:
                notes.append(f"Day {day} runs straight through lunch with nowhere to eat.")

        # C4 — two days that are each fine and impossible as a pair.
        if previous_end is not None and previous_end[1] > LATE_HOUR and first < 8 * 60:
            notes.append(
                f"Day {previous_end[0]} ends at {_fmt_hhmm(previous_end[1] % 1440)} and "
                f"Day {day} starts at {_fmt_hhmm(first)}."
            )
        previous_end = (day, last)

        # C3 — crossing the city and coming back reads worse than the kilometres suggest.
        points = [
            coords
            for stop, _at in timed
            if _stop_kind(stop) not in {"flight", "transport"}
            and (coords := _coords_from_summary(_summary_for_place(_stop_name(stop), destination)))
        ]
        if len(points) >= 3:
            planned = sum(_haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))
            best = _nearest_neighbour_km(points)
            if planned > best * 1.6 and planned - best > 8:
                notes.append(
                    f"Day {day} doubles back across the city; about "
                    f"{round(planned - best)} km of the driving is backtracking."
                )
    return notes


# --------------------------------------------------------------------------- #
# saying it in words                                                            #
# --------------------------------------------------------------------------- #


def describe_day(plan: dict[str, Any], day: int) -> str:
    """A day in measured quantities. Never a score, a bar or a rating."""
    entries = day_efforts(plan)
    entry = next((item for item in entries if item.day == day), None)
    if entry is None:
        return ""
    parts: list[str] = []
    if entry.route_km >= 1:
        parts.append(f"{entry.route_km:.0f} km of driving between stops")
    if entry.transit_min >= 60:
        parts.append(f"{entry.transit_min / 60:.0f}h in transit")
    if entry.first_start is not None and entry.first_start < EARLY_HOUR:
        parts.append(f"a {_fmt_hhmm(entry.first_start)} start")
    if entry.last_end is not None and entry.last_end > LATE_HOUR:
        parts.append(f"a finish after {_fmt_hhmm(entry.last_end % 1440)}")
    if not parts:
        return ""
    fullest = max(entries, key=lambda item: item.total)
    tail = " — the fullest day of the trip." if fullest.day == day and len(entries) > 1 else "."
    return f"Day {day}: {', '.join(parts)}{tail}"


def cost_of_change(before: dict[str, Any], after: dict[str, Any]) -> str:
    """What a permitted change cost, stated as a difference rather than a verdict.

    Returns an empty string when the change is neutral or better, which is the
    common case and the reason this layer is not friction.
    """
    capacity = capacity_for(after).minutes
    left = {entry.day: entry for entry in day_efforts(before)}
    sentences: list[str] = []
    for entry in day_efforts(after):
        previous = left.get(entry.day)
        if previous is None:
            continue
        deltas = {c: entry.effort[c] - previous.effort[c] for c in CURRENCIES}
        currency = max(CURRENCIES, key=lambda c: deltas[c])
        if deltas[currency] <= capacity * 0.15:
            continue
        sentences.append(
            f"Day {entry.day} gains about {round(deltas[currency] / 60)}h "
            f"{CURRENCY_LABEL[currency]}."
        )
    return " ".join(sentences)
