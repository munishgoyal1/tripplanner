"""Structured itinerary view-model assembly.

Split out of ``trip_view`` (tech-debt #7). ``trip_view._place_coords`` remains
the substitutable geocoding seam; this module lazy-delegates to it so tests that
patch ``trip_view._place_coords`` still apply. ``places_cache`` attribute patches
on the shared module object continue to apply because both modules import the
same cache module.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any
from urllib.parse import quote

from tripplanner import place_facts
from tripplanner.web import places_cache
from tripplanner.web.budget import _PRICE_KEYS, _to_number, currency_symbol, fmt_money
from tripplanner.web.day_journey import implied_terminal_hop_mode
from tripplanner.web.gallery import _selected_names
from tripplanner.web.map_pins import (
    _day_color,
    _local_route_stop_indexes,
    _route_circuit_id,
    _route_stats_for_day_coords,
    _trip_day_count,
)
from tripplanner.web.schedule import (
    _apply_hotel_endpoint_times,
    _clock_display,
    _clock_minutes,
    _day_schedule,
    _enrich_drive_transfer_timing,
    _enrich_stop_timing,
    _haversine_km,
    _route_duration_display,
    _route_stats_for_distance,
)
from tripplanner.web.transport import (
    _canonical_transport_name,
    _intercity_transfer_mode,
    _normalized_stop_kind,
    _resolved_transfer_mode,
    _transport_terminal_refs,
)


def _place_coords(name: str, destination: str) -> tuple[float, float] | None:
    from tripplanner.web import trip_view

    return trip_view._place_coords(name, destination)


def build_weather(trip: dict[str, Any] | None) -> dict[str, Any] | None:
    from tripplanner.web import trip_view

    return trip_view.build_weather(trip)


def get_settings():
    from tripplanner.web import trip_view

    return trip_view.get_settings()


# ---------------------------------------------------------------------------
# structured itinerary view-model (no network) — drives the Itinerary tab,
# cross-references selections + per-stop booked flags so each stop is clickable
# (focus its photos) and reflects what's booked.
# ---------------------------------------------------------------------------

# A stop's "kind" decides its chip + whether it can load place photos.
_STOP_KINDS = {
    "hotel", "airport", "origin", "attraction", "flight", "meal", "restaurant",
    "transport", "other"
}
_DEFAULT_STOP_DURATION_MIN = {
    "hotel": 45,
    "attraction": 120,
    "meal": 60,
    "transport": 30,
    "flight": 90,
    "other": 60,
}
_PRICE_LEVEL_HINT = {
    "PRICE_LEVEL_INEXPENSIVE": "Budget",
    "PRICE_LEVEL_MODERATE": "Mid-range",
    "PRICE_LEVEL_EXPENSIVE": "Premium",
    "PRICE_LEVEL_VERY_EXPENSIVE": "Luxury",
}
# Bands are per currency, because 6,000-15,000 a night is an ordinary hotel in
# rupees and a yacht in euros. A currency with no band shows nothing at all: an
# absent guess is honest, a wrongly scaled one is not.
_COST_HINT_BANDS = {
    "\u20b9": {
        "meal": "500-1,500 pp",
        "attraction": "300-1,200 tickets",
        "hotel": "6,000-15,000 / night",
    },
    "\u20ac": {
        "meal": "15-40 pp",
        "attraction": "8-25 tickets",
        "hotel": "90-220 / night",
    },
    "$": {
        "meal": "18-45 pp",
        "attraction": "10-30 tickets",
        "hotel": "110-260 / night",
    },
    "\u00a3": {
        "meal": "15-40 pp",
        "attraction": "10-28 tickets",
        "hotel": "95-230 / night",
    },
}


def _infer_stop_kind(name: str, hotels: set[str], activities: set[str]) -> str:
    n = (name or "").strip().lower()
    if n in hotels:
        return "hotel"
    if n in activities:
        return "attraction"
    return "attraction"


def _normalize_stop(
    raw: Any, hotels: set[str], activities: set[str]
) -> dict[str, Any] | None:
    """Turn a raw stop (str or dict) into the structured stop view-model."""
    if isinstance(raw, str):
        name = raw.strip()
        if not name:
            return None
        kind = _infer_stop_kind(name, hotels, activities)
        return {
            "name": name,
            "kind": kind,
            "time": "",
            "duration_min": None,
            "note": "",
            "booked": False,
            "selected": name.lower() in (hotels if kind == "hotel" else activities),
            "opening_hours": "",
            "cost_display": "",
            "insight": "",
            "concern": "",
        }
    if isinstance(raw, dict):
        name = str(raw.get("name") or "").strip()
        if not name:
            return None
        name = _canonical_transport_name(name, str(raw.get("mode") or ""))
        kind = _normalized_stop_kind(
            name, str(raw.get("kind") or ""), str(raw.get("mode") or "")
        )
        if kind not in _STOP_KINDS:
            kind = _infer_stop_kind(name, hotels, activities)
        dur = raw.get("duration_min")
        distance = raw.get("distance_km")
        return {
            "name": name,
            "kind": kind,
            "time": str(raw.get("time") or "").strip(),
            "arrival_time": str(raw.get("arrival_time") or "").strip(),
            "duration_min": dur if isinstance(dur, (int, float)) else None,
            "distance_km": distance if isinstance(distance, (int, float)) else None,
            "note": str(raw.get("note") or "").strip(),
            "booked": bool(raw.get("booked")),
            "booking_ref": str(raw.get("booking_ref") or raw.get("confirmation") or "").strip(),
            "ticket_url": str(raw.get("ticket_url") or "").strip(),
            "selected": name.lower()
            in (hotels if kind == "hotel" else activities),
            "opening_hours": str(raw.get("opening_hours") or "").strip(),
            "cost_display": str(raw.get("cost_display") or "").strip(),
            "insight": str(raw.get("insight") or "").strip(),
            "concern": str(raw.get("concern") or "").strip(),
        }
    return None


def _transport_terminal_stops(stop: dict[str, Any]) -> list[dict[str, Any]]:
    terminal_refs = _transport_terminal_refs(stop["name"], stop["kind"])
    mode = _intercity_transfer_mode(stop["name"], stop["kind"])
    if len(terminal_refs) < 2 or mode not in {"Flight", "Train", "Bus"}:
        return [stop]

    settings = get_settings()
    departure = str(stop.get("time") or "")
    arrival = str(stop.get("arrival_time") or "")
    duration = stop.get("duration_min")
    if mode == "Flight" and (not isinstance(duration, (int, float)) or duration <= 0):
        duration = settings.flight_duration_default_min
        stop["duration_min"] = duration
        stop["duration_estimated"] = True

    departure_minutes = _clock_minutes(departure)
    arrival_estimated = False
    if (
        not arrival
        and departure_minutes is not None
        and isinstance(duration, (int, float))
        and duration > 0
    ):
        arrival = _clock_display(departure_minutes + int(duration))
        stop["arrival_time"] = arrival
        stop["arrival_time_estimated"] = True
        stop["concern"] = stop.get("concern") or (
            "Arrival time estimated; verify the local arrival time with the airline."
        )
        arrival_estimated = True

    if mode == "Flight":
        departure_buffer = settings.airport_departure_buffer_min
        arrival_buffer = settings.airport_arrival_buffer_min
        departure_operation = "check-in and security"
        arrival_operation = "baggage and airport exit"
    elif mode == "Train":
        departure_buffer = settings.railway_departure_buffer_min
        arrival_buffer = settings.railway_arrival_buffer_min
        departure_operation = "baggage and boarding"
        arrival_operation = "disembark and baggage"
    else:
        departure_buffer = settings.bus_departure_buffer_min
        arrival_buffer = settings.bus_arrival_buffer_min
        departure_operation = "baggage and boarding"
        arrival_operation = "disembark and baggage"

    def _terminal_stop(
        name: str,
        kind: str,
        time: str,
        role: str,
        duration_min: int | None,
        time_estimated: bool,
    ) -> dict[str, Any]:
        operation = (
            departure_operation
            if role == "departure"
            else arrival_operation
            if role == "arrival"
            else "connection; layover time not provided"
        )
        return {
            "name": name,
            "kind": kind,
            "time": time,
            "arrival_time": "",
            "duration_min": duration_min,
            "duration_estimated": duration_min is not None,
            "operational_time_display": (
                f"{_route_duration_display(duration_min)} {operation}"
                if duration_min is not None
                else operation
            ),
            "time_estimated": time_estimated,
            "note": "",
            "booked": False,
            "selected": False,
            "opening_hours": "",
            "cost_display": "",
            "insight": "",
            "concern": "",
            "terminal_role": role,
        }

    connection_names = [name for _, name in terminal_refs[1:-1]]
    stop["name"] = f"{mode}: {terminal_refs[0][1]} to {terminal_refs[-1][1]}"
    if connection_names:
        stop["name"] += f" via {', '.join(connection_names)}"
    departure_terminal_time = (
        _clock_display(departure_minutes - departure_buffer)
        if departure_minutes is not None
        else ""
    )
    return [
        _terminal_stop(
            terminal_refs[0][1],
            terminal_refs[0][0],
            departure_terminal_time,
            "departure",
            departure_buffer,
            bool(departure_terminal_time),
        ),
        stop,
        *[
            _terminal_stop(
                connection_name,
                connection_kind,
                "",
                "connection",
                None,
                False,
            )
            for connection_kind, connection_name in terminal_refs[1:-1]
        ],
        _terminal_stop(
            terminal_refs[-1][1],
            terminal_refs[-1][0],
            arrival,
            "arrival",
            arrival_buffer,
            arrival_estimated,
        ),
    ]


def _road_origin_stop(stop: dict[str, Any]) -> dict[str, Any] | None:
    if _resolved_transfer_mode(stop["name"], stop["kind"]) != "Drive":
        return None
    refs = _transport_terminal_refs(stop["name"], stop["kind"])
    if len(refs) != 1:
        return None
    return {
        "name": refs[0][1],
        "kind": "origin",
        "time": str(stop.get("time") or ""),
        "arrival_time": "",
        "duration_min": None,
        "note": "Road journey starts here",
        "booked": False,
        "selected": False,
        "opening_hours": "",
        "cost_display": "",
        "insight": "",
        "concern": "",
    }


def _selected_price_map(trip: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in ("selected_hotels", "selected_activities"):
        for item in (trip or {}).get(key) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip().lower()
            if not name:
                continue
            for price_key in _PRICE_KEYS:
                if price_key not in item:
                    continue
                value = _to_number(item.get(price_key))
                if value > 0:
                    out[name] = value
                    break
    return out


def _first_sentence(text: Any) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", s)
    return parts[0][:180].strip()


def _weekday_name(day_iso: str) -> str:
    text = str(day_iso or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text).strftime("%A")
    except ValueError:
        return ""


def _opening_hint(summary: dict[str, Any], day_iso: str) -> tuple[str, str]:
    """The hours line to show, and the worry to raise, from the same facts.

    The concern here is the soft, always-visible half. Anything it can state as
    a fact is also an invariant in ``trip_guard``, so the itinerary is corrected
    rather than merely annotated.
    """
    weekday_lines = summary.get("weekday_descriptions") or []
    facts = place_facts.facts_from_summary(summary)
    day_name = _weekday_name(day_iso)

    matched = ""
    if day_name and isinstance(weekday_lines, list):
        prefix = day_name.lower() + ":"
        for line in weekday_lines:
            text = str(line or "").strip()
            if text.lower().startswith(prefix):
                matched = text
                break

    opening = matched
    if not opening and facts.open_now is True:
        opening = "Open now"
    elif not opening and facts.open_now is False:
        opening = "May be closed now"

    concern = ""
    if facts.unavailable:
        concern = "Reported closed for business; replace this stop."
    elif facts.closed_on(day_iso) and day_name:
        concern = f"Closed on {day_name}s; move this to another day."
    elif facts.open_now is False:
        concern = "Check opening hours before visiting."
    return opening, concern


def _cost_hint(kind: str, summary: dict[str, Any], selected_price: float, symbol: str) -> str:
    if selected_price > 0:
        return fmt_money(selected_price, symbol)

    level = str(summary.get("price_level") or "").strip().upper()
    if level in _PRICE_LEVEL_HINT:
        return _PRICE_LEVEL_HINT[level]

    band = _COST_HINT_BANDS.get(symbol, {}).get(kind, "")
    return f"{symbol}{band} (est.)" if band else ""


def _duration_hint(kind: str, duration_min: Any) -> int:
    if isinstance(duration_min, (int, float)) and duration_min > 0:
        return int(round(float(duration_min)))
    return _DEFAULT_STOP_DURATION_MIN.get(kind, 60)


def _insight_hint(name: str, kind: str, summary: dict[str, Any]) -> str:
    text = _first_sentence(summary.get("editorial_summary"))
    if text:
        return text
    if kind == "hotel":
        return f"{name} is a practical base for nearby sights."
    if kind == "meal":
        return f"{name} is a convenient meal break near your route."
    return f"{name} is a popular stop to include in this day circuit."


def _popularity_score(summary: dict[str, Any]) -> int | None:
    rating = summary.get("rating")
    review_count = summary.get("review_count")
    if not isinstance(rating, (int, float)) or rating <= 0:
        return None
    rating_points = min(float(rating), 5.0) / 5.0 * 75
    volume = int(review_count) if isinstance(review_count, (int, float)) else 0
    volume_points = min(math.log10(max(volume, 1)) / 5.0, 1.0) * 25
    return int(round(rating_points + volume_points))


def _reachability_hint(stops: list[dict[str, Any]], route: dict[str, Any]) -> str:
    names = [str(s.get("name") or "").strip() for s in stops if str(s.get("name") or "").strip()]
    if len(names) < 2:
        return ""

    first = names[0]
    second = names[1]
    mode = str(route.get("mode") or "").strip().lower()
    if mode == "walk":
        return f"Start at {first}, then walk to {second}; most stops are in a compact area."
    if mode == "metro":
        return (
            f"Take the Metro from near {first} toward {second}; use the nearest stations "
            "and walk the short connections."
        )
    if mode == "taxi":
        return f"Take a taxi from {first} to {second}, then continue the circuit by taxi."
    return f"Use {route.get('mode')} between {first}, {second}, and the remaining stops."


def _google_travel_mode(route_mode: str) -> str:
    mode = str(route_mode or "").strip().lower()
    if mode == "walk":
        return "walking"
    if mode == "metro":
        return "transit"
    return "driving"


def _google_maps_day_url(
    destination: str,
    stops: list[dict[str, Any]],
    route_mode: str,
) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for stop in stops:
        name = str(stop.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)

    if not names:
        return ""

    if len(names) == 1:
        query = f"{names[0]}, {destination}".strip().strip(",")
        return "https://www.google.com/maps/search/?api=1&query=" + quote(query, safe="")

    origin = f"{names[0]}, {destination}".strip().strip(",")
    dest = f"{names[-1]}, {destination}".strip().strip(",")
    url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote(origin, safe='')}"
        f"&destination={quote(dest, safe='')}"
        f"&travelmode={quote(_google_travel_mode(route_mode), safe='')}"
    )
    waypoints = names[1:-1][:8]
    if waypoints:
        waypoint_text = "|".join(f"{w}, {destination}".strip().strip(",") for w in waypoints)
        url += f"&waypoints={quote(waypoint_text, safe='')}"
    return url


def _ordered_selected(trip: dict[str, Any] | None, key: str) -> list[str]:
    """Display-cased selected names for a bucket, in selection order, deduped."""
    out: list[str] = []
    seen: set[str] = set()
    for it in (trip or {}).get(key) or []:
        name = ""
        if isinstance(it, dict):
            name = str(it.get("name") or "").strip()
        elif isinstance(it, str):
            name = it.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out




def _nearest_neighbor_order(
    names: list[str],
    coords: dict[str, tuple[float, float]],
    start: tuple[float, float] | None,
) -> list[str]:
    """Greedy nearest-neighbor ordering so consecutive stops are geographically
    close. Names without coordinates keep their original relative order and are
    appended after the geo-ordered ones."""
    placed = [n for n in names if n in coords]
    unplaced = [n for n in names if n not in coords]
    if not placed:
        return list(names)
    ordered: list[str] = []
    remaining = placed[:]
    cur = start
    if cur is None:
        cur = coords[remaining[0]]
        ordered.append(remaining.pop(0))
    while remaining:
        nxt = min(remaining, key=lambda n: _haversine_km(cur, coords[n]))
        remaining.remove(nxt)
        ordered.append(nxt)
        cur = coords[nxt]
    ordered.extend(unplaced)
    return ordered


def _split_contiguous(items: list[str], n: int) -> list[list[str]]:
    """Split a list into ``n`` contiguous, near-even chunks (front-loaded).

    Contiguous (not round-robin) so each chunk stays a geographically coherent
    cluster when ``items`` is already nearest-neighbor ordered."""
    n = max(1, min(n, len(items))) if items else 1
    k, m = divmod(len(items), n)
    chunks: list[list[str]] = []
    start = 0
    for i in range(n):
        size = k + (1 if i < m else 0)
        chunks.append(items[start : start + size])
        start += size
    return chunks


def _is_overnight_travel_day(entry: dict[str, Any]) -> bool:
    text_parts = [entry.get("title"), entry.get("summary"), entry.get("plan")]
    for raw in entry.get("stops") or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").strip().lower()
        if kind in {"flight", "transport"}:
            text_parts.extend((raw.get("name"), raw.get("note")))
    text = " ".join(str(part or "") for part in text_parts).lower()
    return any(
        marker in text
        for marker in ("overnight", "night train", "night bus", "sleeper", "red-eye", "red eye")
    )


def _itinerary_from_selections(trip: dict[str, Any] | None) -> dict[str, Any]:
    """Synthesize an intelligent multi-day v1 itinerary when the agent never
    wrote a structured ``day_wise_itinerary`` — so the panel is never blank and
    the user gets a real, editable first draft on the first go.

    Selected attractions are ordered by geographic proximity (nearest-neighbor
    from the hotel) and split into contiguous, day-sized clusters across the
    trip's length, with the hotel anchoring Day 1. The user can then ask the
    planner to refine times, meals, and pacing. Network-but-cached for coords;
    degrades to selection order when Places isn't configured.
    """
    hotels = _ordered_selected(trip, "selected_hotels")
    activities = _ordered_selected(trip, "selected_activities")
    destination = str((trip or {}).get("destination") or "")
    if not hotels and not activities:
        return {
            "has_itinerary": False,
            "destination": destination,
            "currency": currency_symbol(trip),
            "days": [],
            "stats": {"days": 0, "stops": 0, "booked": 0},
        }

    anchor = hotels[0] if hotels else None
    symbol = currency_symbol(trip)

    places_cache.prefetch(
        [*hotels, *activities], destination, max_photos=0, with_reviews=False
    )

    # Geographic ordering of the attractions (cached coord lookups).
    coords: dict[str, tuple[float, float]] = {}
    for name in activities:
        c = _place_coords(name, destination)
        if c:
            coords[name] = c
    start = _place_coords(anchor, destination) if anchor else None
    ordered = _nearest_neighbor_order(activities, coords, start)

    # How many days to spread across: the trip length, but never more days than
    # we have attractions to fill (so we don't emit empty days).
    trip_days = _trip_day_count(trip or {})
    if ordered:
        n_days = min(trip_days or len(ordered), len(ordered))
    else:
        n_days = 1
    n_days = max(1, n_days)
    chunks = _split_contiguous(ordered, n_days)

    days: list[dict[str, Any]] = []
    total_stops = 0
    for i, chunk in enumerate(chunks, start=1):
        color = _day_color(i)
        stops: list[dict[str, Any]] = []
        day_coords: list[tuple[float, float]] = []
        hotel_coords: tuple[float, float] | None = None

        if anchor:
            for hname in [anchor]:
                summary = places_cache.get_details(hname, destination) or {}
                opening, concern = _opening_hint(summary, "")
                stops.append({
                    "name": hname, "kind": "hotel", "time": "", "duration_min": None,
                    "note": "Your base", "booked": False, "selected": True, "color": color,
                    "opening_hours": opening,
                    "cost_display": _cost_hint("hotel", summary, 0.0, symbol),
                    "insight": _insight_hint(hname, "hotel", summary),
                    "concern": concern,
                    "rating": summary.get("rating"),
                    "review_count": summary.get("review_count"),
                    "popularity_score": _popularity_score(summary),
                })
                # Add hotel coords to day route.
                c = coords.get(hname) or _place_coords(hname, destination)
                if c:
                    hotel_coords = c
                    day_coords.append(c)

        for name in chunk:
            summary = places_cache.get_details(name, destination) or {}
            opening, concern = _opening_hint(summary, "")
            stops.append({
                "name": name, "kind": "attraction", "time": "", "duration_min": None,
                "note": "", "booked": False, "selected": True, "color": color,
                "opening_hours": opening,
                "cost_display": _cost_hint("attraction", summary, 0.0, symbol),
                "insight": _insight_hint(name, "attraction", summary),
                "concern": concern,
                "rating": summary.get("rating"),
                "review_count": summary.get("review_count"),
                "popularity_score": _popularity_score(summary),
            })
            # Add attraction coords to day route.
            c = coords.get(name)
            if c:
                day_coords.append(c)

        if anchor:
            hotel_start = stops[0]
            hotel_start["note"] = hotel_start.get("note") or "Start from your stay"
            hotel_return = dict(hotel_start)
            hotel_return["note"] = "Return to your stay"
            stops.append(hotel_return)
            if hotel_coords:
                day_coords.append(hotel_coords)

        if not stops:
            continue

        primary = chunk[0] if chunk else (anchor or f"Day {i}")
        previous_coords: tuple[float, float] | None = None
        previous_name = ""
        for stop in stops:
            stop_coords = coords.get(str(stop.get("name") or "")) or _place_coords(
                str(stop.get("name") or ""), destination
            )
            if stop_coords and previous_coords:
                stop["travel_from_previous"] = _route_stats_for_distance(
                    _haversine_km(previous_coords, stop_coords),
                    from_name=previous_name,
                    to_name=str(stop.get("name") or ""),
                )
            if stop_coords:
                previous_coords = stop_coords
                previous_name = str(stop.get("name") or "")
        route = _route_stats_for_day_coords(day_coords)
        _enrich_stop_timing(stops)
        schedule = _day_schedule(stops, route)
        _apply_hotel_endpoint_times(stops, schedule)
        _enrich_stop_timing(stops)

        days.append({
            "day": i,
            "date": "",
            "title": f"Day {i} · {primary}" if len(chunks) > 1 else primary,
            "summary": "Suggested first-draft plan grouped by area — ask the "
            "planner to fine-tune times, meals, and pacing.",
            "color": color,
            "stops": stops,
            "route": route,
            "schedule": schedule,
            "reachability": _reachability_hint(stops, route),
            "google_maps_url": _google_maps_day_url(destination, stops, route.get("mode", "")),
        })
        total_stops += len(stops)

    return {
        "has_itinerary": True,
        "destination": destination,
        "currency": currency_symbol(trip),
        "days": days,
        "stats": {"days": len(days), "stops": total_stops, "booked": 0},
    }


def _itinerary_place_coords(
    itin: list[Any],
    hotels: list[str],
    activities: list[str],
    destination: str,
) -> dict[str, tuple[float, float]]:
    """Pre-load coordinates for every itinerary stop so days can be measured.

    Uses EVERY itinerary stop name, not just selected buckets, so added meals,
    markets, and non-selected places still contribute to route metrics.
    """
    stop_names = {name.lower(): name for name in [*hotels, *activities]}
    for entry in itin:
        if not isinstance(entry, dict):
            continue
        for raw in entry.get("stops") or []:
            if isinstance(raw, dict):
                name = str(raw.get("name") or "").strip()
                kind = str(raw.get("kind") or "").strip().lower()
            else:
                name = str(raw or "").strip()
                kind = ""
            terminal_refs = _transport_terminal_refs(name, kind)
            if terminal_refs:
                for _, terminal_name in terminal_refs:
                    stop_names[terminal_name.lower()] = terminal_name
            elif name and kind not in {"flight", "transport"}:
                stop_names[name.lower()] = name

    places_cache.prefetch(
        list(stop_names.values()), destination, max_photos=0, with_reviews=False
    )
    place_coords_map: dict[str, tuple[float, float]] = {}
    for name in stop_names.values():
        coords = _place_coords(name, destination)
        if coords:
            place_coords_map[name.strip().lower()] = coords
    return place_coords_map


def _render_day_stops(
    entry: dict[str, Any],
    day_num: int,
    hotels: list[str],
    activities: list[str],
    destination: str,
    symbol: str,
    selected_prices: dict[str, float],
) -> tuple[list[dict[str, Any]], int]:
    """Normalize and enrich one agent-authored day into rendered stops.

    Returns the stops plus how many of them are already booked.
    """
    stops: list[dict[str, Any]] = []
    booked = 0
    pending_bus_arrival: dict[str, Any] | None = None
    for raw_stop_index, raw in enumerate(entry.get("stops") or [], start=1):
        s = _normalize_stop(raw, hotels, activities)
        if not s:
            continue
        if isinstance(raw, dict) and raw.get("decision_id"):
            # Lets the UI put the "why this way" affordance on the leg itself.
            s["decision_id"] = str(raw["decision_id"])
        route_mode = _resolved_transfer_mode(s["name"], s["kind"])
        if route_mode in {"Drive", "Bus"}:
            s["route_circuit_id"] = _route_circuit_id(day_num, raw_stop_index, route_mode)
        is_place = s["kind"] not in {"flight", "transport"}
        summary = places_cache.get_details(s["name"], destination) or {} if is_place else {}
        opening, concern = _opening_hint(summary, str(entry.get("date") or ""))
        s["duration_min"] = (
            None
            if s["kind"] == "hotel"
            else _duration_hint(s["kind"], s.get("duration_min"))
            if is_place or s.get("duration_min")
            else None
        )
        if not s.get("opening_hours"):
            s["opening_hours"] = opening
        if not s.get("concern"):
            s["concern"] = concern
        s["cost_display"] = s.get("cost_display") or _cost_hint(
            s["kind"],
            summary,
            selected_prices.get(str(s["name"]).strip().lower(), 0.0),
            symbol,
        )
        if is_place and not s.get("insight"):
            s["insight"] = _insight_hint(s["name"], s["kind"], summary)
        s["rating"] = summary.get("rating") if is_place else None
        s["review_count"] = summary.get("review_count") if is_place else None
        s["popularity_score"] = _popularity_score(summary) if is_place else None
        rendered_stops = _transport_terminal_stops(s)
        bus_arrival = (
            rendered_stops.pop()
            if route_mode == "Bus"
            and rendered_stops
            and rendered_stops[-1].get("terminal_role") == "arrival"
            else None
        )
        if pending_bus_arrival and s["kind"] not in {"attraction", "meal", "restaurant"}:
            rendered_stops = [pending_bus_arrival, *rendered_stops]
            pending_bus_arrival = None
        if bus_arrival:
            pending_bus_arrival = bus_arrival
        if not stops:
            road_origin = _road_origin_stop(s)
            if road_origin:
                rendered_stops = [road_origin, *rendered_stops]
        for rendered_stop in rendered_stops:
            rendered_stop["color"] = _day_color(day_num)
            stops.append(rendered_stop)
        if s["booked"]:
            booked += 1

    if pending_bus_arrival:
        pending_bus_arrival["color"] = _day_color(day_num)
        stops.append(pending_bus_arrival)
    return stops, booked


def _has_intercity_transfer(
    stops: list[dict[str, Any]],
    place_coords_map: dict[str, tuple[float, float]] | None = None,
) -> bool:
    if any(
        _resolved_transfer_mode(str(stop.get("name") or ""), str(stop.get("kind") or ""))
        for stop in stops
    ):
        return True
    return _implied_terminal_hop(stops, place_coords_map or {}) is not None


def _implied_terminal_hop(
    stops: list[dict[str, Any]],
    place_coords_map: dict[str, tuple[float, float]],
) -> str | None:
    """The unnamed journey between two back-to-back terminals, if there is one."""
    for previous, current in zip(stops, stops[1:]):
        from_coords = place_coords_map.get(str(previous.get("name") or "").strip().lower())
        to_coords = place_coords_map.get(str(current.get("name") or "").strip().lower())
        if not from_coords or not to_coords:
            continue
        mode = implied_terminal_hop_mode(
            _terminal_kind(previous),
            _terminal_kind(current),
            _haversine_km(from_coords, to_coords),
        )
        if mode:
            return mode
    return None


def _terminal_kind(stop: dict[str, Any]) -> str:
    """The terminal a stop names, whatever kind the plan filed it under."""
    kind = str(stop.get("kind") or "").strip().lower()
    if kind in {"airport", "station", "bus_station"}:
        return kind
    refs = _transport_terminal_refs(str(stop.get("name") or ""), kind)
    return refs[0][0] if len(refs) == 1 else ""


def _insert_transfer_day_stay_anchor(
    stops: list[dict[str, Any]],
    day_num: int,
    current_hotel: str,
    hotels: list[str],
    activities: list[str],
) -> None:
    """Start a transfer day at the previous night's stay (mutates ``stops``)."""
    first_transfer_index = next(
        (
            index
            for index, stop in enumerate(stops)
            if _resolved_transfer_mode(
                str(stop.get("name") or ""), str(stop.get("kind") or "")
            )
        ),
        -1,
    )
    first_hotel_index = next(
        (index for index, stop in enumerate(stops) if stop["kind"] == "hotel"),
        -1,
    )
    if first_transfer_index < 0 or (
        first_hotel_index >= 0 and first_transfer_index >= first_hotel_index
    ):
        return
    anchor = _normalize_stop({"name": current_hotel, "kind": "hotel"}, hotels, activities)
    if not anchor:
        return
    anchor["duration_min"] = None
    anchor["color"] = _day_color(day_num)
    anchor["note"] = "Start from your stay"
    if stops and stops[0]["kind"] == "origin":
        stops.pop(0)
    stops.insert(0, anchor)


