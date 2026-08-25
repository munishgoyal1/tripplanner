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
    unnamed_lodging,
    unnamed_meal,
)
from tripplanner.tools.trip_guard import (
    KNOWN_FACT_CODES,
    leg_touches_home,
    plans_own_arrival,
    validate_plan,
)

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


_MEAL_OPEN_RE = re.compile(
    r"\b(meals? (?:are )?open|open meal|meal at leisure|choose (?:your|their) own "
    r"(?:meal|restaurant)|self-guided dining)\b",
    re.I,
)
_WHOLE_DAY_LEISURE_RE = re.compile(
    r"\b(day at leisure|leisure day|free day|rest day|open day|unplanned day)\b",
    re.I,
)
_INTERCITY_TRANSFER_RE = re.compile(
    r"\b(?:flight|train|bus|drive|ferry)\b.*(?:→|\bto\b)|\b(?:overnight|sleeper)\b",
    re.I,
)


def _day_allows_open_meals(day: dict[str, Any], stops: list[Any]) -> bool:
    day_text = " ".join(str(day.get(key) or "") for key in ("title", "summary", "note", "notes"))
    if _MEAL_OPEN_RE.search(day_text) or _WHOLE_DAY_LEISURE_RE.search(day_text):
        return True
    return any(
        _stop_kind(stop) in {"flight", "transport"}
        and _INTERCITY_TRANSFER_RE.search(_stop_name(stop))
        for stop in stops
    )


def _dietary_preferences(plan: dict[str, Any]) -> list[str]:
    preferences = plan.get("preferences_snapshot")
    preferences = preferences if isinstance(preferences, dict) else {}
    diets: list[str] = []
    food = preferences.get("food_preferences")
    if isinstance(food, dict):
        raw = food.get("dietary")
        diets.extend([raw] if isinstance(raw, str) else (raw or []))
    for member in preferences.get("family_members") or []:
        if not isinstance(member, dict):
            continue
        raw = member.get("dietary")
        diets.extend([raw] if isinstance(raw, str) else (raw or []))
    return [
        str(diet).strip().lower()
        for diet in diets
        if str(diet).strip().lower() not in {"", "none", "no", "any"}
    ]


def _restaurant_itinerary_warnings(
    itinerary: Any,
    *,
    cities: set[str] | None = None,
    dietary: list[str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    if not isinstance(itinerary, list):
        return warnings
    known_cities = cities or set()
    diet_tokens = {
        token
        for diet in (dietary or [])
        for token in re.split(r"[\s,;/]+", diet)
        if len(token) >= 4
    }
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
            if _MEAL_PLACEHOLDER_RE.search(_stop_name(stop))
            or unnamed_meal(_stop_name(stop), known_cities)
        ]
        if placeholders:
            warnings.append(f"Day {day_num} has a meal placeholder instead of a named restaurant.")
        elif place_count >= 2 and not meal_stops and not _day_allows_open_meals(day, stops):
            warnings.append(f"Day {day_num} has multiple activities but no named restaurant stop.")
        elif meal_stops and diet_tokens:
            meal_text = " ".join(
                str(value)
                for stop in meal_stops
                if isinstance(stop, dict)
                for value in stop.values()
            ).lower()
            if not any(token in meal_text for token in diet_tokens):
                warnings.append(
                    f"Day {day_num}'s named meal does not confirm the saved dietary "
                    f"preference ({', '.join(sorted(set(dietary or [])))})."
                )
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


def _round_trip_transport_warnings(plan: dict[str, Any]) -> list[str]:
    """Missing explicit journey edges, without requiring provider inventory."""
    origin = str(plan.get("origin") or "").strip()
    destination = str(plan.get("destination") or "").strip()
    itinerary = plan.get("day_wise_itinerary")
    if not destination:
        return []
    if not isinstance(itinerary, list) or not itinerary:
        return []
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
    first_hotel = next(
        (index for index, stop in enumerate(first_stops) if _stop_kind(stop) == "hotel"),
        None,
    )
    last_hotel = next(
        (
            index
            for index in range(len(last_stops) - 1, -1, -1)
            if _stop_kind(last_stops[index]) == "hotel"
        ),
        None,
    )
    has_outbound = first_hotel is not None and any(
        leg_touches_home(stop, origin)[0] for stop in first_stops[:first_hotel]
    )
    has_return = last_hotel is not None and any(
        leg_touches_home(stop, origin)[1] for stop in last_stops[last_hotel + 1:]
    )

    warnings: list[str] = []
    if not has_outbound:
        warnings.append(
            f"Arrival day has no explicit flight, rail, ferry, road, or other journey "
            f"from {origin} to {destination} before destination check-in."
        )
    if not has_return:
        warnings.append(
            f"Departure day has no explicit flight, rail, ferry, road, or other journey "
            f"from {destination} back to {origin} after checkout."
        )
    return warnings


def _journey_inventory_errors(plan: dict[str, Any]) -> list[str]:
    """Selected flight inventory and narrated flight edges must agree."""
    if plans_own_arrival(plan):
        return []
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list) or not itinerary:
        return []
    flight_edges = [
        stop
        for day in itinerary
        if isinstance(day, dict)
        for stop in (day.get("stops") if isinstance(day.get("stops"), list) else [])
        if _stop_kind(stop) == "flight"
    ]
    selected = plan.get("selected_flights")
    selected_flights = selected if isinstance(selected, list) else []
    if flight_edges and not selected_flights:
        return [
            "The itinerary narrates flight travel but no selected flight offer supports it."
        ]
    if selected_flights and not flight_edges:
        return [
            "Selected flight offers have no explicit outbound or return flight edge "
            "in the itinerary."
        ]
    return []


