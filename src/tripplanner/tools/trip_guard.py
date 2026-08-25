"""Deterministic invariants and guarded placement for a trip plan.

The model reads intent and writes prose. It must never be the only thing standing
between an intent and the persisted trip. Everything in this module is arithmetic
over a plan that already carries days, times, durations, cities and cached
coordinates, so the same guarantees hold whichever channel asked for the change.

Two rules govern the split between this module and ``trip_effort``:

    The invariant may block but never speaks in numbers.
    The score may speak but never blocks.

An invariant that cannot be evaluated stays silent. Missing coordinates, missing
times and missing opening hours degrade the guard to *less thorough*, never to
wrong and never to blocked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from tripplanner import place_facts
from tripplanner.tools.trip_common import (
    _HOTEL_PLACEHOLDER_RE,
    _coords_from_summary,
    _fmt_hhmm,
    _haversine_km,
    _parse_hhmm,
    _stop_kind,
    _stop_name,
    _summary_for_place,
    unnamed_lodging,
)

DAY_START_MIN = 8 * 60 + 30
DAY_END_MIN = 21 * 60 + 30
PRE_DEPARTURE_BUFFER_MIN = 120
TURNAROUND_MIN = 10
#: Slack a stop that can simply be reached a little late may absorb. A stop with
#: a time someone else owns -- a ticket, a booking, a departure -- gets none.
FEASIBILITY_GRACE_MIN = 10
ROAD_SPEED_KMH = 42.0
DEFAULT_VISIT_MIN = 90
DEFAULT_MEAL_MIN = 60
DEFAULT_LEG_MIN = 120
DEFAULT_HOTEL_MIN = 45
#: Far enough apart that no ordinary day trip explains it without a named journey.
CONTINUITY_KM = 150.0

_TRANSPORT_KINDS = {"flight", "transport"}
_CITY_ALIASES = {"bengaluru": "bangalore", "mysuru": "mysore", "mumbai": "bombay"}
_TERMINAL_RE = re.compile(
    r"\bairports?\b|\brailway station\b|\btrain station\b|\bbus (?:stand|station)\b", re.I
)
_OVERNIGHT_RE = re.compile(r"\b(?:overnight|night train|night bus|sleeper)\b", re.I)

INVARIANTS: tuple[tuple[str, str, str], ...] = (
    (
        "I1",
        "Trip envelope",
        "Nothing in the destination may be scheduled before you arrive or after you leave.",
    ),
    ("I2", "Presence", "A stop must sit on the side of a journey where you are actually present."),
    ("I3", "Opening hours", "A visit must start and end while the place is open."),
    ("I4", "Temporal feasibility", "Visit plus travel must fit before the next stop starts."),
    ("I5", "Departure buffer", "At least two hours must stay free before an onward journey."),
    ("I6", "Stay coverage", "Every night away from home has a stay."),
    ("I7", "Return coverage", "An outbound leg keeps its matching return leg."),
    ("I8", "Blast radius", "An operation may only change the entities it declared."),
    ("I9", "Continuity", "Every move between stops must be explained by a journey."),
    (
        "I10",
        "Guard coverage",
        "A plan must say where the trip starts, or the envelope invariants cannot run.",
    ),
    ("I11", "Closed day", "A visit must fall on a day the place is actually open."),
    (
        "I12",
        "Permanently closed",
        "A place reported as shut down for good must not be planned at all.",
    ),
    ("I13", "Duplicate visit", "The same sight must not be planned on two different days."),
)

#: A trip the traveller will reach on their own. Named by the user, never
#: assumed, because the alternative is inventing a home city they never gave.
DESTINATION_ONLY = "destination_only"
KNOWN_FACT_CODES = frozenset({"I3", "I11", "I12", "I13"})


def travel_scope(plan: dict[str, Any]) -> str:
    return str(plan.get("travel_scope") or "").strip().lower()


def plans_own_arrival(plan: dict[str, Any]) -> bool:
    """True when the traveller has said they are arranging the journey there."""
    return travel_scope(plan) == DESTINATION_ONLY


@dataclass(frozen=True)
class Violation:
    code: str
    rule: str
    message: str
    day: int | None = None
    stop: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "rule": self.rule,
            "message": self.message,
            "day": self.day,
            "stop": self.stop,
        }


@dataclass(frozen=True)
class Change:
    verb: str
    day: int
    name: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"verb": self.verb, "day": self.day, "name": self.name, "detail": self.detail}

    def sentence(self) -> str:
        return f"{self.verb.capitalize()} {self.name} on Day {self.day} ({self.detail})."


@dataclass(frozen=True)
class Placement:
    day: int
    index: int
    time: str
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Rejection:
    day: int
    window: str
    code: str
    message: str


# --------------------------------------------------------------------------- #
# plan reading                                                                  #
# --------------------------------------------------------------------------- #


def _normalize_city(value: str, *, first_part: bool = False) -> str:
    text = re.split(r"[,;/]", value, maxsplit=1)[0] if first_part else value
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    for alias, canonical in _CITY_ALIASES.items():
        text = re.sub(rf"\b{re.escape(alias)}\b", canonical, text)
    return text


def _is_journey_between(stop: Any, source: str, target: str) -> bool:
    """True when a transport stop reads as a journey from ``source`` to ``target``."""
    if _stop_kind(stop) not in _TRANSPORT_KINDS:
        return False
    name = _normalize_city(_stop_name(stop))
    src = _normalize_city(source, first_part=True)
    dst = _normalize_city(target, first_part=True)
    if not name or not src or not dst:
        return False
    src_at = name.find(src)
    if src_at < 0:
        return False
    return name.find(dst, src_at + len(src)) > src_at


_MODE_PREFIX_RE = re.compile(
    r"^\s*(?:non-?stop\s+|direct\s+)?(?:flight|train|bus|drive|transfer|ferry|taxi|cab|car)\b[\s:—–-]*",
    re.I,
)
_JOURNEY_SPLIT_RE = re.compile(r"→|-+>|—>|\bto\b", re.I)


def _journey_endpoints(stop: Any) -> tuple[str, str] | None:
    """Normalized ``(source, target)`` for a transport stop that names both ends."""
    if _stop_kind(stop) not in _TRANSPORT_KINDS:
        return None
    parts = _JOURNEY_SPLIT_RE.split(_stop_name(stop), maxsplit=1)
    if len(parts) != 2:
        return None
    source = _normalize_city(_MODE_PREFIX_RE.sub("", parts[0]))
    target = _normalize_city(parts[1], first_part=True)
    return (source, target) if source and target else None


def _home_bound_leg(stop: Any, home: str) -> tuple[bool, bool]:
    """``(leaves_home, arrives_home)`` for one transport stop.

    A regional destination names its real cities, so "Flight Bengaluru → Jaipur"
    never contains "Rajasthan". Anchoring on the traveller's home city instead
    keeps the envelope — and every invariant that depends on it — working for a
    multi-city trip.
    """
    endpoints = _journey_endpoints(stop)
    if endpoints is None or not home:
        return (False, False)
    source, target = endpoints
    from_home = home in source
    to_home = home in target
    return (from_home and not to_home, to_home and not from_home)


def leg_touches_home(stop: Any, origin: str) -> tuple[bool, bool]:
    """``(leaves_home, arrives_home)`` for one stop, given the trip's origin."""
    return _home_bound_leg(stop, _normalize_city(origin, first_part=True))


