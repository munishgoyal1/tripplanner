"""Map pin construction and per-day route estimation for the trip panel.

Builds the geocoded pins (selected places + destination suggestions), assigns
day numbers/colors, and estimates per-day route legs and drive/bus circuits.
Split out of ``trip_view`` (tech-debt #7) as a leaf module that depends only on
``places_cache`` and the ``gallery`` / ``schedule`` / ``transport`` leaves;
``trip_view`` re-exports these names so callers and tests are unaffected.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote

from tripplanner.web import places_cache
from tripplanner.web.gallery import (
    _FALLBACK_HOTELS,
    _itinerary_names,
    _place_occurrence_index,
    _place_occurrences,
    _selected_names,
)
from tripplanner.web.place_confidence import (
    ANCHOR,
    LABEL,
    PLACE,
    names_a_place,
    stop_is_booked,
    stop_place_tier,
)
from tripplanner.web.place_confidence import (
    confirmed_bindings as _confirmed_bindings,
)
from tripplanner.web.schedule import (
    _INTERCITY_SPEED_KMH,
    MAX_GROUND_LEG_KM,
    _apply_saved_transfer_metrics,
    _haversine_km,
    _route_duration_display,
    _route_stats_for_coords,
    _route_stats_for_distance,
)
from tripplanner.web.transport import (
    _canonical_transport_name,
    _intercity_transfer_mode,
    _normalized_stop_kind,
    _transport_route_endpoints,
    _transport_terminal_refs,
)

_MAX_OVERVIEW_ATTRACTIONS = 6
_LOCAL_MODES = frozenset({"Walk", "Taxi"})


def build_map_url(destination: str, highlights: list[str] | None = None) -> str:
    """Return a Google Maps Embed iframe URL for ``destination``.

    Returns an empty string when ``GOOGLE_PLACES_API_KEY`` is not configured —
    the frontend simply hides the map in that case. Uses the Embed API "place"
    mode keyed on a free-text query (destination + first highlight) which
    needs no Place IDs and works for any city/country string.
    """
    destination = (destination or "").strip()
    if not destination:
        return ""
    try:
        from tripplanner.config import get_settings

        key = get_settings().google_places_api_key
    except Exception:
        key = ""
    if not key:
        return ""
    query = destination
    if highlights:
        first = next((h for h in highlights if h), "")
        if first:
            query = f"{first}, {destination}"
    return (
        "https://www.google.com/maps/embed/v1/place"
        f"?key={quote(key, safe='')}&q={quote(query, safe='')}"
    )


# Day-pin palette — distinct, reasonably color-blind-safe hues, cycled per day.
_DAY_COLORS = (
    "#e11d48",  # coral (brand)
    "#0d9488",  # teal (accent)
    "#2563eb",  # blue
    "#d97706",  # amber
    "#7c3aed",  # violet
    "#db2777",  # pink
    "#059669",  # emerald
    "#0891b2",  # cyan
)


def _maps_browser_key() -> str:
    try:
        from tripplanner.config import get_settings

        return get_settings().google_maps_browser_key or ""
    except Exception:
        return ""


def _day_color(day: int) -> str:
    return _DAY_COLORS[(day - 1) % len(_DAY_COLORS)]


def _day_for_place(name: str, itinerary: list[Any]) -> int | None:
    """Return the 1-based day number a place belongs to, or ``None``.

    "Both" strategy: prefer a structured ``stops`` list on a day entry; fall
    back to scanning the free-form ``plan`` prose for the place name.
    """
    needle = (name or "").strip().lower()
    if not needle:
        return None
    plan_only_entries: list[tuple[int, dict[str, Any]]] = []
    for idx, entry in enumerate(itinerary or []):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        stops = entry.get("stops")
        if isinstance(stops, list):
            for s in stops:
                s_name = s.get("name") if isinstance(s, dict) else s
                if s_name and needle in str(s_name).strip().lower():
                    return day_num
            continue
        plan_only_entries.append((day_num, entry))
    for day_num, entry in plan_only_entries:
        plan_text = str(entry.get("plan") or "").lower()
        if plan_text and needle in plan_text:
            return day_num
    return None


def _trip_day_count(trip: dict[str, Any]) -> int:
    """Number of days in the trip, for fallback day-clustering on the map.

    Prefers the structured itinerary length, then the date span, else 0.
    """
    itin = trip.get("day_wise_itinerary") or []
    if itin:
        return len(itin)
    dep = str(trip.get("departure_date") or "").strip()
    ret = str(trip.get("return_date") or "").strip()
    try:
        from datetime import date

        nights = (date.fromisoformat(ret) - date.fromisoformat(dep)).days
        if nights > 0:
            return nights
    except (ValueError, TypeError):
        pass
    return 0


def _local_route_stop_indexes(stops: list[Any]) -> set[int]:
    transfer_indexes = [
        index
        for index, stop in enumerate(stops)
        if isinstance(stop, dict)
        and _intercity_transfer_mode(
            str(stop.get("name") or ""), str(stop.get("kind") or "")
        )
    ]
    if not transfer_indexes:
        return set(range(1, len(stops) + 1))

    first_after_transfer = transfer_indexes[-1] + 1
    after_transfer = set(range(first_after_transfer + 1, len(stops) + 1))
    has_destination_stop = any(
        isinstance(stop, dict)
        and str(stop.get("kind") or "").strip().lower()
        not in {"airport", "station", "bus_station", "flight", "transport"}
        for stop in stops[first_after_transfer:]
    )
    if has_destination_stop:
        return after_transfer
    return set(range(1, transfer_indexes[0] + 1))


def _provider_name_matches(source_name: str, provider_name: str) -> bool:
    def _tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", value.lower())
            if len(token) > 2
        }

    source_tokens = _tokens(source_name)
    provider_tokens = _tokens(provider_name)
    if not source_tokens or not provider_tokens:
        return False
    ignored = {"airport", "hotel", "resort", "station", "stand", "temple"}
    source_identity = source_tokens - ignored or source_tokens
    provider_identity = provider_tokens - ignored or provider_tokens
    return any(
        SequenceMatcher(None, source_token, provider_token).ratio() >= 0.75
        for source_token in source_identity
        for provider_token in provider_identity
    ) or any(
        len(source_token) >= 5
        and len(provider_token) >= 5
        and source_token[:5] == provider_token[:5]
        for source_token in source_identity
        for provider_token in provider_identity
    )


def _hotel_identity_matches(left: str, right: str) -> bool:
    def _identity_tokens(name: str) -> set[str]:
        normalized = re.sub(r"\brameshwaram\b", "rameswaram", name, flags=re.IGNORECASE)
        tokens = set(re.findall(r"[a-z0-9]+", normalized.lower()))
        return tokens - {"hotel", "hotels", "resort", "resorts"}

    left_tokens = _identity_tokens(left)
    right_tokens = _identity_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return left_tokens <= right_tokens or right_tokens <= left_tokens


#: "Day 3 · Louvre & Marais" is a heading, not an address.
_DAY_LABEL_RE = re.compile(r"^\s*day\s*\d+\s*[·•:\-–—.]*\s*", re.IGNORECASE)


def _day_place_context(entry: dict[str, Any], destination: str) -> str:
    """Return a useful locality for Places lookups on one itinerary day.

    A title that names no locality must fall back to the destination. Passing
    one through sent Google "Musée d'Orsay Day 4 · Montmartre", which matches
    nothing, and eight Paris stops were reported as having no location at all.
    """
    for field in ("city", "location", "destination"):
        value = str(entry.get(field) or "").strip()
        if value:
            return value

    title = _DAY_LABEL_RE.sub("", str(entry.get("title") or "").strip())
    if not title:
        return destination
    if match := re.search(r"\bto\s+([^,]+)$", title, flags=re.IGNORECASE):
        return match.group(1).strip()
    title = re.sub(r"\s*\([^)]*\)", "", title).strip()
    for marker in (" Day Trip", " Excursion", " &"):
        if marker.lower() in title.lower():
            title = re.split(re.escape(marker), title, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            break
    if not names_a_place(title):
        return destination
    # A title that already says the destination narrows nothing and only adds
    # words the geocoder has to forgive.
    city = re.split(r"[,;/]", destination, maxsplit=1)[0].strip().casefold()
    if city and city in title.casefold():
        return destination
    return title


def _map_pins(
    trip: dict[str, Any],
    destination: str,
    unmapped: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Geocoded pins for selected items + destination top-places (suggestions).

    ``unmapped`` collects every itinerary stop that did not become a pin, with
    the reason, so no surface has to guess why a stop is missing.
    """
    itinerary = trip.get("day_wise_itinerary") or []
    selected = {
        "hotel": _selected_names(trip, "hotel"),
        "attraction": _selected_names(trip, "attraction"),
    }
    itinerary_names = _itinerary_names(trip)
    bindings = _confirmed_bindings(trip)
    chosen_names = selected["hotel"] | selected["attraction"]

    # Structured itinerary stops are authoritative for what should appear on
    # the map and in which order/day. Keep an explicit day map so duplicated
    # names across sources don't lose their itinerary day assignment.
    explicit_day_by_name: dict[str, int] = {}
    tier_by_name: dict[str, str] = {}
    from_itinerary: set[str] = set()

    # (kind, name) in display order: user picks first, then suggestions.
    refs: list[tuple[str, str]] = []
    context_by_name: dict[str, str] = {}
    seen: set[str] = set()

    def _add(kind: str, name: str, context: str = destination) -> None:
        key = (name or "").strip().lower()
        if kind == "hotel" and any(
            existing_kind == "hotel" and _hotel_identity_matches(existing_name, name)
            for existing_kind, existing_name in refs
        ):
            return
        if name and key not in seen:
            seen.add(key)
            refs.append((kind, name))
            context_by_name[key] = context

    def _infer_kind_from_name(name: str) -> str:
        n = (name or "").strip().lower()
        if n in selected["hotel"]:
            return "hotel"
        if n in selected["attraction"]:
            return "attraction"
        return "attraction"

    # 1) Structured itinerary stops first, preserving day/stop order so route
    #    lines follow the actual itinerary sequence.
    for idx, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        stops = entry.get("stops")
        if not isinstance(stops, list):
            continue
        day_context = _day_place_context(entry, destination)
        has_route_anchor = False
        for s in stops:
            if isinstance(s, dict):
                name = str(s.get("name") or "").strip()
                kind = str(s.get("kind") or "").strip().lower()
                mode_name = str(s.get("mode") or "")
                name = _canonical_transport_name(name, mode_name)
                kind = _normalized_stop_kind(name, kind, mode_name)
            else:
                name = str(s or "").strip()
                kind = ""
            if not name:
                continue
            tier = stop_place_tier(
                name,
                kind,
                selected=chosen_names,
                booked=stop_is_booked(s),
            )
            terminal_refs = _transport_terminal_refs(name, kind)
            if terminal_refs:
                if _intercity_transfer_mode(name, kind) == "Drive" and has_route_anchor:
                    continue
                for terminal_kind, terminal_name in terminal_refs:
                    _add(terminal_kind, terminal_name, "")
                    explicit_day_by_name.setdefault(terminal_name.lower(), day_num)
                    tier_by_name.setdefault(terminal_name.lower(), ANCHOR)
                    from_itinerary.add(terminal_name.lower())
                continue
            if kind in {"flight", "transport"}:
                continue
            if kind not in {"hotel", "attraction", "meal", "restaurant"}:
                kind = _infer_kind_from_name(name)
            _add(kind, name, day_context)
            explicit_day_by_name.setdefault(name.lower(), day_num)
            tier_by_name.setdefault(name.lower(), tier)
            from_itinerary.add(name.lower())
            has_route_anchor = True

    # 2) User selected places (ensure presence even if stops list is absent).
    for h in trip.get("selected_hotels") or []:
        if isinstance(h, dict) and h.get("name"):
            _add("hotel", str(h["name"]))
    for a in trip.get("selected_activities") or []:
        if isinstance(a, dict) and a.get("name"):
            _add("attraction", str(a["name"]))

    # 3) Destination suggestions to fill context around the chosen items.
    if destination and len(refs) < 3:
        for name in places_cache.top_places(destination, "hotel", n=_FALLBACK_HOTELS):
            _add("hotel", name)
        for name in places_cache.top_places(
            destination, "attraction", n=_MAX_OVERVIEW_ATTRACTIONS
        ):
            _add("attraction", name)

    names_by_context: dict[str, list[str]] = {}
    for _, name in refs:
        if tier_by_name.get(name.strip().lower()) != LABEL:
            context = context_by_name.get(name.strip().lower(), destination)
            names_by_context.setdefault(context, []).append(name)
    for context, names in names_by_context.items():
        places_cache.prefetch(names, context, max_photos=1, with_reviews=False)

    def _report(name: str, kind: str, reason: str, candidate: dict[str, Any] | None) -> None:
        key = name.strip().lower()
        if unmapped is None or key not in from_itinerary:
            return
        unmapped.append(
            {
                "name": name,
                "kind": kind,
                "day": explicit_day_by_name.get(key),
                "tier": tier_by_name.get(key, PLACE),
                "reason": reason,
                "candidate": candidate,
            }
        )

    place_occurrences = _place_occurrence_index(trip)
    pins: list[dict[str, Any]] = []
    for i, (kind, name) in enumerate(refs):
        key = name.strip().lower()
        context = context_by_name.get(key, destination)
        if tier_by_name.get(key) == LABEL:
            # Naming no place, it has no pin to be missing; say so rather than
            # letting the geocoder invent one.
            _report(name, kind, "not_a_place", None)
            continue
        binding = bindings.get(key)
        info = (
            binding
            if binding
            else (places_cache.get_details(name, context) or {})
        )
        if (
            not binding
            and context != destination
            and (info.get("lat") is None or info.get("lng") is None)
        ):
            destination_info = places_cache.get_details(name, destination) or {}
            if destination_info.get("lat") is not None and destination_info.get("lng") is not None:
                info = destination_info
                context = destination
        provider_name = str(info.get("name") or "").strip()
        if (
            provider_name
            and not binding
            and kind not in {"airport", "station", "bus_station"}
            and not _provider_name_matches(name, provider_name)
        ):
            # The provider found somewhere else. Offer it as a candidate rather
            # than pinning it, so a wrong pin needs a person to agree to it.
            _report(
                name,
                kind,
                "no_match",
                {
                    "name": provider_name,
                    "place_id": info.get("place_id"),
                    "lat": info.get("lat"),
                    "lng": info.get("lng"),
                },
            )
            continue
        lat, lng = info.get("lat"), info.get("lng")
        if lat is None or lng is None:
            _report(name, kind, "no_location", None)
            continue
        photos = places_cache.get_photos(name, context, max_photos=1)
        is_sel = (
            name.strip().lower() in selected.get(kind, set())
            or name.strip().lower() in itinerary_names
        )
        pins.append(
            {
                "id": f"p{i}",
                "name": name,
                "provider_name": provider_name or None,
                "_source_name": name,
                "kind": kind,
                "selected": is_sel,
                "day": explicit_day_by_name.get(name.strip().lower())
                or _day_for_place(name, itinerary),
                "lat": lat,
                "lng": lng,
                "rating": info.get("rating"),
                "address": info.get("address") or "",
                "photo": photos[0] if photos else None,
                "occurrences": _place_occurrences(trip, name, place_occurrences),
            }
        )

    # Fallback day-clustering: any SELECTED attraction the itinerary text didn't
    # explicitly place still deserves a day so it shows a bold, numbered marker
    # and joins a per-day route line. Spread them evenly across the trip's days,
    # continuing after whatever the itinerary already assigned.
    day_count = _trip_day_count(trip)
    if day_count > 0:
        used_days = sorted({p["day"] for p in pins if p["day"]})
        cursor = 0
        for p in pins:
            if p["kind"] != "attraction" or not p["selected"] or p["day"]:
                continue
            # Prefer days that have nothing assigned yet, then round-robin.
            target = None
            for d in range(1, day_count + 1):
                if d not in used_days:
                    target = d
                    used_days.append(d)
                    break
            if target is None:
                target = (cursor % day_count) + 1
                cursor += 1
            p["day"] = target
    return pins