def _journey_persistence_errors(plan: dict[str, Any]) -> list[str]:
    """Journey completeness once a plan claims or selects travel."""
    if plans_own_arrival(plan):
        return []
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list) or not itinerary:
        return []
    journey_stops = [
        stop
        for day in itinerary
        if isinstance(day, dict)
        for stop in (day.get("stops") if isinstance(day.get("stops"), list) else [])
        if _stop_kind(stop) in {"flight", "transport"}
    ]
    selected = plan.get("selected_flights")
    has_selected_flights = isinstance(selected, list) and bool(selected)
    if not journey_stops and not has_selected_flights:
        return []
    if not str(plan.get("origin") or "").strip():
        return []
    return [
        *_round_trip_transport_warnings(plan),
        *_journey_inventory_errors(plan),
    ]


def _hotel_selection_warnings(plan: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    hotels = plan.get("selected_hotels")
    if isinstance(hotels, list) and not hotels:
        warnings.append("No concrete hotel is selected.")

    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return warnings
    warnings.extend(_lodging_name_warnings(plan))
    missing_days = [
        violation.day
        for violation in validate_plan(plan)
        if violation.code == "I6" and violation.stop is None and violation.day is not None
    ]
    if missing_days:
        warnings.append(
            f"Day(s) {', '.join(str(day) for day in missing_days)} have no concrete "
            "lodging anchor for the night."
        )
    return warnings


def _lodging_name_warnings(
    plan: dict[str, Any], *, include_placeholders: bool = True
) -> list[str]:
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return []
    warnings: list[str] = []
    cities = _itinerary_hotel_locations(plan)
    destination = str(plan.get("destination") or "").strip().lower()
    if destination:
        cities = cities | {destination} | {
            part.strip() for part in re.split(r"[,&/()]| and ", destination) if part.strip()
        }
    placeholder_days: list[str] = []
    unnamed_days: list[str] = []
    for index, day in enumerate(itinerary):
        if not isinstance(day, dict):
            continue
        raw_stops = day.get("stops")
        stops = raw_stops if isinstance(raw_stops, list) else []
        stays = [stop for stop in stops if _stop_kind(stop) == "hotel"]
        day_num = str(day.get("day") if isinstance(day.get("day"), int) else index + 1)
        if any(_HOTEL_PLACEHOLDER_RE.search(_stop_name(stop)) for stop in stays):
            placeholder_days.append(day_num)
        elif any(unnamed_lodging(_stop_name(stop), cities) for stop in stays):
            unnamed_days.append(day_num)
    if include_placeholders and placeholder_days:
        warnings.append(
            f"Hotel placeholders remain on Day(s) {', '.join(placeholder_days)}."
        )
    if unnamed_days:
        warnings.append(
            f"Day(s) {', '.join(unnamed_days)} name no bookable property -- a stay "
            "described only as a hotel in a city cannot be booked, reached, or priced. "
            "Choose a real property, or offer two or three named candidates."
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


def _requested_budget_without_cost_evidence(plan: dict[str, Any]) -> list[str]:
    budget = plan.get("budget")
    amount = budget.get("amount") if isinstance(budget, dict) else budget
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
        return []
    total_cost = plan.get("total_cost")
    if (
        isinstance(total_cost, (int, float))
        and not isinstance(total_cost, bool)
        and total_cost > 0
    ):
        return []
    return [
        "The traveller requested a budget, but total_cost has no positive cost evidence. "
        "Save a grounded whole-trip estimate before presenting the plan as complete."
    ]


def _itinerary_density_warnings(plan: dict[str, Any]) -> list[str]:
    recommendation = plan.get("planning_recommendation")
    if not isinstance(recommendation, dict):
        return []
    preferences = dict(plan.get("preferences_snapshot") or {})
    planning_preferences = dict(preferences.get("planning_preferences") or {})
    target_minutes = recommendation.get("target_active_minutes_per_full_day")
    if isinstance(target_minutes, (int, float)):
        planning_preferences["target_active_minutes_per_full_day"] = target_minutes
    preferences["planning_preferences"] = planning_preferences
    assessment = assess_itinerary_density(plan.get("day_wise_itinerary") or [], preferences)
    if not assessment.sparse_days:
        return []
    reasons = "; ".join(day.reason for day in assessment.sparse_days[:3])
    return [
        "Sparse itinerary: " + reasons + ". Rebalance meaningful nearby stops "
        "or explicitly label intentional leisure; do not add filler."
    ]


def core_planning_completion_gaps(plan: dict[str, Any]) -> list[str]:
    """Gaps that a first planning turn must resolve even after its normal tool budget."""
    itinerary = plan.get("day_wise_itinerary")
    if plan.get("destination") and not (isinstance(itinerary, list) and itinerary):
        return [
            "No day-by-day itinerary is saved. Save the full structured "
            "day_wise_itinerary before presenting the trip as planned."
        ]

    violations = validate_plan(plan)
    journey_continuity = [
        violation.message for violation in violations if violation.code in {"I7", "I9"}
    ]
    departure_buffers = [
        violation.message for violation in violations if violation.code == "I5"
    ]
    return [
        *_restaurant_itinerary_warnings(
            itinerary,
            cities=_itinerary_hotel_locations(plan),
            dietary=_dietary_preferences(plan),
        ),
        *_empty_itinerary_day_warnings(itinerary),
        *_round_trip_transport_warnings(plan),
        *_hotel_selection_warnings(plan),
        *journey_continuity,
        *departure_buffers,
        *_requested_budget_without_cost_evidence(plan),
        *_itinerary_density_warnings(plan),
    ]


def planning_completion_gaps(plan: dict[str, Any]) -> list[str]:
    """Return actionable gaps that keep a new plan from feeling complete."""
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
        *_restaurant_itinerary_warnings(
            plan.get("day_wise_itinerary"),
            cities=_itinerary_hotel_locations(plan),
            dietary=_dietary_preferences(plan),
        ),
        *_empty_itinerary_day_warnings(plan.get("day_wise_itinerary")),
        *_round_trip_transport_warnings(plan),
        *_hotel_selection_warnings(plan),
        *coherence_gaps,
        *_itinerary_density_warnings(plan),
    ]


def finalization_gaps(plan: dict[str, Any]) -> list[str]:
    """Return every known reason this trip cannot yet be called booking-ready."""
    known_fact_gaps = [
        violation.message
        for violation in validate_plan(plan)
        if violation.code in KNOWN_FACT_CODES
    ]
    return [*planning_completion_gaps(plan), *known_fact_gaps]


def _itinerary_time_errors(itinerary: Any) -> list[str]:
    """Chronology and duration conflicts across every timed itinerary row."""
    errors: list[str] = []
    if not isinstance(itinerary, list):
        return errors
    previous_start: int | None = None
    previous_end: int | None = None
    previous_name = ""
    previous_day: int | None = None
    previous_kind = ""
    for day_index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        day = entry.get("day") if isinstance(entry.get("day"), int) else day_index + 1
        stops = entry.get("stops") if isinstance(entry.get("stops"), list) else []
        for stop in stops:
            if not isinstance(stop, dict):
                continue
            value = str(stop.get("time") or "").strip()
            if not value:
                continue
            current_time = _parse_hhmm(value)
            name = _stop_name(stop) or "unnamed stop"
            if current_time is None:
                errors.append(f"Day {day} has an invalid time '{value}' for {name}; use HH:MM.")
                continue
            current_start = (day - 1) * 1440 + current_time
            if (
                previous_day == day
                and previous_end is not None
                and previous_end > day * 1440
                and current_start < previous_start
            ):
                current_start += 1440
            turnaround = 0 if previous_kind in {"hotel", "flight", "transport"} else 30
            minimum_start = previous_end + turnaround if previous_end is not None else None
            if minimum_start is not None and current_start < minimum_start:
                errors.append(
                    f"Day {day} is not chronological: {name} at {value} must be after "
                    f"{previous_name} and its visit or journey duration "
                    f"(not before {_fmt_hhmm(minimum_start % 1440)})."
                )
            previous_start = current_start
            previous_end = current_start + validate_guard._duration_of(stop)
            previous_name = name
            previous_day = day
            previous_kind = _stop_kind(stop)
    return errors


_PERSISTENCE_SANITY_CODES = frozenset(
    {"I1", "I2", "I3", "I4", "I5", "I6", "I7", "I9", "I11", "I12"}
)


def persistence_sanity_errors(plan: dict[str, Any]) -> list[str]:
    """Authoritative contradictions that must not cross the persistence boundary."""
    errors = [
        *_itinerary_time_errors(plan.get("day_wise_itinerary")),
        *_lodging_name_warnings(plan, include_placeholders=False),
        *(
            violation.message
            for violation in validate_plan(plan)
            if violation.code in _PERSISTENCE_SANITY_CODES
        ),
        *_journey_persistence_errors(plan),
    ]
    return list(dict.fromkeys(errors))


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