def _default_duration(kind: str) -> int:
    if kind in _TRANSPORT_KINDS:
        return DEFAULT_LEG_MIN
    if kind == "hotel":
        return DEFAULT_HOTEL_MIN
    if kind == "meal":
        return DEFAULT_MEAL_MIN
    return DEFAULT_VISIT_MIN


def _duration_of(stop: Any) -> int:
    kind = _stop_kind(stop)
    raw = stop.get("duration_min") if isinstance(stop, dict) else None
    if isinstance(raw, (int, float)) and raw > 0:
        return int(raw)
    return _default_duration(kind)


def _is_home_endpoint(stop: Any, origin: str) -> bool:
    """True for a non-place row that explicitly marks arrival back at the origin."""
    if _stop_kind(stop) in _PLACE_KINDS | {"hotel"}:
        return False
    home = _normalize_city(origin, first_part=True)
    name = _normalize_city(_stop_name(stop))
    return bool(home and name and (name == home or re.search(rf"\b{re.escape(home)}\b", name)))


def _time_of(stop: Any) -> int | None:
    if not isinstance(stop, dict):
        return None
    return _parse_hhmm(str(stop.get("time") or ""))


def _arrival_of(stop: Any) -> int | None:
    if not isinstance(stop, dict):
        return None
    return _parse_hhmm(str(stop.get("arrival_time") or ""))


def days_of(plan: dict[str, Any]) -> list[tuple[int, dict[str, Any], list[Any]]]:
    """Return ``(day_number, day_entry, stops)`` for every structured day, in order."""
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return []
    out: list[tuple[int, dict[str, Any], list[Any]]] = []
    for index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        number = raw_day if isinstance(raw_day, int) and raw_day > 0 else index + 1
        stops = entry.get("stops")
        out.append((number, entry, stops if isinstance(stops, list) else []))
    return out


