"""Assembly of the interactive-map view-model from already-resolved pins.

Split out of ``trip_view`` (tech-debt #7). ``trip_view.build_map_view`` remains
the public entry point and keeps ownership of every data source that callers and
tests substitute (the browser Maps key, the airport pin, the place pins and the
itinerary); this module receives those as arguments and does only the pure
assembly of pins into day-colored routes and road circuits.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tripplanner.web.day_journey import (
    TERMINAL_KINDS,
    DayJourney,
    frame_pin_ids,
    plan_day_journeys,
    start_journey_from_stay,
)
from tripplanner.web.gallery import _terminal_occurrence_index, _terminal_occurrences
from tripplanner.web.map_pins import (
    _day_color,
    _hotel_identity_matches,
    _normalize_map_stops,
    _resolve_road_circuit_pin_ids,
    _route_circuit_id,
    _route_legs_for_day,
)
from tripplanner.web.schedule import _route_duration_display, _route_stats_for_day

# Resolves an itinerary stop name (with an optional kind hint) to its map pin.
PinResolver = Callable[..., "dict[str, Any] | None"]


def _day_number(entry: dict[str, Any], index: int) -> int:
    raw_day = entry.get("day")
    return raw_day if isinstance(raw_day, int) and raw_day > 0 else index + 1


def _annotate_pin_occurrences(
    trip: dict[str, Any],
    pins: list[dict[str, Any]],
    itinerary_days: dict[int, dict[str, Any]],
) -> None:
    """Tag each pin with the itinerary stops that render it, in place."""
    terminal_occurrences = _terminal_occurrence_index(trip)
    for pin in pins:
        rendered_occurrences = [
            {
                "day": day_num,
                "stop": stop_index,
                "time": str(stop.get("time") or ""),
            }
            for day_num, day in itinerary_days.items()
            for stop_index, stop in enumerate(day.get("stops") or [], start=1)
            if isinstance(stop, dict)
            if (
                str(stop.get("name") or "").strip().lower()
                == str(pin["_source_name"]).strip().lower()
                or (
                    pin["kind"] == "hotel"
                    and str(stop.get("kind") or "").strip().lower() == "hotel"
                    and _hotel_identity_matches(
                        str(stop.get("name") or ""), str(pin["_source_name"])
                    )
                )
            )
        ]
        if rendered_occurrences:
            pin["occurrences"] = rendered_occurrences
        elif pin["kind"] in TERMINAL_KINDS:
            pin["occurrences"] = _terminal_occurrences(
                trip, str(pin["_source_name"]), terminal_occurrences
            )


def _build_pin_resolver(pins: list[dict[str, Any]]) -> PinResolver:
    pin_by_name: dict[str, dict[str, Any]] = {}
    for pin in pins:
        pin_by_name[str(pin["name"]).strip().lower()] = pin
        pin_by_name[str(pin["_source_name"]).strip().lower()] = pin

    def _pin_for_stop(name: Any, kind_hint: str = "") -> dict[str, Any] | None:
        needle = str(name or "").strip().lower()
        if not needle:
            return None
        exact = pin_by_name.get(needle)
        if exact:
            return exact
        if kind_hint == "hotel":
            hotel_match = next(
                (
                    pin
                    for pin in pins
                    if pin["kind"] == "hotel"
                    and _hotel_identity_matches(str(pin["_source_name"]), str(name or ""))
                ),
                None,
            )
            if hotel_match:
                return hotel_match
        partial = next(
            (
                pin
                for candidate, pin in pin_by_name.items()
                if needle in candidate or candidate in needle
            ),
            None,
        )
        if partial:
            return partial
        return None

    return _pin_for_stop



def _occurrence_stop(pin_by_id: dict[str, dict[str, Any]], pin_id: str, day: int) -> int:
    pin = pin_by_id[pin_id]
    occurrence = next(
        (item for item in pin.get("occurrences") or [] if item.get("day") == day),
        None,
    )
    return int(occurrence.get("stop")) if occurrence and occurrence.get("stop") else 10_000



def _resolved_stay_ids(
    itinerary_days: dict[int, dict[str, Any]], pin_for_stop: PinResolver, day: int
) -> list[str]:
    itinerary_day = itinerary_days.get(day) or {}
    resolved: list[str] = []
    for stop in itinerary_day.get("stops") or []:
        if stop.get("kind") != "hotel":
            continue
        pin = pin_for_stop(stop.get("name"))
        if pin and str(pin["id"]) not in resolved:
            resolved.append(str(pin["id"]))
    return resolved


def _active_stay_ids(
    trip: dict[str, Any],
    itinerary_days: dict[int, dict[str, Any]],
    pin_for_stop: PinResolver,
    day: int,
    fallback_ids: list[str],
) -> list[str]:
    itinerary_date = str((itinerary_days.get(day) or {}).get("date") or "").strip()[:10]
    if len(itinerary_date) != 10:
        return fallback_ids

    active: list[str] = []
    has_dated_stay = False
    for stay in trip.get("selected_hotels") or []:
        if not isinstance(stay, dict):
            continue
        checkin = str(stay.get("checkin") or "").strip()[:10]
        checkout = str(stay.get("checkout") or "").strip()[:10]
        has_dated_stay = has_dated_stay or bool(checkin or checkout)
        if (checkin and itinerary_date < checkin) or (checkout and itinerary_date > checkout):
            continue
        pin = pin_for_stop(stay.get("name"), "hotel")
        if pin and str(pin["id"]) not in active:
            active.append(str(pin["id"]))
    return active if has_dated_stay else fallback_ids


def _carried_stay_id(
    itinerary_days: dict[int, dict[str, Any]], pin_for_stop: PinResolver, day: int
) -> str | None:
    """The stay a day starts from when the itinerary carries it over."""
    itinerary_stops = (itinerary_days.get(day) or {}).get("stops") or []
    if not itinerary_stops:
        return None
    first_stop = itinerary_stops[0]
    if first_stop.get("kind") != "hotel" or (
        str(first_stop.get("note") or "").strip().lower() != "start from your stay"
    ):
        return None
    pin = pin_for_stop(first_stop.get("name"))
    return str(pin["id"]) if pin else None




def _local_day_pin_ids(
    ids: list[str],
    pin_by_id: dict[str, dict[str, Any]],
    resolved_stay_ids: list[str],
    stay_ids: list[str],
) -> list[str]:
    """Order a non-transfer day as a loop that starts and ends at its stay."""
    if resolved_stay_ids:
        resolved_stay_set = set(resolved_stay_ids)
        ids = [
            pin_id
            for pin_id in ids
            if pin_by_id[pin_id]["kind"] != "hotel" or pin_id in resolved_stay_set
        ]
    day_stay = next((pid for pid in ids if pin_by_id[pid]["kind"] == "hotel"), None)
    stay_id = (
        (resolved_stay_ids[0] if resolved_stay_ids else None)
        or day_stay
        or (stay_ids[0] if stay_ids else None)
    )
    if not stay_id:
        return ids
    ids = [stay_id, *(pid for pid in ids if pid != stay_id), stay_id]
    return [stay_id] if len(set(ids)) == 1 else ids


def _day_route_summary(
    route_ids: list[str],
    pin_by_id: dict[str, dict[str, Any]],
    intercity_modes: dict[tuple[str, str], str] | None,
    legs: list[dict[str, Any]],
) -> dict[str, Any]:
    if not intercity_modes:
        return _route_stats_for_day(route_ids, pin_by_id)
    distance = round(sum(float(leg["distance_km"]) for leg in legs), 1)
    duration = sum(int(leg["duration_min"]) for leg in legs)
    modes = list(dict.fromkeys(intercity_modes.values()))
    if any(not leg.get("intercity") for leg in legs):
        modes.append("local")
    return {
        "distance_km": distance,
        "duration_min": duration,
        "mode": " + ".join(modes),
        "distance_display": f"{distance:.1f} km",
        "duration_display": _route_duration_display(duration),
    }


def _build_days(
    journeys: dict[int, DayJourney],
    transfer_metrics: dict[str, dict[str, float]],
    by_day: dict[int, list[str]],
    pins: list[dict[str, Any]],
    pin_by_id: dict[str, dict[str, Any]],
    pin_for_stop: PinResolver,
    itinerary_days: dict[int, dict[str, Any]],
    destination: str,
    trip: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_stay_ids = [p["id"] for p in pins if p["kind"] == "hotel" and p["selected"]]
    empty_journey = DayJourney(day=0)

    def _pin_kind(pin_id: str) -> str:
        return str(pin_by_id[pin_id]["kind"])

    days: list[dict[str, Any]] = []
    for d in sorted(by_day):
        ids = sorted(by_day[d], key=lambda pin_id: _occurrence_stop(pin_by_id, pin_id, d))
        journey = journeys.get(d, empty_journey)
        resolved_stay_ids = _resolved_stay_ids(itinerary_days, pin_for_stop, d)
        if journey.is_transfer:
            carried_stay_id = _carried_stay_id(itinerary_days, pin_for_stop, d)
            if carried_stay_id:
                start_journey_from_stay(
                    journey,
                    carried_stay_id,
                    kind_of=_pin_kind,
                    extra_stay_ids=resolved_stay_ids[1:],
                )
            route_ids = journey.route_ids
            ids = journey.map_pin_ids if journey.detached_pin_ids else route_ids
        else:
            stay_ids = _active_stay_ids(
                trip, itinerary_days, pin_for_stop, d, selected_stay_ids
            )
            ids = _local_day_pin_ids(ids, pin_by_id, resolved_stay_ids, stay_ids)
            route_ids = [pid for pid in ids if pin_by_id[pid]["kind"] not in TERMINAL_KINDS]
        intercity_modes = journey.intercity_edges or None
        legs = _route_legs_for_day(
            route_ids,
            pin_by_id,
            intercity_modes,
            journey.circuit_edges or None,
            transfer_metrics,
        )
        days.append(
            {
                "day": d,
                "label": f"Day {d}",
                "context_name": str((itinerary_days.get(d) or {}).get("title") or destination),
                "color": _day_color(d),
                "pin_ids": ids,
                "circuit_pin_ids": frame_pin_ids(
                    route_ids, journey.intercity_edges, kind_of=_pin_kind
                ),
                "route": _day_route_summary(route_ids, pin_by_id, intercity_modes, legs),
                "legs": legs,
            }
        )
    for day in days:
        itinerary_day = itinerary_days.get(int(day["day"]))
        if itinerary_day:
            day["schedule"] = itinerary_day.get("schedule")
    return days


def _circuit_waypoints(
    circuit_pin_ids: list[str], pin_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    return [
        {
            "pin_id": pin_id,
            "role": (
                "origin"
                if index == 0
                else "destination"
                if index == len(circuit_pin_ids) - 1
                else "meal"
                if pin_by_id[pin_id]["kind"] in {"meal", "restaurant"}
                else "scenic"
            ),
        }
        for index, pin_id in enumerate(circuit_pin_ids)
    ]


def _build_road_circuits(
    trip: dict[str, Any],
    transfer_metrics: dict[str, dict[str, float]],
    days: list[dict[str, Any]],
    pin_by_id: dict[str, dict[str, Any]],
    pin_for_stop: PinResolver,
    itinerary_days: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the drive/bus circuits the frontend renders as road polylines."""
    road_circuits: list[dict[str, Any]] = []
    days_by_number = {int(day["day"]): day for day in days}
    for idx, entry in enumerate(trip.get("day_wise_itinerary") or []):
        if not isinstance(entry, dict) or not isinstance(entry.get("stops"), list):
            continue
        day_num = _day_number(entry, idx)
        normalized = _normalize_map_stops(entry["stops"])
        if not any(stop["mode"] in {"Drive", "Bus"} for stop in normalized):
            continue
        day = days_by_number.get(day_num)
        origin_fallbacks: list[str] = []
        carried_stay = _carried_stay_id(itinerary_days, pin_for_stop, day_num)
        if carried_stay:
            origin_fallbacks.append(carried_stay)
        if day and day["pin_ids"]:
            first_pin = pin_by_id.get(day["pin_ids"][0])
            if first_pin and first_pin["kind"] in {"hotel", "origin"}:
                origin_fallbacks.append(str(first_pin["id"]))
        for stop_index, stop in enumerate(normalized, start=1):
            mode = str(stop["mode"] or "")
            if mode not in {"Drive", "Bus"}:
                continue
            circuit_id = _route_circuit_id(day_num, stop_index, mode)
            ordered = _resolve_road_circuit_pin_ids(
                normalized, stop_index - 1, pin_for_stop, origin_fallbacks
            )
            if len(ordered) < 2:
                continue
            edges = list(zip(ordered, ordered[1:]))
            saved_metrics = transfer_metrics.get(circuit_id)
            legs = _route_legs_for_day(
                ordered,
                pin_by_id,
                intercity_modes={edge: mode for edge in edges},
                route_circuit_ids={edge: circuit_id for edge in edges},
                transfer_metrics={circuit_id: saved_metrics} if saved_metrics else None,
            )
            if not legs:
                continue
            distance = round(sum(float(leg["distance_km"]) for leg in legs), 1)
            duration = sum(int(leg["duration_min"]) for leg in legs)
            circuit_pin_ids = [legs[0]["from_pin_id"], *(leg["to_pin_id"] for leg in legs)]
            road_circuits.append(
                {
                    "id": circuit_id,
                    "day": day_num,
                    "mode": mode,
                    "label": str(stop["name"] or mode),
                    "pin_ids": circuit_pin_ids,
                    "waypoints": _circuit_waypoints(circuit_pin_ids, pin_by_id),
                    "legs": legs,
                    "route": {
                        "distance_km": distance,
                        "duration_min": duration,
                        "mode": mode,
                        "distance_display": f"{distance:.1f} km",
                        "duration_display": _route_duration_display(duration),
                    },
                }
            )
    return road_circuits


