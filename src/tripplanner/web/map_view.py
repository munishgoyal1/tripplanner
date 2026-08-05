"""Assembly of the interactive-map view-model from already-resolved pins.

Split out of ``trip_view`` (tech-debt #7). ``trip_view.build_map_view`` remains
the public entry point and keeps ownership of every data source that callers and
tests substitute (the browser Maps key, the airport pin, the place pins and the
itinerary); this module receives those as arguments and does only the pure
assembly of pins into day-colored routes and road circuits.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

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
from tripplanner.web.transport import (
    _canonical_transport_name,
    _intercity_transfer_mode,
    _normalized_stop_kind,
    _transport_terminal_refs,
)

_TERMINAL_KINDS = {"airport", "station", "bus_station"}

# Resolves an itinerary stop name (with an optional kind hint) to its map pin.
PinResolver = Callable[..., "dict[str, Any] | None"]


@dataclass
class _DayRoutes:
    """Per-day routing derived from the structured ``day_wise_itinerary``."""

    by_day: dict[int, list[str]] = field(default_factory=dict)
    route_pin_ids: dict[int, list[str]] = field(default_factory=dict)
    intercity_modes: dict[int, dict[tuple[str, str], str]] = field(default_factory=dict)
    route_circuit_ids: dict[int, dict[tuple[str, str], str]] = field(default_factory=dict)
    transfer_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    transfer_mode: dict[int, str] = field(default_factory=dict)
    transfer_days: set[int] = field(default_factory=set)


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
        elif pin["kind"] in _TERMINAL_KINDS:
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


def _scan_day_routes(trip: dict[str, Any], pin_for_stop: PinResolver) -> _DayRoutes:
    """Walk the structured itinerary once, collecting per-day route state.

    Structured days are authoritative and may reuse the same place on multiple
    days. A pin has one primary day for display, while day routes can reference
    it wherever the itinerary includes it.
    """
    routes = _DayRoutes()
    for idx, entry in enumerate(trip.get("day_wise_itinerary") or []):
        if not isinstance(entry, dict) or not isinstance(entry.get("stops"), list):
            continue
        day_num = _day_number(entry, idx)
        route_ids = routes.route_pin_ids.setdefault(day_num, [])
        pending_intercity_mode: str | None = None
        pending_route_circuit_id: str | None = None
        pending_bus_destination_id: str | None = None
        for stop_index, stop in enumerate(entry["stops"], start=1):
            name = stop.get("name") if isinstance(stop, dict) else stop
            kind = str(stop.get("kind") or "").strip().lower() if isinstance(stop, dict) else ""
            mode_name = str(stop.get("mode") or "") if isinstance(stop, dict) else ""
            name = _canonical_transport_name(str(name or ""), mode_name)
            kind = _normalized_stop_kind(str(name or ""), kind, mode_name)
            mode = _intercity_transfer_mode(str(name or ""), kind)
            if mode:
                if pending_bus_destination_id and route_ids:
                    edge = (route_ids[-1], pending_bus_destination_id)
                    routes.intercity_modes.setdefault(day_num, {})[edge] = "Bus"
                    if pending_route_circuit_id:
                        routes.route_circuit_ids.setdefault(day_num, {})[
                            edge
                        ] = pending_route_circuit_id
                    route_ids.append(pending_bus_destination_id)
                    pending_bus_destination_id = None
                    pending_intercity_mode = None
                    pending_route_circuit_id = None
                routes.transfer_days.add(day_num)
                routes.transfer_mode[day_num] = mode
                circuit_id = _route_circuit_id(day_num, stop_index, mode)
                if isinstance(stop, dict):
                    saved_metrics = {
                        metric: float(stop[metric])
                        for metric in ("distance_km", "duration_min")
                        if isinstance(stop.get(metric), (int, float)) and stop[metric] > 0
                    }
                    if saved_metrics:
                        routes.transfer_metrics[circuit_id] = saved_metrics
                terminal_refs = _transport_terminal_refs(str(name or ""), kind)
                terminal_ids: list[str] = []
                for terminal_kind, terminal_name in terminal_refs:
                    terminal_pin = pin_for_stop(terminal_name, terminal_kind)
                    if terminal_pin:
                        terminal_ids.append(str(terminal_pin["id"]))
                if len(terminal_ids) == len(terminal_refs) and len(terminal_ids) >= 2:
                    for terminal_id in terminal_ids:
                        if terminal_id not in routes.by_day.setdefault(day_num, []):
                            routes.by_day[day_num].append(terminal_id)
                    route_ids.append(terminal_ids[0])
                    if mode == "Bus":
                        pending_intercity_mode = mode
                        pending_route_circuit_id = circuit_id
                        pending_bus_destination_id = terminal_ids[-1]
                    else:
                        route_ids.append(terminal_ids[-1])
                        routes.intercity_modes.setdefault(day_num, {})[
                            (terminal_ids[0], terminal_ids[-1])
                        ] = mode
                        routes.route_circuit_ids.setdefault(day_num, {})[
                            (terminal_ids[0], terminal_ids[-1])
                        ] = circuit_id
                else:
                    if not route_ids and terminal_refs:
                        origin_pin = pin_for_stop(terminal_refs[0][1], terminal_refs[0][0])
                        if origin_pin:
                            origin_id = str(origin_pin["id"])
                            if origin_id not in routes.by_day.setdefault(day_num, []):
                                routes.by_day[day_num].append(origin_id)
                            route_ids.append(origin_id)
                    pending_intercity_mode = mode
                    pending_route_circuit_id = circuit_id
                continue
            if (
                pending_bus_destination_id
                and kind not in {"attraction", "meal", "restaurant"}
                and route_ids
            ):
                edge = (route_ids[-1], pending_bus_destination_id)
                routes.intercity_modes.setdefault(day_num, {})[edge] = "Bus"
                if pending_route_circuit_id:
                    routes.route_circuit_ids.setdefault(day_num, {})[
                        edge
                    ] = pending_route_circuit_id
                route_ids.append(pending_bus_destination_id)
                pending_bus_destination_id = None
                pending_intercity_mode = None
                pending_route_circuit_id = None
            pin = pin_for_stop(name, kind)
            if pin and pin["id"] not in routes.by_day.setdefault(day_num, []):
                routes.by_day[day_num].append(pin["id"])
            if pin:
                pin_id = str(pin["id"])
                if pending_intercity_mode and route_ids:
                    if pin["kind"] not in _TERMINAL_KINDS:
                        routes.intercity_modes.setdefault(day_num, {})[
                            (route_ids[-1], pin_id)
                        ] = pending_intercity_mode
                        if pending_route_circuit_id:
                            routes.route_circuit_ids.setdefault(day_num, {})[
                                (route_ids[-1], pin_id)
                            ] = pending_route_circuit_id
                    if pending_intercity_mode not in {"Drive", "Bus"} or pin["kind"] == "hotel":
                        pending_intercity_mode = None
                        pending_route_circuit_id = None
                route_ids.append(pin_id)
        if pending_bus_destination_id and route_ids:
            edge = (route_ids[-1], pending_bus_destination_id)
            routes.intercity_modes.setdefault(day_num, {})[edge] = "Bus"
            if pending_route_circuit_id:
                routes.route_circuit_ids.setdefault(day_num, {})[
                    edge
                ] = pending_route_circuit_id
            route_ids.append(pending_bus_destination_id)
    return routes


def _occurrence_stop(pin_by_id: dict[str, dict[str, Any]], pin_id: str, day: int) -> int:
    pin = pin_by_id[pin_id]
    occurrence = next(
        (item for item in pin.get("occurrences") or [] if item.get("day") == day),
        None,
    )
    return int(occurrence.get("stop")) if occurrence and occurrence.get("stop") else 10_000


def _local_pin_ids(
    pin_by_id: dict[str, dict[str, Any]],
    intercity_edges: dict[tuple[str, str], str],
    route_ids: list[str],
) -> list[str]:
    """Trim a day's route to the leg that is walkable/local, if there is one."""
    if "Drive" in intercity_edges.values():
        return route_ids
    edge_indexes = next(
        (
            (route_ids.index(start_id), route_ids.index(end_id))
            for start_id, end_id in intercity_edges
            if start_id in route_ids and end_id in route_ids
        ),
        None,
    )
    if not edge_indexes:
        return route_ids
    start_index, end_index = edge_indexes
    destination_ids = route_ids[end_index:]
    has_destination_stop = any(
        pin_by_id[pin_id]["kind"] not in _TERMINAL_KINDS for pin_id in destination_ids
    )
    return destination_ids if has_destination_stop else route_ids[: start_index + 1]


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