def _abs(day: int, minute: int) -> int:
    return (day - 1) * 1440 + minute


@dataclass(frozen=True)
class Envelope:
    """The only interval in which destination plans may exist."""

    arrival_day: int | None
    arrival_end: int | None
    arrival_name: str
    departure_day: int | None
    departure_start: int | None
    departure_name: str

    @property
    def bounded_start(self) -> bool:
        return self.arrival_end is not None

    @property
    def bounded_end(self) -> bool:
        return self.departure_start is not None


def envelope(plan: dict[str, Any]) -> Envelope:
    origin = str(plan.get("origin") or "").strip()
    destination = str(plan.get("destination") or "").strip()
    arrival_day = arrival_end = departure_day = departure_start = None
    arrival_name = departure_name = ""
    if not origin or not destination:
        return Envelope(None, None, "", None, None, "")

    home = _normalize_city(origin, first_part=True)

    for day, _entry, stops in days_of(plan):
        for stop in stops:
            leaves_home, arrives_home = _home_bound_leg(stop, home)
            if not leaves_home and not arrives_home:
                leaves_home = _is_journey_between(stop, origin, destination)
                arrives_home = _is_journey_between(stop, destination, origin)
            if leaves_home and arrival_day is None:
                start = _time_of(stop)
                arrival_day = day
                arrival_name = _stop_name(stop)
                arrival = _arrival_of(stop)
                if arrival is not None:
                    arrival_end = _abs(day, arrival)
                    if start is not None and arrival < start:
                        arrival_end += 1440
                elif start is not None:
                    arrival_end = _abs(day, start + _duration_of(stop))
            if arrives_home:
                start = _time_of(stop)
                departure_day = day
                departure_name = _stop_name(stop)
                departure_start = _abs(day, start) if start is not None else None

    return Envelope(
        arrival_day, arrival_end, arrival_name, departure_day, departure_start, departure_name
    )


# --------------------------------------------------------------------------- #
# opening hours (best effort)                                                   #
# --------------------------------------------------------------------------- #

_PLACE_KINDS = {"attraction", "meal"}


def facts_for(name: str, destination: str) -> place_facts.PlaceFacts:
    """Everything known about one place, read through the single fact boundary.

    Facts belonging to a different business of a similar name are worse than no
    facts, so a lookup that answered about somewhere else stays silent.
    """
    if not name:
        return place_facts.UNKNOWN
    summary = _summary_for_place(name, destination)
    if not place_facts.names_match(name, str(summary.get("name") or "")):
        return place_facts.UNKNOWN
    return place_facts.facts_from_summary(summary)


def day_dates(plan: dict[str, Any]) -> dict[int, str]:
    """Calendar date per day number, from the entry itself or the start date.

    A weekday closure is only checkable against a real date, so a plan that
    never wrote one simply keeps those invariants silent.
    """
    start: date | None = None
    raw_start = str(plan.get("departure_date") or plan.get("start_date") or "").strip()
    if raw_start:
        try:
            start = date.fromisoformat(raw_start)
        except ValueError:
            start = None

    out: dict[int, str] = {}
    for day, entry, _stops in days_of(plan):
        text = str(entry.get("date") or "").strip()
        if place_facts.weekday_of(text) is not None:
            out[day] = text
        elif start is not None:
            out[day] = (start + timedelta(days=day - 1)).isoformat()
    return out


# --------------------------------------------------------------------------- #
# travel                                                                        #
# --------------------------------------------------------------------------- #


def _coords(stop: Any, destination: str) -> tuple[float, float] | None:
    name = _stop_name(stop)
    if not name:
        return None
    summary = _summary_for_place(name, destination)
    if not place_facts.names_match(name, str(summary.get("name") or "")):
        return None
    return _coords_from_summary(summary)


def travel_min(a: tuple[float, float], b: tuple[float, float]) -> int:
    return max(TURNAROUND_MIN, round((_haversine_km(a, b) / ROAD_SPEED_KMH) * 60) + TURNAROUND_MIN)


# --------------------------------------------------------------------------- #
# validation                                                                    #
# --------------------------------------------------------------------------- #


def validate_plan(plan: dict[str, Any]) -> list[Violation]:
    """Every invariant this plan can be checked against, in code order."""
    out: list[Violation] = []
    destination = str(plan.get("destination") or "")
    env = envelope(plan)
    structured = days_of(plan)

    out.extend(_envelope_violations(structured, env, str(plan.get("origin") or "")))
    out.extend(_presence_violations(structured, env))
    out.extend(_hours_violations(structured, destination, day_dates(plan)))
    out.extend(_availability_violations(structured, destination))
    out.extend(_repeat_visit_violations(structured))
    out.extend(_feasibility_violations(structured, destination))
    out.extend(_stay_violations(plan, structured, env))
    out.extend(_return_violations(plan, env))
    out.extend(_continuity_violations(structured, destination))
    out.extend(_coverage_violations(plan))
    return out


