"""Google Routes API (v2) — day-by-day travel time and route optimization.

Backs the agent's "Travel time between spots" line in itinerary builds with
real numbers instead of guesses, and reorders a day's stops to minimize travel
time when asked.

Reuses GOOGLE_PLACES_API_KEY (same Maps Platform key — just enable the
"Routes API" on the same Cloud project).
Docs: https://developers.google.com/maps/documentation/routes/compute_route_directions
"""

from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool

from tripplanner import http_client
from tripplanner.config import get_settings
from tripplanner.providers.cache import ProviderTTLCache
from tripplanner.providers.openrouteservice import OpenRouteServiceError, OpenRouteServiceProvider

_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

_VALID_MODES = {"DRIVE", "WALK", "BICYCLE", "TRANSIT", "TWO_WHEELER"}
_ORS_ROUTE_CACHE: ProviderTTLCache[dict] = ProviderTTLCache("ors-route")


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_places_api_key or settings.openrouteservice_api_key)


def _google_configured() -> bool:
    return bool(get_settings().google_places_api_key)


def _ors_configured() -> bool:
    return bool(get_settings().openrouteservice_api_key)


def _normalize_mode(mode: str) -> str:
    m = (mode or "DRIVE").strip().upper()
    return m if m in _VALID_MODES else "DRIVE"


def _waypoint(stop: str | dict) -> dict:
    """Accept either a free-form address string or {address|place_id|lat,lng}."""
    if isinstance(stop, str):
        return {"address": stop}
    if not isinstance(stop, dict):
        return {"address": str(stop)}
    if stop.get("place_id"):
        return {"placeId": stop["place_id"]}
    if "lat" in stop and "lng" in stop:
        return {"location": {"latLng": {"latitude": stop["lat"], "longitude": stop["lng"]}}}
    return {"address": stop.get("address") or stop.get("name") or json.dumps(stop)}


def _parse_stops(stops_json: str) -> list:
    try:
        data = json.loads(stops_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"stops_json is not valid JSON: {e}") from e
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError("stops_json must be a JSON array with at least 2 stops.")
    return data


