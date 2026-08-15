"""Itinerary validation and post-mutation review checks.

Pure, read-only assessments over a trip plan — restaurant/empty-day/hotel
placeholder warnings, round-trip transport checks, chronology errors, completion
gaps, and the post-edit "does this change merit review?" heuristic. Split out
(tech-debt #8) as a leaf module; ``trip_planner`` re-exports these names so
existing callers and tests resolve unchanged.
"""

from __future__ import annotations

import re
from typing import Any

from tripplanner.planning_intelligence import assess_itinerary_density
from tripplanner.tools import trip_guard as validate_guard
from tripplanner.tools.trip_common import (
    _HOTEL_PLACEHOLDER_RE,
    _MEAL_PLACEHOLDER_RE,
    _day_stats,
    _fmt_hhmm,
    _parse_hhmm,
    _stop_kind,
    _stop_name,
    _style_caps,
)
from tripplanner.tools.trip_guard import leg_touches_home, plans_own_arrival, validate_plan

#: Invariants that mean the itinerary contradicts itself about time or place.
#: Temporal feasibility is left out on purpose: it degrades with missing cached
#: facts, and a gate must not fire on what it cannot know.
_COHERENCE_CODES = frozenset({"I1", "I2", "I5", "I9"})


def itinerary_coherence_gaps(plan: dict[str, Any]) -> list[str]:
    """Ways the saved itinerary disagrees with itself, in the user's terms."""
    return [
        violation.message
        for violation in validate_plan(plan)
        if violation.code in _COHERENCE_CODES
    ]


def _restaurant_itinerary_warnings(itinerary: Any) -> list[str]:
    warnings: list[str] = []
    if not isinstance(itinerary, list):
        return warnings
    for index, day in enumerate(itinerary):
        if not isinstance(day, dict):
            continue
        day_num = day.get("day") if isinstance(day.get("day"), int) else index + 1
        raw_stops = day.get("stops")
        stops: list[Any] = raw_stops if isinstance(raw_stops, list) else []
        place_count = sum(1 for stop in stops if _stop_kind(stop) == "attraction")
        meal_stops = [stop for stop in stops if _stop_kind(stop) == "meal"]
        placeholders = [
            _stop_name(stop)
            for stop in meal_stops
            if not _stop_name(stop) or _MEAL_PLACEHOLDER_RE.search(_stop_name(stop))
        ]
        if placeholders:
            warnings.append(f"Day {day_num} has a meal placeholder instead of a named restaurant.")
        elif place_count >= 2 and not meal_stops:
            warnings.append(f"Day {day_num} has multiple activities but no named restaurant stop.")
    return warnings


def _empty_itinerary_day_warnings(itinerary: Any) -> list[str]:
    warnings: list[str] = []
    if not isinstance(itinerary, list):
        return warnings
    for index, day in enumerate(itinerary):
        if not isinstance(day, dict):
            continue
        day_num = day.get("day") if isinstance(day.get("day"), int) else index + 1
        raw_stops = day.get("stops")
        stops: list[Any] = raw_stops if isinstance(raw_stops, list) else []
        kinds = {_stop_kind(stop) for stop in stops}
        if not kinds.intersection({"attraction", "meal"}) and not kinds.intersection(
            {"flight", "transport"}
        ):
            warnings.append(f"Day {day_num} has no planned places beyond the hotel.")
    return warnings


_INTERCITY_GROUND_MODE_RE = re.compile(r"\b(?:drive|road|car|bus|train|rail)\b", re.I)
_CITY_NAME_ALIASES = {"bengaluru": "bangalore", "mysuru": "mysore"}