def _envelope_violations(
    structured: list[tuple[int, dict[str, Any], list[Any]]], env: Envelope, origin: str
) -> list[Violation]:
    out: list[Violation] = []
    for day, _entry, stops in structured:
        for stop in stops:
            if _stop_kind(stop) in _TRANSPORT_KINDS or _is_home_endpoint(stop, origin):
                continue
            start = _time_of(stop)
            if start is None:
                continue
            begins = _abs(day, start)
            ends = begins + _duration_of(stop)
            name = _stop_name(stop) or "An untitled stop"
            if env.arrival_end is not None and begins < env.arrival_end:
                out.append(
                    Violation(
                        "I1",
                        "Trip envelope",
                        f"{name} starts at {_fmt_hhmm(start)} on Day {day}, before "
                        f"{env.arrival_name or 'your arrival'} gets you there.",
                        day,
                        name,
                    )
                )
            if env.departure_start is not None and ends > env.departure_start:
                out.append(
                    Violation(
                        "I1",
                        "Trip envelope",
                        f"{name} runs to {_fmt_hhmm(start + _duration_of(stop))} on Day {day}, "
                        f"after {env.departure_name or 'your departure'} has left.",
                        day,
                        name,
                    )
                )
    return out


def _presence_violations(
    structured: list[tuple[int, dict[str, Any], list[Any]]], env: Envelope
) -> list[Violation]:
    """Ordering-based presence, for the times a leg carries no clock time."""
    out: list[Violation] = []
    for day, _entry, stops in structured:
        if env.departure_day == day:
            leg_at = next(
                (
                    index
                    for index, stop in enumerate(stops)
                    if _stop_name(stop) == env.departure_name
                ),
                None,
            )
            if leg_at is not None:
                for stop in stops[leg_at + 1:]:
                    if _stop_kind(stop) in _TRANSPORT_KINDS or _stop_kind(stop) == "hotel":
                        continue
                    name = _stop_name(stop) or "An untitled stop"
                    out.append(
                        Violation(
                            "I2",
                            "Presence",
                            f"{name} is listed after {env.departure_name} on Day {day}, "
                            "when you have already left the city.",
                            day,
                            name,
                        )
                    )
        if env.arrival_day == day:
            leg_at = next(
                (index for index, stop in enumerate(stops) if _stop_name(stop) == env.arrival_name),
                None,
            )
            if leg_at is not None:
                for stop in stops[:leg_at]:
                    if _stop_kind(stop) in _TRANSPORT_KINDS:
                        continue
                    name = _stop_name(stop) or "An untitled stop"
                    out.append(
                        Violation(
                            "I2",
                            "Presence",
                            f"{name} is listed before {env.arrival_name} on Day {day}, "
                            "when you have not arrived yet.",
                            day,
                            name,
                        )
                    )
    return out


def _hours_violations(
    structured: list[tuple[int, dict[str, Any], list[Any]]],
    destination: str,
    dates: dict[int, str],
) -> list[Violation]:
    """I11 then I3: the wrong day is a different mistake from the wrong hour."""
    out: list[Violation] = []
    for day, _entry, stops in structured:
        day_iso = dates.get(day, "")
        for stop in stops:
            if _stop_kind(stop) not in _PLACE_KINDS:
                continue
            name = _stop_name(stop)
            if not name:
                continue
            facts = facts_for(name, destination)
            if facts.closed_on(day_iso):
                weekday = place_facts.weekday_of(day_iso)
                named = (
                    place_facts.WEEKDAY_NAMES[weekday] + "s"
                    if weekday is not None
                    else "that day"
                )
                out.append(
                    Violation(
                        "I11",
                        "Closed day",
                        f"{name} is closed on {named}, and Day {day} is one. "
                        "Move it to a day it is open.",
                        day,
                        name,
                    )
                )
                continue
            start = _time_of(stop)
            if start is None:
                continue
            ends = start + _duration_of(stop)
            if facts.fits(day_iso, start, ends) is not False:
                continue
            out.append(
                Violation(
                    "I3",
                    "Opening hours",
                    f"{name} is open {facts.window_text(day_iso)}; the Day {day} visit runs "
                    f"{_fmt_hhmm(start)}–{_fmt_hhmm(ends % 1440)}.",
                    day,
                    name,
                )
            )
    return out