def _airport_pin(destination: str) -> dict[str, Any] | None:
    """A single 'arrival airport' pin for Day-1 context, if geocodable."""
    if not destination:
        return None
    info = places_cache.get_details(f"{destination} International Airport", destination)
    if not info or info.get("lat") is None or info.get("lng") is None:
        return None
    return {
        "id": "airport",
        "name": info.get("name") or f"{destination} Airport",
        "kind": "airport",
        "lat": info["lat"],
        "lng": info["lng"],
    }


def _route_legs_for_day(
    pin_ids: list[str],
    pin_by_id: dict[str, dict[str, Any]],
    intercity_modes: dict[tuple[str, str], str] | None = None,
    route_circuit_ids: dict[tuple[str, str], str] | None = None,
    transfer_metrics: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for from_id, to_id in zip(pin_ids, pin_ids[1:]):
        start = pin_by_id.get(from_id) or {}
        end = pin_by_id.get(to_id) or {}
        start_coords = (start.get("lat"), start.get("lng"))
        end_coords = (end.get("lat"), end.get("lng"))
        if not all(isinstance(value, (int, float)) for value in (*start_coords, *end_coords)):
            continue
        distance = _haversine_km(
            (float(start_coords[0]), float(start_coords[1])),
            (float(end_coords[0]), float(end_coords[1])),
        )
        intercity_mode = (intercity_modes or {}).get((from_id, to_id))
        if intercity_mode:
            speed = _INTERCITY_SPEED_KMH[intercity_mode]
            duration = int(round((distance / speed) * 60))
            metrics = {
                "distance_km": round(distance, 1),
                "duration_min": duration,
                "mode": intercity_mode,
                "distance_display": f"{distance:.1f} km",
                "duration_display": _route_duration_display(duration),
            }
            metrics["intercity"] = True
        else:
            metrics = _route_stats_for_distance(
                distance,
                from_name=str(start.get("name") or ""),
                to_name=str(end.get("name") or ""),
            )
        if metrics["mode"] in _LOCAL_MODES and distance > MAX_GROUND_LEG_KM:
            continue
        circuit_id = (route_circuit_ids or {}).get((from_id, to_id))
        legs.append({
            "from_pin_id": from_id,
            "to_pin_id": to_id,
            **metrics,
            **({"route_circuit_id": circuit_id} if circuit_id else {}),
        })

    for circuit_id, saved_metrics in (transfer_metrics or {}).items():
        _apply_saved_transfer_metrics(
            [leg for leg in legs if leg.get("route_circuit_id") == circuit_id],
            saved_metrics,
        )
    return legs


def _route_circuit_id(day: int, stop: int, mode: str) -> str:
    return f"day-{day}-stop-{stop}-{mode.strip().lower()}"


def _normalize_map_stops(stops: list[Any]) -> list[dict[str, str | None]]:
    """Canonical (name, kind, transfer-mode) per raw stop, preserving order.

    Mirrors how ``build_itinerary`` normalizes each stop so drive-circuit
    construction sees the same names/kinds (and thus the same circuit ids).
    """
    normalized: list[dict[str, str | None]] = []
    for stop in stops:
        if isinstance(stop, dict):
            raw_name = str(stop.get("name") or "")
            raw_kind = str(stop.get("kind") or "").strip().lower()
            mode_name = str(stop.get("mode") or "")
        else:
            raw_name = str(stop or "")
            raw_kind = ""
            mode_name = ""
        name = _canonical_transport_name(raw_name, mode_name)
        kind = _normalized_stop_kind(name, raw_kind, mode_name)
        normalized.append(
            {"name": name, "kind": kind, "mode": _intercity_transfer_mode(name, kind)}
        )
    return normalized


def _resolve_road_circuit_pin_ids(
    normalized: list[dict[str, str | None]],
    transfer_index: int,
    resolve_pin: Any,
    origin_fallbacks: list[str],
) -> list[str]:
    """Ordered pin ids ``[origin, *waypoints, destination]`` for a road row.

    Drive circuits use the prior place and next hotel/terminal. Bus circuits use
    their named bus terminals and include only scenic/meal stops before check-in,
    so destination-local sightseeing cannot leak into the transfer circuit.
    """
    transfer = normalized[transfer_index]
    mode = str(transfer["mode"] or "")
    terminal_refs = _transport_terminal_refs(
        str(transfer["name"] or ""), str(transfer["kind"] or "")
    )
    if mode == "Bus" and len(terminal_refs) == 2:
        terminal_pins = [resolve_pin(name, kind) for kind, name in terminal_refs]
        if all(terminal_pins):
            origin_id = str(terminal_pins[0]["id"])
            destination_id = str(terminal_pins[1]["id"])
            waypoint_ids: list[str] = []
            for candidate in normalized[transfer_index + 1:]:
                if candidate["mode"] or candidate["kind"] == "hotel":
                    break
                if candidate["kind"] not in {"attraction", "meal", "restaurant"}:
                    continue
                pin = resolve_pin(candidate["name"], candidate["kind"])
                if pin:
                    pin_id = str(pin["id"])
                    if pin_id not in {origin_id, destination_id} and pin_id not in waypoint_ids:
                        waypoint_ids.append(pin_id)
            return [origin_id, *waypoint_ids, destination_id]

    endpoints = _transport_route_endpoints(str(transfer["name"] or ""))
    parsed_origin, parsed_dest = endpoints if endpoints else (None, None)

    origin_id: str | None = None
    for prev in reversed(normalized[:transfer_index]):
        if prev["mode"] or not prev["name"]:
            continue
        pin = resolve_pin(prev["name"], prev["kind"])
        if pin:
            origin_id = str(pin["id"])
            break
    if origin_id is None:
        origin_id = next((pid for pid in origin_fallbacks if pid), None)
    if origin_id is None and parsed_origin:
        pin = resolve_pin(parsed_origin, "origin") or resolve_pin(parsed_origin, "")
        if pin:
            origin_id = str(pin["id"])

    waypoint_ids: list[str] = []
    destination_id: str | None = None
    for nxt in normalized[transfer_index + 1:]:
        if nxt["mode"]:
            refs = _transport_terminal_refs(str(nxt["name"] or ""), str(nxt["kind"] or ""))
            if refs:
                pin = resolve_pin(refs[0][1], refs[0][0])
                if pin and str(pin["id"]) != origin_id:
                    destination_id = str(pin["id"])
            break
        if not nxt["name"]:
            continue
        pin = resolve_pin(nxt["name"], nxt["kind"])
        if not pin:
            continue
        pin_id = str(pin["id"])
        if pin["kind"] == "hotel":
            destination_id = pin_id
            break
        if pin_id != origin_id and pin_id not in waypoint_ids:
            waypoint_ids.append(pin_id)
    if destination_id is None and parsed_dest:
        for hint, candidate in (
            ("airport", f"{parsed_dest} Airport"),
            ("airport", parsed_dest),
            ("station", f"{parsed_dest} Railway Station"),
            ("bus_station", f"{parsed_dest} Bus Stand"),
            ("", parsed_dest),
        ):
            pin = resolve_pin(candidate, hint)
            if pin and str(pin["id"]) != origin_id:
                destination_id = str(pin["id"])
                break
    if destination_id is None and waypoint_ids:
        destination_id = waypoint_ids.pop()

    ordered: list[str] = []
    for pin_id in [origin_id, *waypoint_ids, destination_id]:
        if pin_id and (not ordered or ordered[-1] != pin_id):
            ordered.append(pin_id)
    return ordered


def _route_stats_for_day_coords(coords: list[tuple[float, float]]) -> dict[str, Any]:
    """Estimate day route metrics from an ordered list of (lat, lng) tuples.

    Same logic as _route_stats_for_day, but takes pre-computed coordinates
    instead of pin_ids. Used by build_itinerary to calculate per-day routes.
    """
    return _route_stats_for_coords(coords)