def _round_trip_transport_warnings(plan: dict[str, Any]) -> list[str]:
    origin = str(plan.get("origin") or "").strip()
    destination = str(plan.get("destination") or "").strip()
    itinerary = plan.get("day_wise_itinerary")
    if not destination:
        return []
    if not isinstance(itinerary, list) or not itinerary:
        return []
    # A traveller who is getting there on their own owes no outbound leg, and a
    # trip that has simply never been asked is a question, not a fault.
    if plans_own_arrival(plan):
        return []
    if not origin:
        return [
            "The trip does not say where it starts from. Ask the traveller which city "
            "they are travelling from, or whether they are arranging their own way "
            "there, and save the answer as origin or travel_scope."
        ]
    if origin.casefold() == destination.casefold():
        return []

    days = [day for day in itinerary if isinstance(day, dict)]
    if not days:
        return []
    first_stops = days[0].get("stops") if isinstance(days[0].get("stops"), list) else []
    last_stops = days[-1].get("stops") if isinstance(days[-1].get("stops"), list) else []

    def normalized_text(value: str, *, city_only: bool = False) -> str:
        text = re.split(r"[,;/]", value, maxsplit=1)[0] if city_only else value
        text = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
        for alias, canonical in _CITY_NAME_ALIASES.items():
            text = re.sub(rf"\b{re.escape(alias)}\b", canonical, text)
        return text

    def has_direction(stop: Any, source: str, target: str) -> bool:
        kind = _stop_kind(stop)
        name = normalized_text(_stop_name(stop))
        source_name = normalized_text(source, city_only=True)
        target_name = normalized_text(target, city_only=True)
        source_index = name.find(source_name)
        target_index = name.find(target_name, source_index + len(source_name))
        has_mode = kind == "flight" or (
            kind == "transport" and bool(_INTERCITY_GROUND_MODE_RE.search(_stop_name(stop)))
        )
        return has_mode and source_index >= 0 and target_index > source_index

    first_hotel = next(
        (index for index, stop in enumerate(first_stops) if _stop_kind(stop) == "hotel"),
        len(first_stops),
    )
    last_hotel = next(
        (index for index in range(len(last_stops) - 1, -1, -1)
         if _stop_kind(last_stops[index]) == "hotel"),
        -1,
    )
    # A regional destination names its real cities, so a leg that simply leaves
    # or returns home counts even when it never spells the destination out.
    has_outbound = first_hotel < len(first_stops) and any(
        has_direction(stop, origin, destination) or leg_touches_home(stop, origin)[0]
        for stop in first_stops[:first_hotel]
    )
    has_return = last_hotel >= 0 and any(
        has_direction(stop, destination, origin) or leg_touches_home(stop, origin)[1]
        for stop in last_stops[last_hotel + 1:]
    )

    warnings: list[str] = []
    if not has_outbound:
        warnings.append(
            f"Arrival day has no flight or named road, bus, or train journey from "
            f"{origin} to {destination} before destination check-in."
        )
    if not has_return:
        warnings.append(
            f"Departure day has no flight or named road, bus, or train journey from "
            f"{destination} back to {origin} after checkout."
        )
    return warnings