def _availability_violations(
    structured: list[tuple[int, dict[str, Any], list[Any]]], destination: str
) -> list[Violation]:
    """I12. A place the source says has shut down is not a scheduling problem."""
    out: list[Violation] = []
    for day, _entry, stops in structured:
        for stop in stops:
            if _stop_kind(stop) in _TRANSPORT_KINDS:
                continue
            name = _stop_name(stop)
            if not name or not facts_for(name, destination).unavailable:
                continue
            out.append(
                Violation(
                    "I12",
                    "Availability",
                    f"{name} is reported closed for business; Day {day} plans it anyway. "
                    "Replace it with somewhere still operating.",
                    day,
                    name,
                )
            )
    return out


def _repeat_visit_violations(
    structured: list[tuple[int, dict[str, Any], list[Any]]],
) -> list[Violation]:
    """I13. Two days at the same sight is almost always a replan that half-ran."""
    out: list[Violation] = []
    first_day: dict[str, int] = {}
    for day, _entry, stops in structured:
        for name in {
            _stop_name(stop) for stop in stops if _stop_kind(stop) == "attraction"
        }:
            if not name:
                continue
            seen = first_day.setdefault(name.casefold(), day)
            if seen == day:
                continue
            out.append(
                Violation(
                    "I13",
                    "Repeat visit",
                    f"{name} is scheduled on Day {seen} and again on Day {day}. "
                    "Keep the better one and give the other day its own place.",
                    day,
                    name,
                )
            )
    return out


def _has_a_time_of_its_own(stop: Any) -> bool:
    """True when someone else owns this stop's clock and will not wait.

    A booked table or a timed entry is a promise to be somewhere at an hour you
    did not choose. Arriving late for it is not a rounding error, so it gets no
    slack at all, while an ordinary sight can simply be reached a little later.
    """
    if not isinstance(stop, dict):
        return False
    if stop.get("booked") or stop.get("booking_ref") or stop.get("ticket_url"):
        return True
    return bool(
        str(stop.get("entry_time") or stop.get("timed_entry") or "").strip()
    )


def _feasibility_violations(
    structured: list[tuple[int, dict[str, Any], list[Any]]], destination: str
) -> list[Violation]:
    out: list[Violation] = []
    for day, _entry, stops in structured:
        timed = [(stop, _time_of(stop)) for stop in stops]
        timed = [(stop, at) for stop, at in timed if at is not None]
        timed.sort(key=lambda pair: pair[1])
        for index in range(len(timed) - 1):
            current, current_at = timed[index]
            following, following_at = timed[index + 1]
            ends = current_at + _duration_of(current)
            if _stop_kind(following) in _TRANSPORT_KINDS:
                # Two hours is an airport, not a car. Asking for check-in time
                # before a drive turns a real rule into background noise.
                buffer_min = (
                    PRE_DEPARTURE_BUFFER_MIN
                    if _stop_kind(following) == "flight"
                    else TURNAROUND_MIN
                )
                needed = ends + buffer_min
                if needed > following_at:
                    out.append(
                        Violation(
                            "I5",
                            "Departure buffer",
                            f"{_stop_name(current)} leaves only {following_at - ends} minutes "
                            f"before {_stop_name(following)} on Day {day}; "
                            f"{buffer_min} are required.",
                            day,
                            _stop_name(following),
                        )
                    )
                continue
            here = _coords(current, destination)
            there = _coords(following, destination)
            if not here or not there:
                continue
            needed = ends + travel_min(here, there)
            grace = 0 if _has_a_time_of_its_own(following) else FEASIBILITY_GRACE_MIN
            if needed > following_at + grace:
                out.append(
                    Violation(
                        "I4",
                        "Temporal feasibility",
                        f"{_stop_name(current)} cannot reach {_stop_name(following)} in time on "
                        f"Day {day}; short by {needed - following_at} minutes.",
                        day,
                        _stop_name(following),
                    )
                )
    return out


def _overnight_journey(stop: Any) -> bool:
    if _stop_kind(stop) not in _TRANSPORT_KINDS:
        return False
    if _OVERNIGHT_RE.search(_stop_name(stop)):
        return True
    start = _time_of(stop)
    return start is not None and start + _duration_of(stop) >= 24 * 60


def _stay_locations(plan: dict[str, Any]) -> set[str]:
    locations: set[str] = set()
    destination = str(plan.get("destination") or "").strip()
    if destination:
        locations.add(destination.lower())
        locations.update(
            part.strip().lower()
            for part in re.split(r"[,&/()]| and ", destination)
            if part.strip()
        )
    for _day, entry, stops in days_of(plan):
        for source in [entry, *[stop for stop in stops if isinstance(stop, dict)]]:
            for key in ("destination", "city", "location"):
                value = str(source.get(key) or "").strip().lower()
                if value:
                    locations.add(value)
    return locations