def _map_center(
    pins: list[dict[str, Any]], airport: dict[str, Any] | None
) -> dict[str, float] | None:
    """Average of all pin coords for an initial viewport.

    The frontend fits bounds precisely once it has the pins.
    """
    coords = [(p["lat"], p["lng"]) for p in pins]
    if airport:
        coords.append((airport["lat"], airport["lng"]))
    if not coords:
        return None
    return {
        "lat": sum(c[0] for c in coords) / len(coords),
        "lng": sum(c[1] for c in coords) / len(coords),
    }


def build(
    trip: dict[str, Any],
    destination: str,
    pins: list[dict[str, Any]],
    airport: dict[str, Any] | None,
    itinerary_days: dict[int, dict[str, Any]],
    key_configured: bool,
    unmapped_stops: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the map view-model from pins the caller already resolved."""
    _annotate_pin_occurrences(trip, pins, itinerary_days)
    pin_for_stop = _build_pin_resolver(pins)
    # Structured days are authoritative and may reuse the same place on multiple
    # days. A pin has one primary day for display, while day routes can
    # reference it wherever the itinerary includes it. ``day_journey`` owns what
    # a transfer day is; here we only collect the pins it puts on the map.
    journeys, transfer_metrics = plan_day_journeys(
        trip.get("day_wise_itinerary"), resolve_pin=pin_for_stop
    )
    by_day: dict[int, list[str]] = {}
    for day_num, journey in journeys.items():
        if not journey.map_pin_ids:
            continue
        day_ids = by_day.setdefault(day_num, [])
        for pin_id in journey.map_pin_ids:
            if pin_id not in day_ids:
                day_ids.append(pin_id)

    unscheduled: list[str] = []
    for p in pins:
        if p["day"]:
            day_ids = by_day.setdefault(p["day"], [])
            if p["id"] not in day_ids:
                day_ids.append(p["id"])
        else:
            unscheduled.append(p["id"])

    pin_by_id = {p["id"]: p for p in pins}
    days = _build_days(
        journeys,
        transfer_metrics,
        by_day,
        pins,
        pin_by_id,
        pin_for_stop,
        itinerary_days,
        destination,
        trip,
    )
    road_circuits = _build_road_circuits(
        trip, transfer_metrics, days, pin_by_id, pin_for_stop, itinerary_days
    )

    scheduled_ids = {pin_id for day in days for pin_id in day["pin_ids"]}
    unscheduled = [pin_id for pin_id in unscheduled if pin_id not in scheduled_ids]
    center = _map_center(pins, airport)
    for pin in pins:
        pin["source_name"] = str(pin.pop("_source_name", "") or pin["name"])

    return {
        "enabled": key_configured,
        "destination": destination,
        "center": center,
        "pins": pins,
        "days": days,
        "road_circuits": road_circuits,
        "drive_circuits": [
            circuit for circuit in road_circuits if circuit["mode"] == "Drive"
        ],
        "available_days": [
            int(day.get("day") or index + 1)
            for index, day in enumerate(trip.get("day_wise_itinerary") or [])
            if isinstance(day, dict)
        ],
        "unscheduled_pin_ids": unscheduled,
        "unmapped_stops": unmapped_stops or [],
        "airport": airport,
        "empty_message": None if pins else (
            "No mappable places yet. Pick hotels and attractions and they'll "
            "appear pinned by day on the map."
        ),
    }