def _seconds_to_human(value) -> str:
    """Routes API returns durations like '1234s'. Convert to '20m', '1h 5m'."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        secs = int(value)
    else:
        s = str(value).rstrip("sS")
        try:
            secs = int(float(s))
        except ValueError:
            return str(value)
    if secs < 60:
        return f"{secs}s"
    mins, secs = divmod(secs, 60)
    if mins < 60:
        return f"{mins}m"
    hours, mins = divmod(mins, 60)
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def _meters_to_human(meters) -> str:
    if meters is None:
        return ""
    try:
        m = int(meters)
    except (TypeError, ValueError):
        return str(meters)
    if m < 1000:
        return f"{m} m"
    return f"{m / 1000:.1f} km"


def _post_routes(payload: dict, field_mask: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": get_settings().google_places_api_key,
        "X-Goog-FieldMask": field_mask,
    }
    resp = http_client.post(_ENDPOINT, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()


def _build_route_payload(stops: list, mode: str, *, optimize: bool) -> dict:
    origin = _waypoint(stops[0])
    destination = _waypoint(stops[-1])
    intermediates = [_waypoint(s) for s in stops[1:-1]]
    payload: dict = {
        "origin": origin,
        "destination": destination,
        "travelMode": _normalize_mode(mode),
    }
    if intermediates:
        payload["intermediates"] = intermediates
        if optimize:
            payload["optimizeWaypointOrder"] = True
    if _normalize_mode(mode) == "DRIVE":
        payload["routingPreference"] = "TRAFFIC_AWARE"
    return payload


def _format_legs(route: dict, stop_labels: list[str]) -> list[dict]:
    legs_out = []
    for i, leg in enumerate(route.get("legs", []) or []):
        from_label = stop_labels[i] if i < len(stop_labels) else f"stop {i}"
        to_label = stop_labels[i + 1] if i + 1 < len(stop_labels) else f"stop {i + 1}"
        legs_out.append({
            "from": from_label,
            "to": to_label,
            "duration": _seconds_to_human(leg.get("duration")),
            "distance": _meters_to_human(leg.get("distanceMeters")),
        })
    return legs_out


def _stop_label(stop: str | dict) -> str:
    if isinstance(stop, str):
        return stop
    if isinstance(stop, dict):
        return stop.get("name") or stop.get("address") or stop.get("place_id") or json.dumps(stop)
    return str(stop)


def _coordinate_stops(stops: list) -> list[tuple[float, float]] | None:
    coordinates: list[tuple[float, float]] = []
    for stop in stops:
        if not isinstance(stop, dict) or "lat" not in stop or "lng" not in stop:
            return None
        try:
            coordinates.append((float(stop["lat"]), float(stop["lng"])))
        except (TypeError, ValueError):
            return None
    return coordinates


def _ors_route(stops: list, mode: str) -> dict | None:
    coordinates = _coordinate_stops(stops)
    if not coordinates or not _ors_configured():
        return None
    normalized_mode = _normalize_mode(mode)
    if normalized_mode not in {"DRIVE", "WALK", "BICYCLE"}:
        return None
    settings = get_settings()
    cache_key = json.dumps({"coordinates": coordinates, "mode": normalized_mode})
    cached = _ORS_ROUTE_CACHE.get(cache_key)
    if cached:
        return cached.value
    provider = OpenRouteServiceProvider(
        settings.openrouteservice_api_key,
        settings.openrouteservice_base_url,
    )
    try:
        route = provider.compute_route(coordinates, normalized_mode)
    except OpenRouteServiceError:
        return None
    summary = route.get("summary") or {}
    legs = [
        {"duration": segment.get("duration"), "distanceMeters": segment.get("distance")}
        for segment in route.get("segments") or []
    ]
    normalized = {
        "duration": summary.get("duration"),
        "distanceMeters": summary.get("distance"),
        "legs": legs,
        "provider": provider.name,
    }
    _ORS_ROUTE_CACHE.set(
        cache_key,
        normalized,
        provider=provider.name,
        ttl_seconds=settings.openrouteservice_route_ttl_sec,
    )
    return normalized


@tool
def compute_route(stops_json: str, mode: str = "DRIVE") -> str:
    """Compute travel time and distance for an ordered list of stops.

    Use this when building a day itinerary to put real numbers on transitions
    ("hotel → Louvre: 22m walk, 1.8 km") instead of guessing.

    Args:
        stops_json: JSON array of stops, IN THE ORDER you want to visit them.
            Each stop can be:
              - a string address: "Hotel Lutetia, Paris"
              - {"name": "Louvre", "address": "Rue de Rivoli, 75001 Paris"}
              - {"place_id": "ChIJ..."}  (from search_places_with_reviews)
              - {"lat": 48.86, "lng": 2.34}
            Minimum 2 stops; up to 25.
        mode: DRIVE | WALK | BICYCLE | TRANSIT | TWO_WHEELER. Default DRIVE.

    Returns JSON with total_duration, total_distance, and per-leg breakdown.
    """
    if not is_configured():
        return (
            "Route provider not configured. Set GOOGLE_PLACES_API_KEY for Google Routes, "
            "or OPENROUTESERVICE_API_KEY for coordinate-based driving, walking, and cycling."
        )
    try:
        stops = _parse_stops(stops_json)
    except ValueError as e:
        return str(e)

    route: dict | None = None
    source = ""
    google_error = ""
    if _google_configured():
        payload = _build_route_payload(stops, mode, optimize=False)
        field_mask = (
            "routes.duration,routes.distanceMeters,"
            "routes.legs.duration,routes.legs.distanceMeters"
        )
        try:
            data = _post_routes(payload, field_mask)
            routes = data.get("routes") or []
            route = routes[0] if routes else None
            source = "google_routes" if route else ""
        except httpx.HTTPError as exc:
            google_error = type(exc).__name__
    if route is None:
        route = _ors_route(stops, mode)
        source = str(route.get("provider") or "") if route else ""
    if route is None:
        if google_error:
            return f"No route found after Google Routes failed ({google_error})."
        return "No route found for the supplied stops."
    labels = [_stop_label(s) for s in stops]
    out = {
        "mode": _normalize_mode(mode),
        "provider": source,
        "total_duration": _seconds_to_human(route.get("duration")),
        "total_distance": _meters_to_human(route.get("distanceMeters")),
        "legs": _format_legs(route, labels),
    }
    return json.dumps(out, indent=2)


def _seconds_to_minutes(value) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(str(value).rstrip("sS")) / 60))
    except (TypeError, ValueError):
        return None


def route_metrics(origin: str | dict, destination: str | dict, mode: str) -> dict | None:
    """Duration in minutes and distance in km for one origin → destination hop.

    Non-tool: transport comparison needs the numbers, not the formatted string
    ``compute_route`` hands to the model.
    """
    if not is_configured():
        return None
    stops = [origin, destination]
    route: dict | None = None
    source = ""
    if _google_configured():
        payload = _build_route_payload(stops, mode, optimize=False)
        try:
            data = _post_routes(payload, "routes.duration,routes.distanceMeters")
            routes = data.get("routes") or []
            route = routes[0] if routes else None
            source = "google_routes" if route else ""
        except httpx.HTTPError:
            route = None
    if route is None:
        route = _ors_route(stops, mode)
        source = str(route.get("provider") or "") if route else ""
    if route is None:
        return None
    minutes = _seconds_to_minutes(route.get("duration"))
    if minutes is None:
        return None
    meters = route.get("distanceMeters")
    return {
        "mode": _normalize_mode(mode),
        "provider": source,
        "duration_min": minutes,
        "distance_km": round(float(meters) / 1000, 1) if meters else None,
    }


@tool
def optimize_day_route(stops_json: str, mode: str = "DRIVE") -> str:
    """Reorder a day's intermediate stops to minimize total travel time.

    The FIRST and LAST stops are pinned (usually hotel → ... → hotel or
    hotel → dinner). All stops in between are reshuffled by Google.

    Use when the user has a bag of attractions to fit into one day and asks
    "what's the best order?" or you suspect their picked order is inefficient.

    Args:
        stops_json: JSON array; first = start (e.g. hotel), last = end, middle
            stops will be optimized. Same shape as compute_route. Need ≥ 3 stops
            for optimization to be meaningful.
        mode: DRIVE | WALK | BICYCLE | TRANSIT | TWO_WHEELER. Default DRIVE.

    Returns JSON with optimized_order (the new sequence of stop labels),
    total_duration, total_distance, and per-leg breakdown in the new order.
    """
    if not _google_configured():
        return (
            "Google Routes API not configured. Waypoint optimization requires Google Routes; "
            "OpenRouteService is available only as a coordinate route fallback."
        )
    try:
        stops = _parse_stops(stops_json)
    except ValueError as e:
        return str(e)
    if len(stops) < 3:
        return (
            "Need at least 3 stops to optimize order (first and last are "
            "pinned). Use compute_route instead."
        )

    payload = _build_route_payload(stops, mode, optimize=True)
    field_mask = (
        "routes.duration,routes.distanceMeters,"
        "routes.optimizedIntermediateWaypointIndex,"
        "routes.legs.duration,routes.legs.distanceMeters"
    )
    try:
        data = _post_routes(payload, field_mask)
    except httpx.HTTPError as e:
        return f"Routes API call failed: {e}"

    routes = data.get("routes") or []
    if not routes:
        return "No route found for the supplied stops."
    route = routes[0]

    intermediates = stops[1:-1]
    optimized_idx = route.get("optimizedIntermediateWaypointIndex") or list(
        range(len(intermediates))
    )
    reordered_intermediates = [
        intermediates[index]
        for index in optimized_idx
        if 0 <= index < len(intermediates)
    ]
    new_order = [stops[0], *reordered_intermediates, stops[-1]]
    labels = [_stop_label(s) for s in new_order]

    out = {
        "mode": _normalize_mode(mode),
        "optimized_order": labels,
        "total_duration": _seconds_to_human(route.get("duration")),
        "total_distance": _meters_to_human(route.get("distanceMeters")),
        "legs": _format_legs(route, labels),
    }
    return json.dumps(out, indent=2)