def _required_stay_days(
    plan: dict[str, Any],
    structured: list[tuple[int, dict[str, Any], list[Any]]],
    env: Envelope,
) -> list[int]:
    if not structured:
        return []
    if env.arrival_day is not None and env.departure_day is not None:
        candidates = [
            day for day, _entry, _stops in structured
            if env.arrival_day <= day < env.departure_day
        ]
    elif plans_own_arrival(plan):
        candidates = [day for day, _entry, _stops in structured[:-1]]
    else:
        return []
    overnight_days = {
        day for day, _entry, stops in structured if any(_overnight_journey(stop) for stop in stops)
    }
    return [day for day in candidates if day not in overnight_days]


def _stay_violations(
    plan: dict[str, Any],
    structured: list[tuple[int, dict[str, Any], list[Any]]],
    env: Envelope,
) -> list[Violation]:
    required = set(_required_stay_days(plan, structured, env))
    if not required:
        return []
    cities = _stay_locations(plan)
    out: list[Violation] = []
    for day, _entry, stops in structured:
        if day not in required:
            continue
        stays = [stop for stop in stops if _stop_kind(stop) == "hotel"]
        concrete = [
            stop
            for stop in stays
            if not _HOTEL_PLACEHOLDER_RE.search(_stop_name(stop))
            and not unnamed_lodging(_stop_name(stop), cities)
        ]
        if concrete:
            continue
        if stays:
            name = _stop_name(stays[0]) or "unnamed hotel"
            out.append(
                Violation(
                    "I6",
                    "Stay coverage",
                    f"Day {day} has no concrete, bookable stay for the night; replace {name}.",
                    day,
                    name,
                )
            )
        else:
            out.append(
                Violation(
                    "I6",
                    "Stay coverage",
                    f"Day {day} has no concrete lodging anchor for the night.",
                    day,
                )
            )
    return out


def _continuity_violations(
    structured: list[tuple[int, dict[str, Any], list[Any]]], destination: str
) -> list[Violation]:
    """I9. Every move between stops must be explained by a journey.

    The trip is one body moving through one sequence of places, so the rule is
    the same inside a day and across midnight. A named leg moves you and ends
    the chain; two terminals in a row are the leg the plan did not bother to
    name. Anything else has to stay within a day's reach of the stop before it.

    Silent unless both sides are located: a guard that guesses geography is
    worse than one that stays quiet about it.
    """
    out: list[Violation] = []
    previous: tuple[str, int, tuple[float, float], bool] | None = None
    for day, _entry, stops in structured:
        for stop in stops:
            name = _stop_name(stop) or "An untitled stop"
            terminal = bool(_TERMINAL_RE.search(name))
            if _stop_kind(stop) in _TRANSPORT_KINDS and not terminal:
                previous = None
                continue
            here = _coords(stop, destination)
            if not here:
                previous = None
                continue
            if previous is not None:
                previous_name, previous_day, previous_coords, previous_terminal = previous
                if not (previous_terminal and terminal) and (
                    _haversine_km(previous_coords, here) > CONTINUITY_KM
                ):
                    out.append(
                        Violation(
                            "I9",
                            "Continuity",
                            (
                                f"Day {day} starts at {name}, far from where Day "
                                f"{previous_day} ended, and no journey connects them."
                            )
                            if previous_day != day
                            else (
                                f"{name} is far from {previous_name} on Day {day}, "
                                "and no journey connects them."
                            ),
                            day,
                            name,
                        )
                    )
            previous = (name, day, here, terminal)
    return out


def _coverage_violations(plan: dict[str, Any]) -> list[Violation]:
    """I10. Say when the guard has gone blind instead of passing in silence.

    Without an origin there is no envelope, so arrival, presence, stay coverage
    and return all stop reporting — the plan looks clean because nothing looked.
    A traveller who is arranging their own way there has answered the question,
    though, and must not be asked again on every edit.
    """
    if not str(plan.get("destination") or "").strip():
        return []
    if str(plan.get("origin") or "").strip() or plans_own_arrival(plan):
        return []
    return [
        Violation(
            "I10",
            "Guard coverage",
            "The trip does not say where it starts from, so arrival, presence, stay "
            "coverage and the return leg cannot be checked. Ask the traveller where "
            "they are setting out from, or record that they are arranging their own "
            "way there.",
        )
    ]