def _wrap_day_in_stay(
    stops: list[dict[str, Any]],
    entry: dict[str, Any],
    day_num: int,
    current_hotel: str,
    hotels: list[str],
    activities: list[str],
    destination: str,
    symbol: str,
    selected_prices: dict[str, float],
) -> list[dict[str, Any]]:
    """Bookend a purely local day with the traveller's stay."""
    hotel_stops = [stop for stop in stops if stop["kind"] == "hotel"]
    distinct_hotels = {str(stop.get("name") or "").strip().lower() for stop in hotel_stops}
    if _is_overnight_travel_day(entry) or len(distinct_hotels) >= 2:
        return stops
    anchor = hotel_stops[0] if hotel_stops else None
    if anchor is None and current_hotel:
        anchor = _normalize_stop({"name": current_hotel, "kind": "hotel"}, hotels, activities)
        if anchor:
            summary = places_cache.get_details(anchor["name"], destination) or {}
            opening, concern = _opening_hint(summary, str(entry.get("date") or ""))
            anchor["duration_min"] = None
            anchor["opening_hours"] = opening
            anchor["concern"] = concern
            anchor["cost_display"] = _cost_hint(
                "hotel",
                summary,
                selected_prices.get(anchor["name"].strip().lower(), 0.0),
                symbol,
            )
            anchor["insight"] = _insight_hint(anchor["name"], "hotel", summary)
            anchor["color"] = _day_color(day_num)
    if not anchor:
        return stops
    middle = [stop for stop in stops if stop["kind"] != "hotel"]
    if not middle:
        return [dict(anchor)]
    hotel_start = dict(anchor)
    hotel_start["note"] = hotel_start.get("note") or "Start from your stay"
    hotel_return = dict(hotel_stops[-1] if len(hotel_stops) > 1 else anchor)
    hotel_return["note"] = hotel_return.get("note") or "Return to your stay"
    return [hotel_start, *middle, hotel_return]