def _hotel_selection_warnings(plan: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    hotels = plan.get("selected_hotels")
    if isinstance(hotels, list) and not hotels:
        warnings.append("No concrete hotel is selected.")

    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return warnings
    placeholder_days: list[str] = []
    for index, day in enumerate(itinerary):
        if not isinstance(day, dict):
            continue
        raw_stops = day.get("stops")
        stops = raw_stops if isinstance(raw_stops, list) else []
        if any(
            _stop_kind(stop) == "hotel"
            and _HOTEL_PLACEHOLDER_RE.search(_stop_name(stop))
            for stop in stops
        ):
            day_num = day.get("day") if isinstance(day.get("day"), int) else index + 1
            placeholder_days.append(str(day_num))
    if placeholder_days:
        warnings.append(
            f"Hotel placeholders remain on Day(s) {', '.join(placeholder_days)}."
        )
    return warnings


def _itinerary_hotel_locations(plan: dict[str, Any]) -> set[str]:
    locations: set[str] = set()
    for hotel in plan.get("selected_hotels") or []:
        if not isinstance(hotel, dict):
            continue
        for key in ("destination", "city", "location"):
            value = str(hotel.get(key) or "").strip().lower()
            if value:
                locations.add(value)
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        for key in ("destination", "city", "location"):
            value = str(day.get(key) or "").strip().lower()
            if value:
                locations.add(value)
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            for key in ("destination", "city", "location"):
                value = str(stop.get(key) or "").strip().lower()
                if value:
                    locations.add(value)
            if _stop_kind(stop) not in {"flight", "transport"}:
                continue
            route = re.split(r"\b(?:to|→)\b", _stop_name(stop), flags=re.IGNORECASE)
            for city in route[1:]:
                value = re.split(r"[,;(/]", city, maxsplit=1)[0].strip().lower()
                if value:
                    locations.add(value)
    return locations


def _hotel_destination_errors(
    destination: str,
    hotels: Any,
    itinerary_locations: set[str] | None = None,
) -> list[str]:
    if not destination.strip() or not isinstance(hotels, list):
        return []
    destination_token = re.split(r"[,;/]", destination.lower(), maxsplit=1)[0].strip()
    if not destination_token:
        return []
    destination_parts = [part.strip() for part in re.split(r"[,;/]", destination.lower())]
    destination_country = destination_parts[1] if len(destination_parts) > 1 else ""
    allowed_locations = {destination_token, *(itinerary_locations or set())}
    errors: list[str] = []
    for hotel in hotels:
        if not isinstance(hotel, dict):
            continue
        name = _stop_name(hotel) or str(hotel.get("hotel_name") or "").strip()
        if _HOTEL_PLACEHOLDER_RE.search(name):
            continue
        structured_locations = [
            str(hotel.get(key) or "").strip().lower()
            for key in ("destination", "city", "location")
            if str(hotel.get(key) or "").strip()
        ]
        address = str(hotel.get("address") or "").strip().lower()
        country = str(hotel.get("country") or "").strip().lower()
        matching_location = any(
            allowed in location or location in allowed
            for location in structured_locations
            for allowed in allowed_locations
        )
        mismatched_country = bool(
            country and destination_country and destination_country not in country
        )
        address_only_mismatch = bool(
            address
            and not structured_locations
            and not any(allowed in address for allowed in allowed_locations)
        )
        if (
            (structured_locations and not matching_location)
            or mismatched_country
            or address_only_mismatch
        ):
            errors.append(
                f"{name or 'Selected hotel'} is located outside the trip destination "
                f"'{destination}'."
            )
        elif not structured_locations and not address and not any(
            allowed in name.lower() for allowed in allowed_locations
        ):
            errors.append(
                f"{name or 'Selected hotel'} has no location evidence matching the trip "
                f"destination '{destination}'."
            )
    return errors


def planning_completion_gaps(plan: dict[str, Any]) -> list[str]:
    """Return actionable gaps that keep a new plan from feeling complete."""
    density_warnings: list[str] = []
    recommendation = plan.get("planning_recommendation")
    if isinstance(recommendation, dict):
        preferences = dict(plan.get("preferences_snapshot") or {})
        planning_preferences = dict(preferences.get("planning_preferences") or {})
        target_minutes = recommendation.get("target_active_minutes_per_full_day")
        if isinstance(target_minutes, (int, float)):
            planning_preferences["target_active_minutes_per_full_day"] = target_minutes
        preferences["planning_preferences"] = planning_preferences
        assessment = assess_itinerary_density(
            plan.get("day_wise_itinerary") or [], preferences
        )
        if assessment.sparse_days:
            reasons = "; ".join(day.reason for day in assessment.sparse_days[:3])
            density_warnings.append(
                "Sparse itinerary: " + reasons + ". Rebalance meaningful nearby stops "
                "or explicitly label intentional leisure; do not add filler."
            )
    itinerary = plan.get("day_wise_itinerary")
    # Every other check walks the days, so a trip with none of them reported
    # nothing at all and could be narrated as planned while holding no plan.
    missing_itinerary = (
        [
            "No day-by-day itinerary is saved. Save the full structured "
            "day_wise_itinerary before presenting the trip as planned."
        ]
        if plan.get("destination") and not (isinstance(itinerary, list) and itinerary)
        else []
    )
    coherence_gaps = itinerary_coherence_gaps(plan)
    if coherence_gaps:
        coherence_gaps = [
            "Itinerary is not coherent: "
            + " ".join(coherence_gaps[:3])
            + " Replan the affected day or days as a whole rather than moving one stop."
        ]
    return [
        *missing_itinerary,
        *_restaurant_itinerary_warnings(plan.get("day_wise_itinerary")),
        *_empty_itinerary_day_warnings(plan.get("day_wise_itinerary")),
        *_round_trip_transport_warnings(plan),
        *_hotel_selection_warnings(plan),
        *coherence_gaps,
        *density_warnings,
    ]


def _itinerary_time_errors(itinerary: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(itinerary, list):
        return errors
    for day_index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        day = entry.get("day") if isinstance(entry.get("day"), int) else day_index + 1
        stops = entry.get("stops") if isinstance(entry.get("stops"), list) else []
        previous_time: int | None = None
        previous_duration: int | None = None
        previous_name = ""
        for stop in stops:
            if _stop_kind(stop) in {"hotel", "flight", "transport"} or not isinstance(stop, dict):
                continue
            value = str(stop.get("time") or "").strip()
            if not value:
                continue
            current_time = _parse_hhmm(value)
            name = _stop_name(stop) or "unnamed stop"
            if current_time is None:
                errors.append(f"Day {day} has an invalid time '{value}' for {name}; use HH:MM.")
                continue
            minimum_time = previous_time
            if minimum_time is not None and previous_duration is not None:
                minimum_time += previous_duration + 30
            if minimum_time is not None and current_time < minimum_time:
                errors.append(
                    f"Day {day} is not chronological: {name} at {value} must be after "
                    f"{previous_name} at {_fmt_hhmm(previous_time)}"
                    + (
                        f" and its visit/transfer time (not before {_fmt_hhmm(minimum_time)})."
                        if previous_duration is not None
                        else "."
                    )
                )
            previous_time = current_time
            duration = stop.get("duration_min")
            previous_duration = (
                max(15, int(duration)) if isinstance(duration, (int, float)) else None
            )
            previous_name = name
    return errors


def assess_itinerary_change(
    plan: dict[str, Any],
    *,
    action: str,
    name: str,
    days: list[int] | None = None,
) -> dict[str, Any] | None:
    """Return a material post-mutation concern that merits planner review."""
    itinerary = plan.get("day_wise_itinerary") or []
    destination = str(plan.get("destination") or "")
    max_stops, max_duration, max_km = _style_caps(plan)
    requested_days = set(days or [])
    concerns: list[tuple[int, int, str]] = []

    for day_index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        day = int(entry.get("day") or day_index + 1)
        if requested_days and day not in requested_days:
            continue
        stops = entry.get("stops") if isinstance(entry.get("stops"), list) else []
        planned = [
            stop for stop in stops
            if _stop_kind(stop) in {"attraction", "meal", "restaurant", "other"}
        ]
        planned_duration = sum(
            int(stop.get("duration_min"))
            if isinstance(stop, dict) and isinstance(stop.get("duration_min"), (int, float))
            else 90
            for stop in planned
        )
        attraction_count = sum(_stop_kind(stop) in {"attraction", "other"} for stop in planned)
        has_meal = any(_stop_kind(stop) in {"meal", "restaurant"} for stop in planned)
        stats = _day_stats(entry, destination, (99, max_duration, max_km))
        planned_cap = max(2, max_stops - 1)
        reasons: list[str] = []
        severity = 0
        if len(planned) > planned_cap:
            reasons.append(f"{len(planned)} planned places")
            severity += 3
        if planned_duration > max_duration:
            hours = planned_duration / 60
            reasons.append(f"about {hours:.1f} hours of planned stops")
            severity += 2
        if stats["route_km"] > max_km:
            reasons.append(f"roughly {stats['route_km']:.0f} km between stops")
            severity += 2
        if action == "removed" and not planned:
            reasons.append("no non-stay places remaining")
            severity += 3
        elif attraction_count >= 3 and not has_meal:
            reasons.append("no named meal stop")
            severity += 1
        if reasons:
            concerns.append((severity, day, ", ".join(reasons)))

    if not concerns:
        return None

    _, day, reason = max(concerns, key=lambda item: (item[0], -item[1]))
    if "no non-stay places" in reason:
        summary = f"Day {day} is now empty apart from the stay."
    else:
        summary = f"Day {day} may feel crowded: {reason}."
    prompt = (
        f"Review my recent itinerary change: I {action} {name}. {summary} "
        "Explain the most important trade-off and propose up to three practical options. "
        "Do not change the itinerary or call any mutation tool until I explicitly approve an option."
    )
    return {
        "severity": "warning",
        "day": day,
        "summary": summary,
        "prompt": prompt,
    }