def _return_violations(plan: dict[str, Any], env: Envelope) -> list[Violation]:
    origin = str(plan.get("origin") or "").strip()
    destination = str(plan.get("destination") or "").strip()
    if not origin or not destination or origin.casefold() == destination.casefold():
        return []
    if env.arrival_day is None and env.departure_day is not None:
        return [
            Violation(
                "I7",
                "Return coverage",
                f"The return leg from {destination} has no matching outbound from {origin}.",
            )
        ]
    if env.arrival_day is None or env.departure_day is not None:
        return []
    return [
        Violation(
            "I7",
            "Return coverage",
            f"The outbound leg to {destination} has no matching return to {origin}.",
        )
    ]


# --------------------------------------------------------------------------- #
# guarded placement                                                             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Window:
    day: int
    index: int
    start: int
    end: int
    before: Any | None
    after: Any | None


def _day_bounds(day: int, env: Envelope) -> tuple[int, int]:
    start = _abs(day, DAY_START_MIN)
    end = _abs(day, DAY_END_MIN)
    if env.arrival_day == day and env.arrival_end is not None:
        start = max(start, env.arrival_end)
    if env.departure_day == day and env.departure_start is not None:
        end = min(end, env.departure_start - PRE_DEPARTURE_BUFFER_MIN)
    if env.arrival_day is not None and day < env.arrival_day:
        return (0, -1)
    if env.departure_day is not None and day > env.departure_day:
        return (0, -1)
    return start, end


def _windows(day: int, stops: list[Any], env: Envelope) -> list[_Window]:
    start, end = _day_bounds(day, env)
    if end <= start:
        return []
    blocks: list[tuple[int, int, int, Any]] = []
    for index, stop in enumerate(stops):
        at = _time_of(stop)
        if at is None:
            continue
        if _stop_kind(stop) in _TRANSPORT_KINDS:
            # The trip's own arrival and departure already bound the day. Any
            # other journey is a drive the traveller is sitting in, so it holds
            # its hours the same way a museum visit does.
            if _stop_name(stop) in {env.arrival_name, env.departure_name}:
                continue
        blocks.append(
            (
                _abs(day, at) - TURNAROUND_MIN,
                _abs(day, at) + _duration_of(stop) + TURNAROUND_MIN,
                index,
                stop,
            )
        )
    blocks.sort(key=lambda block: block[0])

    windows: list[_Window] = []
    cursor = start
    previous: Any | None = None
    insert_at = 0
    for block_start, block_end, index, stop in blocks:
        if block_start > cursor:
            windows.append(_Window(day, index, cursor, min(block_start, end), previous, stop))
        cursor = max(cursor, block_end)
        previous = stop
        insert_at = index + 1
    if cursor < end:
        windows.append(_Window(day, max(insert_at, len(stops)), cursor, end, previous, None))
    return [window for window in windows if window.end > window.start]