def _append_return_to_stay(
    stops: list[dict[str, Any]],
    place_coords_map: dict[str, tuple[float, float]],
) -> None:
    """Close a transfer day by returning to the new stay after local outings."""
    hotel_indexes = [index for index, stop in enumerate(stops) if stop["kind"] == "hotel"]
    if not hotel_indexes:
        return
    last_hotel_index = max(hotel_indexes)
    last_transfer_index = max(
        (
            index
            for index, stop in enumerate(stops)
            if _resolved_transfer_mode(
                str(stop.get("name") or ""), str(stop.get("kind") or "")
            )
        ),
        default=-1,
    )
    if last_transfer_index >= last_hotel_index:
        return
    local_outings_after_hotel = [
        stop
        for stop in stops[last_hotel_index + 1 :]
        if stop["kind"] not in {"hotel", "airport", "flight", "transport"}
    ]
    hotel_coords = place_coords_map.get(
        str(stops[last_hotel_index].get("name") or "").strip().lower()
    )
    return_from_coords = (
        place_coords_map.get(
            str(local_outings_after_hotel[-1].get("name") or "").strip().lower()
        )
        if local_outings_after_hotel
        else None
    )
    if not hotel_coords or not return_from_coords:
        return
    hotel_return = dict(stops[last_hotel_index])
    for key in (
        "time",
        "arrival_time",
        "departure_time",
        "expected_arrival_time",
        "buffer_before_min",
        "buffer_before_display",
        "timing_conflict_min",
        "timing_conflict_display",
        "concern",
    ):
        hotel_return.pop(key, None)
    hotel_return["note"] = "Return to your stay"
    stops.append(hotel_return)