def _rebase_edges_to_stay(
    edges_by_day: dict[int, dict[tuple[str, str], Any]],
    day: int,
    origin_id: str,
    carried_stay_id: str,
) -> None:
    """Re-anchor a day's edges from a dropped origin pin onto the carried stay."""
    edges = edges_by_day.get(day) or {}
    replacements = {
        (carried_stay_id, end_id): value
        for (start_id, end_id), value in edges.items()
        if start_id == origin_id
    }
    if not replacements:
        return
    edges_by_day.setdefault(day, {}).update(replacements)
    edges_by_day[day] = {
        edge: value for edge, value in edges_by_day[day].items() if edge[0] != origin_id
    }


def _transfer_day_route_ids(
    routes: _DayRoutes,
    itinerary_days: dict[int, dict[str, Any]],
    pin_by_id: dict[str, dict[str, Any]],
    pin_for_stop: PinResolver,
    day: int,
    resolved_stay_ids: list[str],
) -> list[str]:
    route_ids = routes.route_pin_ids.get(day, [])
    carried_stay_id = _carried_stay_id(itinerary_days, pin_for_stop, day)
    if not carried_stay_id:
        return route_ids
    if route_ids and pin_by_id[route_ids[0]]["kind"] == "origin":
        origin_id = route_ids.pop(0)
        _rebase_edges_to_stay(routes.intercity_modes, day, origin_id, carried_stay_id)
        _rebase_edges_to_stay(routes.route_circuit_ids, day, origin_id, carried_stay_id)
    route_ids = [
        carried_stay_id,
        *(pin_id for pin_id in route_ids if pin_id != carried_stay_id),
    ]
    if len(route_ids) >= 2:
        first_edge = (route_ids[0], route_ids[1])
        routes.intercity_modes.setdefault(day, {}).setdefault(
            first_edge, routes.transfer_mode[day]
        )
    for resolved_stay_id in resolved_stay_ids[1:]:
        if resolved_stay_id not in route_ids:
            route_ids.append(resolved_stay_id)
    return route_ids


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
    routes: _DayRoutes,
    pins: list[dict[str, Any]],
    pin_by_id: dict[str, dict[str, Any]],
    pin_for_stop: PinResolver,
    itinerary_days: dict[int, dict[str, Any]],
    destination: str,
) -> list[dict[str, Any]]:
    stay_ids = [p["id"] for p in pins if p["kind"] == "hotel" and p["selected"]]
    days: list[dict[str, Any]] = []
    for d in sorted(routes.by_day):
        ids = sorted(routes.by_day[d], key=lambda pin_id: _occurrence_stop(pin_by_id, pin_id, d))
        is_transfer_day = d in routes.transfer_days
        resolved_stay_ids = _resolved_stay_ids(itinerary_days, pin_for_stop, d)
        if is_transfer_day:
            route_ids = _transfer_day_route_ids(
                routes, itinerary_days, pin_by_id, pin_for_stop, d, resolved_stay_ids
            )
            ids = route_ids
        else:
            ids = _local_day_pin_ids(ids, pin_by_id, resolved_stay_ids, stay_ids)
            route_ids = [pid for pid in ids if pin_by_id[pid]["kind"] not in _TERMINAL_KINDS]
        intercity_modes = routes.intercity_modes.get(d)
        legs = _route_legs_for_day(
            route_ids,
            pin_by_id,
            intercity_modes,
            routes.route_circuit_ids.get(d),
            routes.transfer_metrics,
        )
        days.append(
            {
                "day": d,
                "label": f"Day {d}",
                "context_name": str((itinerary_days.get(d) or {}).get("title") or destination),
                "color": _day_color(d),
                "pin_ids": ids,
                "circuit_pin_ids": _local_pin_ids(
                    pin_by_id, routes.intercity_modes.get(d) or {}, route_ids
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
    routes: _DayRoutes,
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
            saved_metrics = routes.transfer_metrics.get(circuit_id)
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
) -> dict[str, Any]:
    """Assemble the map view-model from pins the caller already resolved."""
    _annotate_pin_occurrences(trip, pins, itinerary_days)
    pin_for_stop = _build_pin_resolver(pins)
    routes = _scan_day_routes(trip, pin_for_stop)

    unscheduled: list[str] = []
    for p in pins:
        if p["day"]:
            day_ids = routes.by_day.setdefault(p["day"], [])
            if p["id"] not in day_ids:
                day_ids.append(p["id"])
        else:
            unscheduled.append(p["id"])

    pin_by_id = {p["id"]: p for p in pins}
    days = _build_days(routes, pins, pin_by_id, pin_for_stop, itinerary_days, destination)
    road_circuits = _build_road_circuits(
        trip, routes, days, pin_by_id, pin_for_stop, itinerary_days
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
        "airport": airport,
        "empty_message": None if pins else (
            "No mappable places yet. Pick hotels and attractions and they'll "
            "appear pinned by day on the map."
        ),
    }