def choose_placement(
    plan: dict[str, Any],
    name: str,
    kind: str,
    *,
    duration_min: int | None = None,
    preferred_day: int | None = None,
) -> tuple[Placement | None, list[Rejection]]:
    """Pick the best legal slot for a new stop, or explain why none exists.

    Unlike the load heuristic this replaces, a day that cannot legally hold the
    stop is not merely expensive — it is not a candidate at all. That is what
    keeps a new place off the far side of the flight home.
    """
    destination = str(plan.get("destination") or "")
    env = envelope(plan)
    summary = _summary_for_place(name, destination)
    coords = _coords_from_summary(summary)
    facts = place_facts.facts_from_summary(summary)
    dates = day_dates(plan)
    visit = (
        duration_min
        if isinstance(duration_min, int) and duration_min > 0
        else _default_duration(kind)
    )

    best: tuple[float, Placement] | None = None
    rejections: list[Rejection] = []

    for day, _entry, stops in days_of(plan):
        if preferred_day is not None and day != preferred_day:
            continue
        day_iso = dates.get(day, "")
        hours = facts.hours_on(day_iso) if kind in _PLACE_KINDS else None
        if hours == ():
            weekday = place_facts.weekday_of(day_iso)
            rejections.append(
                Rejection(
                    day,
                    "all day",
                    "I11",
                    "closed on "
                    + (place_facts.WEEKDAY_NAMES[weekday] if weekday is not None else "that day")
                    + "s",
                )
            )
            continue
        for window in _windows(day, stops, env):
            label = f"{_fmt_hhmm(window.start % 1440)}–{_fmt_hhmm(window.end % 1440)}"
            inbound = TURNAROUND_MIN
            outbound = TURNAROUND_MIN
            before_at = _coords(window.before, destination) if window.before else None
            after_at = _coords(window.after, destination) if window.after else None
            if coords and before_at:
                inbound = travel_min(before_at, coords)
            if coords and after_at:
                outbound = travel_min(coords, after_at)

            available = window.end - window.start
            needed = inbound + visit + outbound
            if available < needed:
                rejections.append(
                    Rejection(
                        day,
                        label,
                        "I4",
                        f"needs {needed} minutes with travel, the gap is {available}",
                    )
                )
                continue

            earliest = -(-(window.start + inbound) // 5) * 5
            begins = earliest
            if hours:
                day_start = _abs(day, 0)
                latest = window.end - outbound - visit
                legal: list[int] = []
                for opens, closes in hours:
                    candidate = -(-max(earliest, day_start + opens) // 5) * 5
                    if candidate <= latest and candidate + visit <= day_start + closes:
                        legal.append(candidate)
                if not legal:
                    local = earliest - day_start
                    rejections.append(
                        Rejection(
                            day,
                            label,
                            "I3",
                            f"arriving {_fmt_hhmm(local)} does not fit "
                            f"{facts.window_text(day_iso)}",
                        )
                    )
                    continue
                begins = min(legal)
            local = begins - _abs(day, 0)

            detour = 0.0
            if coords and before_at:
                detour += _haversine_km(before_at, coords)
            if coords and after_at:
                detour += _haversine_km(coords, after_at)
            if before_at and after_at:
                detour -= _haversine_km(before_at, after_at)
            load = sum(_duration_of(stop) for stop in stops)
            slack = available - needed
            score = max(0.0, detour) * 1.4 + load * 0.08 - min(slack, 180) * 0.15
            if env.arrival_day == day:
                score += 25

            reasons = [
                f"{round(max(0.0, detour))} km of extra driving against the day's route",
                f"{inbound} min in, {outbound} min out, {slack} min of slack left",
                f"Day {day} already holds about {round(load / 60)}h of plans",
            ]
            if env.arrival_day == day:
                reasons.append("Penalised for being the arrival day, when delays are most likely")
            if hours:
                reasons.append(
                    f"Open {facts.window_text(day_iso)}; "
                    f"this visit is {_fmt_hhmm(local)}–{_fmt_hhmm((local + visit) % 1440)}"
                )

            placement = Placement(day, window.index, _fmt_hhmm(local), reasons)
            if best is None or score < best[0]:
                best = (score, placement)

    return (best[1] if best else None), rejections


# --------------------------------------------------------------------------- #
# blast radius                                                                  #
# --------------------------------------------------------------------------- #


def _index_plan(plan: dict[str, Any]) -> dict[tuple[int, str], dict[str, Any]]:
    index: dict[tuple[int, str], dict[str, Any]] = {}
    for day, _entry, stops in days_of(plan):
        for stop in stops:
            name = _stop_name(stop)
            if not name:
                continue
            index[(day, name.casefold())] = {
                "day": day,
                "name": name,
                "time": str(stop.get("time") or "") if isinstance(stop, dict) else "",
                "kind": _stop_kind(stop),
            }
    return index


def diff_stops(before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    """Every stop-level difference between two plans, written from the plans."""
    left = _index_plan(before)
    right = _index_plan(after)
    left_names = {name: entry for (_day, name), entry in left.items()}
    right_names = {name: entry for (_day, name), entry in right.items()}

    changes: list[Change] = []
    for key, entry in left.items():
        if key in right:
            moved = right[key]
            if moved["time"] != entry["time"] and entry["time"] and moved["time"]:
                detail = f"{entry['time']} → {moved['time']}"
                changes.append(Change("moved", entry["day"], entry["name"], detail))
            continue
        elsewhere = right_names.get(key[1])
        if elsewhere:
            changes.append(
                Change(
                    "moved",
                    elsewhere["day"],
                    entry["name"],
                    f"Day {entry['day']} → Day {elsewhere['day']}",
                )
            )
        else:
            was = f"was at {entry['time'] or 'no set time'}"
            changes.append(Change("removed", entry["day"], entry["name"], was))
    for key, entry in right.items():
        if key in left or key[1] in left_names:
            continue
        at = f"at {entry['time'] or 'no set time'}"
        changes.append(Change("added", entry["day"], entry["name"], at))
    return changes


def unexpected_changes(changes: list[Change], declared: set[str]) -> list[Change]:
    """I8. Anything the operation touched without saying it would."""
    allowed = {name.casefold() for name in declared}
    return [change for change in changes if change.name.casefold() not in allowed]


def receipt(changes: list[Change]) -> str:
    """A change report written from the diff, not from the request."""
    if not changes:
        return "Nothing in the trip changed."
    return " ".join(change.sentence() for change in changes)