def _measure_local_route(
    stops: list[dict[str, Any]],
    place_coords_map: dict[str, tuple[float, float]],
) -> tuple[list[dict[str, Any]], list[tuple[float, float]]]:
    """Annotate leg-by-leg travel between local stops and collect their coords."""
    local_indexes = _local_route_stop_indexes(stops)
    local_stops = [
        stop for stop_index, stop in enumerate(stops, start=1) if stop_index in local_indexes
    ]
    day_coords: list[tuple[float, float]] = []
    previous_coords: tuple[float, float] | None = None
    previous_name = ""
    for stop in local_stops:
        coords = place_coords_map.get(str(stop.get("name") or "").strip().lower())
        if not coords:
            continue
        if previous_coords:
            stop["travel_from_previous"] = _route_stats_for_distance(
                _haversine_km(previous_coords, coords),
                from_name=previous_name,
                to_name=str(stop.get("name") or ""),
            )
        day_coords.append(coords)
        previous_coords = coords
        previous_name = str(stop.get("name") or "")
    return local_stops, day_coords


def _estimate_hotel_arrival_times(stops: list[dict[str, Any]]) -> None:
    """Fill in check-in times for stays reached straight from a terminal or drive."""
    for stop_index, stop in enumerate(stops[1:], start=1):
        previous = stops[stop_index - 1]
        if stop.get("kind") != "hotel" or stop.get("time"):
            continue
        estimated_time: int | None = None
        if previous.get("kind") in {"airport", "station", "bus_station"}:
            previous_time = _clock_minutes(previous.get("time"))
            has_transfer = isinstance(
                (stop.get("travel_from_previous") or {}).get("duration_min"),
                (int, float),
            ) and (stop.get("travel_from_previous") or {}).get("duration_min") > 0
            if previous_time is not None and has_transfer:
                transfer_minutes = int(
                    (stop.get("travel_from_previous") or {}).get("duration_min") or 0
                )
                terminal_exit_minutes = int(previous.get("duration_min") or 0)
                estimated_time = previous_time + terminal_exit_minutes + transfer_minutes
        elif (
            _intercity_transfer_mode(
                str(previous.get("name") or ""), str(previous.get("kind") or "")
            )
            == "Drive"
        ):
            estimated_time = _clock_minutes(
                previous.get("arrival_time") or previous.get("departure_time")
            )
        if estimated_time is not None:
            stop["time"] = _clock_display(estimated_time)
            stop["time_estimated"] = True


def build_itinerary(trip: dict[str, Any] | None) -> dict[str, Any]:
    """Structured day-by-day itinerary view-model (frontend-agnostic).

    Each day carries a title, prose summary, day color, and an ordered list of
    structured stops. Every stop is cross-referenced against the trip's
    selections (``selected``) and carries its own ``booked`` flag so the UI can
    render booked checkmarks and make each stop clickable (to focus its photos
    or its map pin). When the agent never wrote a structured itinerary, falls
    back to an intelligent multi-day plan synthesized from the selections
    (proximity-clustered; network-but-cached for coordinates).
    """
    if not trip or not (trip.get("day_wise_itinerary") or []):
        return _itinerary_from_selections(trip)

    hotels = _selected_names(trip, "hotel")
    ordered_hotels = _ordered_selected(trip, "selected_hotels")
    activities = _selected_names(trip, "attraction")
    destination = str((trip or {}).get("destination") or "")
    symbol = currency_symbol(trip)
    selected_prices = _selected_price_map(trip)
    itin = trip.get("day_wise_itinerary") or []
    weather = build_weather(trip)
    weather_by_date = {
        day["date"]: day for day in (weather or {}).get("days", [])
    }
    place_coords_map = _itinerary_place_coords(itin, hotels, activities, destination)
    transport_preferences = (
        (trip.get("preferences_snapshot") or {}).get("transport_preferences") or {}
    )

    days: list[dict[str, Any]] = []
    total_stops = 0
    total_booked = 0
    current_hotel = ordered_hotels[0] if ordered_hotels else ""
    for idx, entry in enumerate(itin):
        if not isinstance(entry, dict):
            entry = {"plan": str(entry)}
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        stops, day_booked = _render_day_stops(
            entry, day_num, hotels, activities, destination, symbol, selected_prices
        )
        total_booked += day_booked

        if _has_intercity_transfer(stops, place_coords_map):
            if idx > 0 and current_hotel:
                _insert_transfer_day_stay_anchor(
                    stops, day_num, current_hotel, hotels, activities
                )
            _append_return_to_stay(stops, place_coords_map)
        else:
            stops = _wrap_day_in_stay(
                stops,
                entry,
                day_num,
                current_hotel,
                hotels,
                activities,
                destination,
                symbol,
                selected_prices,
            )

        rendered_hotels = [stop for stop in stops if stop["kind"] == "hotel"]
        if rendered_hotels:
            current_hotel = str(rendered_hotels[-1].get("name") or current_hotel)

        local_stops, day_coords = _measure_local_route(stops, place_coords_map)
        total_stops += sum(
            stop["kind"] not in {"airport", "station", "bus_station", "origin"}
            for stop in stops
        )

        # Calculate route stats for the day.
        route = _route_stats_for_day_coords(day_coords)
        _enrich_drive_transfer_timing(stops, place_coords_map, transport_preferences)
        _enrich_stop_timing(stops)
        _estimate_hotel_arrival_times(stops)
        schedule = _day_schedule(stops, route)
        _apply_hotel_endpoint_times(stops, schedule)
        _enrich_stop_timing(stops)

        days.append(
            {
                "day": day_num,
                "date": str(entry.get("date") or "").strip(),
                "title": str(entry.get("title") or "").strip() or f"Day {day_num}",
                "summary": str(entry.get("summary") or entry.get("plan") or "").strip(),
                "color": _day_color(day_num),
                "stops": stops,
                "route": route,
                "schedule": schedule,
                "weather": weather_by_date.get(str(entry.get("date") or "").strip()),
                "reachability": _reachability_hint(local_stops, route),
                "google_maps_url": _google_maps_day_url(
                    destination, local_stops, route.get("mode", "")
                ),
            }
        )

    return {
        "has_itinerary": True,
        "destination": str(trip.get("destination") or ""),
        "currency": currency_symbol(trip),
        "days": days,
        "stats": {"days": len(days), "stops": total_stops, "booked": total_booked},
    }

