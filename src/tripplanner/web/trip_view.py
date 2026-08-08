"""Pure-Python view-model builder for the trip panel.

This module is the **decoupling boundary** between the trip-planner backend
and whatever frontend renders it. It contains **no UI-framework imports** —
only plain functions that turn a trip dict into a JSON-serializable ``dict``
describing what to show.

The React SPA (``frontend/``) fetches this JSON from ``GET /trip/view`` (see
``api.py``) and renders it. Keeping the shaping here means the frontend never
touches the data logic.

The only external dependency is ``places_cache`` for photos/reviews — that's a
data source (Google Places), not a UI concern, and it degrades gracefully when
unconfigured.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any
from urllib.parse import quote

from tripplanner.config import get_settings
from tripplanner.decisions.provenance import build_provenance
from tripplanner.decisions.store import list_decisions
from tripplanner.tools import user_preferences
from tripplanner.web import map_view, places_cache

# Budget/money helpers live in ``budget`` (tech-debt #7); re-exported here so
# existing ``trip_view.*`` callers and tests are unaffected.
from tripplanner.web.budget import (  # noqa: F401
    _PRICE_KEYS,
    _sum_item_prices,
    _to_number,
    build_budget,
    currency_symbol,
    fmt_money,
    traveler_count,
)

# Gallery selection and itinerary occurrence indexing live in ``gallery``
# (tech-debt #7), a leaf module; re-exported here for callers/tests.
from tripplanner.web.gallery import (  # noqa: F401
    _FALLBACK_ATTRACTIONS,
    _FALLBACK_HOTELS,
    _MAX_GALLERY_ITEMS,
    _itinerary_names,
    _place_occurrence_index,
    _place_occurrences,
    _planned_place_names,
    _selected_names,
    _terminal_occurrence_index,
    _terminal_occurrences,
    itinerary_items,
)

# Map pin construction and per-day route estimation live in ``map_pins``
# (tech-debt #7), a leaf module; re-exported here for callers/tests.
from tripplanner.web.map_pins import (  # noqa: F401
    _DAY_COLORS,
    _MAX_OVERVIEW_ATTRACTIONS,
    _airport_pin,
    _day_color,
    _day_for_place,
    _hotel_identity_matches,
    _local_route_stop_indexes,
    _map_pins,
    _maps_browser_key,
    _normalize_map_stops,
    _provider_name_matches,
    _resolve_road_circuit_pin_ids,
    _route_circuit_id,
    _route_legs_for_day,
    _route_stats_for_day_coords,
    _trip_day_count,
    build_map_url,
)

# Route-metric and stop-timing helpers live in ``schedule`` (tech-debt #7), a
# pure-computation leaf module; re-exported here for callers/tests.
from tripplanner.web.schedule import (  # noqa: F401
    _INTERCITY_SPEED_KMH,
    _apply_hotel_endpoint_times,
    _apply_saved_transfer_metrics,
    _clock_display,
    _clock_minutes,
    _day_schedule,
    _enrich_drive_transfer_timing,
    _enrich_stop_timing,
    _haversine_km,
    _route_duration_display,
    _route_stats_for_coords,
    _route_stats_for_day,
    _route_stats_for_distance,
    _stop_duration_display,
)

# Transport-name helpers live in ``transport`` (tech-debt #7), a leaf module
# shared by the gallery and map-pin builders; re-exported here for callers/tests.
from tripplanner.web.transport import (  # noqa: F401
    _canonical_transport_name,
    _intercity_transfer_mode,
    _normalized_stop_kind,
    _transport_route_endpoints,
    _transport_terminal_refs,
)

_MAX_PHOTOS_PER_ITEM = 3
_MAX_REVIEWS_PER_ITEM = 2

# Lab 13 — paged destination guide.
_BROWSE_KINDS = ("hotel", "attraction", "restaurant")
_FALLBACK_CITY_PLACES = 6
_GUIDE_PAGE_SIZE = 6
_GUIDE_MAX_LIMIT = 24
_HOTEL_ALIASES = {"hotel", "lodging", "stay", "accommodation"}
_RESTAURANT_ALIASES = {"restaurant", "meal", "food", "dining", "cafe", "eatery"}
# Transport legs ("Flight: Bangalore to Indore", "Drive: Indore to Ujjain") are not
# places to discover — they're excluded from the guide pool, but their arrival city
# tells us which city the stops that follow belong to when no structured city exists.
_TRANSPORT_KINDS = {"flight", "transport", "train", "bus", "car", "drive", "taxi", "ferry", "cab"}
_TRANSPORT_PREFIXES = {"flight", "drive", "train", "bus", "cab", "taxi", "ferry", "car"}


# ---------------------------------------------------------------------------
# pure helpers (no network) — safe to unit-test without stubs
# ---------------------------------------------------------------------------


def has_selections(trip: dict[str, Any] | None) -> bool:
    if not trip:
        return False
    return bool((trip.get("selected_hotels") or []) or (trip.get("selected_activities") or []))


def is_fallback(trip: dict[str, Any] | None, focus: dict[str, Any] | None) -> bool:
    """True when we're showing destination highlights rather than the user's
    own picks (a destination is known, nothing selected yet, not focused)."""
    if focus and focus.get("name"):
        return False
    return bool(trip and trip.get("destination")) and not has_selections(trip)


def family_pills(prefs: dict[str, Any] | None) -> list[str]:
    """Short, render-ready chips summarising who's on the trip.

    Derived from ``family_members``, ``food_preferences.dietary``, and
    ``accessibility_needs``. The trip agent already uses this same data to
    bias suggestions; showing the pills makes the bias visible to the user so
    they can correct it ("Actually we're not vegetarian anymore").
    """
    if not prefs:
        return []
    out: list[str] = []
    members = [m for m in (prefs.get("family_members") or []) if isinstance(m, dict)]

    def _age(m: dict[str, Any]) -> float | None:
        v = m.get("age")
        return float(v) if isinstance(v, (int, float)) else None

    kid_ages = sorted({int(_age(m)) for m in members if _age(m) is not None and _age(m) < 13})
    teen_ages = sorted({int(_age(m)) for m in members if _age(m) is not None and 13 <= _age(m) < 18})
    senior_members = [m for m in members if _age(m) is not None and _age(m) >= 65]
    pet_members = [m for m in members if (m.get("relationship") or "").lower() in ("pet", "dog", "cat")]

    if kid_ages:
        out.append("\U0001f476 Kid-friendly (ages " + ",".join(str(a) for a in kid_ages) + ")")
    if teen_ages:
        out.append("\U0001f9d2 Teen-friendly (ages " + ",".join(str(a) for a in teen_ages) + ")")
    if senior_members:
        mobility = next((str(m.get("mobility") or "").strip() for m in senior_members if (m.get("mobility") or "").strip()), "")
        label = "\U0001f475 Senior-friendly" + (f" ({mobility})" if mobility else "")
        out.append(label)
    if pet_members:
        out.append("\U0001f43e Pet-friendly")

    diets: set[str] = set()
    for m in members:
        d = str(m.get("dietary") or "").strip()
        if d:
            diets.add(d.title())
    for d in (prefs.get("food_preferences", {}) or {}).get("dietary") or []:
        d = str(d or "").strip()
        if d:
            diets.add(d.title())
    for d in sorted(diets):
        out.append(f"\U0001f957 {d}")

    for a in (prefs.get("accessibility_needs") or []):
        a = str(a or "").strip()
        if a:
            out.append(f"\u267f {a.title()}")

    return out


def _weather_condition(summary: str) -> str:
    value = summary.strip().lower()
    if any(word in value for word in ("thunder", "storm", "hail")):
        return "storm"
    if any(word in value for word in ("snow", "sleet", "freezing")):
        return "snow"
    if any(word in value for word in ("rain", "drizzle", "shower")):
        return "rain"
    if "fog" in value or "mist" in value:
        return "fog"
    if "overcast" in value or "cloudy" in value:
        return "cloudy" if "partly" not in value else "partly_cloudy"
    if any(word in value for word in ("clear", "sunny")):
        return "clear"
    return "unknown"


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def build_weather(trip: dict[str, Any] | None) -> dict[str, Any] | None:
    raw = (trip or {}).get("weather")
    if not isinstance(raw, dict):
        return None
    source = str(raw.get("source") or "").strip().lower()
    if source not in {"forecast", "seasonal_estimate", "agent_climate_estimate"}:
        return None

    days: list[dict[str, Any]] = []
    for raw_day in raw.get("days") or []:
        if not isinstance(raw_day, dict):
            continue
        day_date = str(raw_day.get("date") or "").strip()
        summary = str(raw_day.get("summary") or "Typical conditions").strip()
        if not day_date:
            continue
        days.append(
            {
                "date": day_date,
                "summary": summary,
                "condition": _weather_condition(summary),
                "high_c": _number(raw_day.get("high_c")),
                "low_c": _number(raw_day.get("low_c")),
                "precip_mm": _number(raw_day.get("precip_mm")),
                "precip_probability_pct": _number(
                    raw_day.get("precip_probability_pct")
                ),
            }
        )
    if not days:
        return None

    highs = [day["high_c"] for day in days if day["high_c"] is not None]
    lows = [day["low_c"] for day in days if day["low_c"] is not None]
    rainy = any(
        day["condition"] in {"rain", "storm"}
        or (day["precip_mm"] or 0) >= 2
        or (day["precip_probability_pct"] or 0) >= 40
        for day in days
    )
    snowy = any(day["condition"] == "snow" for day in days)
    packing = [str(item).strip() for item in raw.get("packing_advice") or [] if str(item).strip()]
    if not packing:
        if snowy or (lows and min(lows) <= 5):
            packing.append("Insulated coat, warm layers, gloves, and weatherproof shoes")
        elif lows and min(lows) <= 15:
            packing.append("Light jacket and layers for cooler mornings and evenings")
        elif highs and max(highs) >= 28:
            packing.append("Light, breathable clothes plus a hat and sunscreen")
        else:
            packing.append("Comfortable light layers for changing conditions")
        if rainy:
            packing.append("Compact umbrella, light rain jacket, and quick-dry footwear")

    return {
        "source": source,
        "source_label": {
            "forecast": "Live forecast",
            "seasonal_estimate": "Typical for this season",
            "agent_climate_estimate": "Typical monthly pattern",
        }[source],
        "note": str(raw.get("note") or "").strip(),
        "days": days,
        "packing_advice": packing,
    }


# ---------------------------------------------------------------------------
# view-model assembly (may hit Places for photos/reviews)
# ---------------------------------------------------------------------------


def _build_cost_baseline(trip: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    """What the plan cost before the traveller started overruling it.

    Absent until the first overrule, so an untouched trip shows no comparison
    against itself.
    """
    baseline = trip.get("cost_baseline")
    if not isinstance(baseline, dict):
        return None
    first, current = baseline.get("first"), baseline.get("current")
    if not isinstance(first, int | float) or not isinstance(current, int | float):
        return None
    saved = round(float(first) - float(current), 2)
    return {
        "first": first,
        "current": current,
        "saved": saved,
        "currency": str(baseline.get("currency") or ""),
        "first_display": fmt_money(first, symbol),
        "current_display": fmt_money(current, symbol),
        "saved_display": fmt_money(abs(saved), symbol),
    }


def _build_overview(trip: dict[str, Any]) -> dict[str, Any]:
    counts = {
        "flights": len(trip.get("selected_flights") or []),
        "hotels": len(trip.get("selected_hotels") or []),
        "activities": len(_planned_place_names(trip)),
        "days": len(trip.get("day_wise_itinerary") or []),
    }
    total = trip.get("total_cost")
    try:
        prefs = user_preferences.load_preferences()
    except Exception:  # pragma: no cover - storage failure shouldn't break the view
        prefs = None
    symbol = currency_symbol(trip)
    return {
        "destination": trip.get("destination") or "",
        "origin": trip.get("origin") or "",
        "departure_date": trip.get("departure_date") or "",
        "return_date": trip.get("return_date") or "",
        "travelers": trip.get("travelers") or "",
        "status": str(trip.get("status") or "draft"),
        "notes": trip.get("notes") or "",
        "counts": counts,
        "total_cost": total,
        "total_cost_display": fmt_money(total, symbol),
        "cost_baseline": _build_cost_baseline(trip, symbol),
        "provenance": build_provenance(trip),
        "budget": build_budget(trip),
        "weather": build_weather(trip),
        "family_pills": family_pills(prefs),
        "constraints": [
            str(c).strip()
            for c in (trip.get("trip_constraints") or [])
            if str(c).strip()
        ],
    }


def _build_item(
    ref: dict[str, str],
    destination: str,
    selected_names: dict[str, set[str]],
    itinerary_names: set[str] | None = None,
    occurrences: list[dict[str, Any]] | None = None,
    city: str = "",
) -> dict[str, Any]:
    name = ref["name"]
    kind = ref.get("kind", "place")
    info = places_cache.get_summary(name, destination) or {}
    photos = places_cache.get_photos(name, destination, max_photos=_MAX_PHOTOS_PER_ITEM)
    reviews = [
        {
            "rating": r.get("rating"),
            "text": r.get("text") or "",
            "author": r.get("author") or "Guest",
        }
        for r in (info.get("reviews") or [])[:_MAX_REVIEWS_PER_ITEM]
        if (r.get("text") or "").strip()
    ]
    key = name.strip().lower()
    # Buckets are hotel/attraction only, so map every other kind (restaurant,
    # meal, activity, ...) the same way the guide's IN TRIP badge does.
    bucket = "hotel" if browse_kind(kind) == "hotel" else "attraction"
    selected = key in selected_names.get(bucket, set()) or key in (itinerary_names or set())
    return {
        "kind": kind,
        "name": info.get("name") or name,
        "city": city,
        "selected": selected,
        "rating": info.get("rating"),
        "review_count": info.get("review_count"),
        "address": info.get("address") or "",
        "summary": info.get("editorial_summary") or "",
        "website": info.get("website") or "",
        "photos": photos,
        "reviews": reviews,
        "occurrences": occurrences or [],
    }


def browse_kind(kind: str | None) -> str:
    """Normalize a raw place kind into one of the three browse buckets."""
    value = str(kind or "").strip().lower()
    if value in _HOTEL_ALIASES:
        return "hotel"
    if value in _RESTAURANT_ALIASES:
        return "restaurant"
    return "attraction"


def _clean_city(value: Any) -> str:
    return str(value or "").strip()


def _is_transport_stop(name: str, kind: str) -> bool:
    """True for flights/drives/trains etc. — movement between places, not a place."""
    if kind in _TRANSPORT_KINDS:
        return True
    prefix = name.split(":", 1)[0].strip().lower() if ":" in name else ""
    return prefix in _TRANSPORT_PREFIXES


def _arrival_city(name: str) -> str:
    """Extract the arrival city from a transport leg name ("... to <City>")."""
    endpoints = _transport_route_endpoints(name)
    if not endpoints:
        return ""
    return re.split(r"[(\[]", endpoints[1])[0].strip().strip(".,").strip()


def _derive_route_cities(trip: dict[str, Any]) -> dict[str, str]:
    """Attribute each non-transport stop to a city inferred from transport legs.

    A fallback used only when stops carry no structured ``city``: the arrival city
    of the most recent ``... to <City>`` leg becomes the current city for the stops
    that follow it, so a multi-city route still yields per-city filters.
    """
    mapping: dict[str, str] = {}
    current = ""
    for day in trip.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops") or []:
            name = str((stop.get("name") if isinstance(stop, dict) else stop) or "").strip()
            kind = str((stop.get("kind") if isinstance(stop, dict) else "") or "").strip().lower()
            if not name:
                continue
            if _is_transport_stop(name, kind):
                arrival = _arrival_city(name)
                if arrival:
                    current = arrival
                continue
            key = name.lower()
            if current and key not in mapping:
                mapping[key] = current
    return mapping


def _place_cities(trip: dict[str, Any]) -> dict[str, str]:
    """Map ``place-name-lower -> city`` from structured itinerary/place evidence.

    City identity comes from explicit ``city`` fields on itinerary days, stops
    and selected items — never by parsing the free-form destination label. Places
    without structured evidence fall back to route-derived cities (arrival city of
    the preceding transport leg) so multi-city trips without city fields still work.
    """
    mapping: dict[str, str] = {}

    def _record(name: Any, city: Any) -> None:
        n = str(name or "").strip().lower()
        c = _clean_city(city)
        if n and c and n not in mapping:
            mapping[n] = c

    for day in trip.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        day_city = day.get("city") or day.get("location")
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                _record(stop.get("name"), stop.get("city") or day_city)
            else:
                _record(stop, day_city)
    for bucket in ("selected_hotels", "selected_activities"):
        for item in trip.get(bucket) or []:
            if isinstance(item, dict):
                _record(item.get("name"), item.get("city") or item.get("location"))
    for name, city in _derive_route_cities(trip).items():
        mapping.setdefault(name, city)
    return mapping


def _trip_cities(trip: dict[str, Any]) -> list[str]:
    """Ordered, unique cities the trip actually visits (day/stop evidence)."""
    ordered: list[str] = []
    seen: set[str] = set()

    def _push(city: Any) -> None:
        c = _clean_city(city)
        key = c.lower()
        if c and key not in seen:
            seen.add(key)
            ordered.append(c)

    for day in trip.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        _push(day.get("city") or day.get("location"))
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                _push(stop.get("city"))
    if ordered:
        return ordered
    # No structured city evidence — infer the visit order from transport legs.
    for city in _derive_route_cities(trip).values():
        _push(city)
    return ordered


def discovery_pool(trip: dict[str, Any]) -> list[dict[str, str]]:
    """Ordered ``[{kind, name, city}]`` candidate pool for the destination guide.

    Combines the user's own picks and planned stops with per-city top hotels,
    attractions and restaurants — deduped and round-robined across city × kind so
    the mixed-highlights default stays balanced across the whole route.
    """
    destination = _clean_city(trip.get("destination"))
    city_of = _place_cities(trip)
    cities = _trip_cities(trip) or ([destination] if destination else [])

    pool: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _resolve_city(name: str) -> str:
        return city_of.get(name.strip().lower()) or destination

    def _add(kind: str, name: str, city: str = "") -> None:
        name = str(name or "").strip()
        if not name:
            return
        bk = browse_kind(kind)
        key = (bk, name.lower())
        if key in seen:
            return
        seen.add(key)
        pool.append({"kind": bk, "name": name, "city": city or _resolve_city(name)})

    for h in trip.get("selected_hotels") or []:
        if isinstance(h, dict) and h.get("name"):
            _add("hotel", str(h["name"]), _clean_city(h.get("city") or h.get("location")))
    for a in trip.get("selected_activities") or []:
        if isinstance(a, dict) and a.get("name"):
            _add(
                a.get("kind") or "attraction",
                str(a["name"]),
                _clean_city(a.get("city") or a.get("location")),
            )
    for day in trip.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        day_city = _clean_city(day.get("city") or day.get("location"))
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                stop_name = str(stop.get("name") or "")
                stop_kind = str(stop.get("kind") or "").strip().lower()
                if _is_transport_stop(stop_name, stop_kind):
                    continue  # a flight/drive/train leg, not a place to discover
                _add(
                    stop.get("kind") or "attraction",
                    stop_name,
                    _clean_city(stop.get("city")) or day_city,
                )

    fallback_sources = cities or ([destination] if destination else [])
    ranked: dict[tuple[str, str], list[str]] = {}
    depth = 0
    for city in fallback_sources:
        for kind in _BROWSE_KINDS:
            names = places_cache.top_places(city, kind, n=_FALLBACK_CITY_PLACES)
            ranked[(city, kind)] = names
            depth = max(depth, len(names))
    for rank in range(depth):
        for city in fallback_sources:
            for kind in _BROWSE_KINDS:
                names = ranked.get((city, kind), [])
                if rank < len(names):
                    _add(kind, names[rank], city)
    return pool


def _build_row(
    ref: dict[str, str],
    destination: str,
    selected_names: dict[str, set[str]],
    itinerary_names: set[str],
) -> dict[str, Any]:
    """Lightweight browse row — one photo, no reviews (rich data is focus-only)."""
    name = ref["name"]
    kind = browse_kind(ref.get("kind"))
    city = ref.get("city") or destination
    info = places_cache.get_details(name, city or destination) or {}
    photos = places_cache.get_photos(name, city or destination, max_photos=1)
    key = name.strip().lower()
    bucket = "hotel" if kind == "hotel" else "attraction"
    selected = key in selected_names.get(bucket, set()) or key in itinerary_names
    return {
        "kind": kind,
        "name": info.get("name") or name,
        "city": city,
        "selected": selected,
        "rating": info.get("rating"),
        "review_count": info.get("review_count"),
        "address": info.get("address") or "",
        "summary": info.get("editorial_summary") or "",
        "photo": photos[0] if photos else None,
        "website": info.get("website") or "",
    }


def paged_places(
    trip: dict[str, Any] | None,
    *,
    city: str | None = None,
    kind: str | None = None,
    query: str | None = None,
    cursor: str | None = None,
    limit: int = _GUIDE_PAGE_SIZE,
    focus_name: str | None = None,
    focus_kind: str | None = None,
) -> dict[str, Any]:
    """Cursor-paged place discovery for the Lab 13 destination guide.

    Filters the balanced :func:`discovery_pool` by ``city``/``kind``/``query`` and
    returns one lightweight page plus counts and the available filter values. When
    ``focus_name`` is set, returns same-city, same-kind alternatives to that place
    (excluding it) so the focused inspector can offer contextual comparisons.
    """
    empty = {
        "items": [],
        "cursor": None,
        "total_count": 0,
        "remaining_count": 0,
        "available_cities": [],
        "available_kinds": [],
    }
    if not trip:
        return empty

    destination = _clean_city(trip.get("destination"))
    pool = discovery_pool(trip)

    available_cities: list[str] = []
    seen_city: set[str] = set()
    for entry in pool:
        c = entry.get("city") or ""
        k = c.lower()
        if c and k not in seen_city:
            seen_city.add(k)
            available_cities.append(c)
    available_kinds = [k for k in _BROWSE_KINDS if any(e["kind"] == k for e in pool)]

    focus_name = (focus_name or "").strip()
    if focus_name:
        fk = browse_kind(focus_kind)
        fcity = ""
        for entry in pool:
            if entry["name"].strip().lower() == focus_name.lower():
                fcity = entry.get("city") or ""
                break
        if not fcity:
            fcity = _place_cities(trip).get(focus_name.lower()) or destination
        filtered = [
            e
            for e in pool
            if e["kind"] == fk
            and (e.get("city") or "").lower() == fcity.lower()
            and e["name"].strip().lower() != focus_name.lower()
        ]
    else:
        want_city = _clean_city(city)
        if want_city.lower() in ("", "all", "all cities"):
            want_city = ""
        raw_kind = (kind or "").strip().lower()
        want_kind = "" if raw_kind in ("", "highlights", "all") else browse_kind(kind)
        q = (query or "").strip().lower()
        filtered = []
        for e in pool:
            if want_city and (e.get("city") or "").lower() != want_city.lower():
                continue
            if want_kind and e["kind"] != want_kind:
                continue
            if q and q not in f"{e['name']} {e.get('city', '')}".lower():
                continue
            filtered.append(e)

    selected_names = {
        "hotel": _selected_names(trip, "hotel"),
        "attraction": _selected_names(trip, "attraction"),
    }
    itinerary_names = _itinerary_names(trip)

    def _in_trip(entry: dict[str, str]) -> bool:
        key = entry["name"].strip().lower()
        bucket = "hotel" if browse_kind(entry.get("kind")) == "hotel" else "attraction"
        return key in selected_names.get(bucket, set()) or key in itinerary_names

    # New / not-yet-in-trip discoveries surface first; stable within each group so
    # paging stays deterministic across "show more" calls.
    filtered.sort(key=lambda e: 1 if _in_trip(e) else 0)

    total = len(filtered)
    try:
        start = max(0, int(cursor)) if cursor else 0
    except (TypeError, ValueError):
        start = 0
    page_size = max(1, min(int(limit or _GUIDE_PAGE_SIZE), _GUIDE_MAX_LIMIT))
    page = filtered[start : start + page_size]
    next_start = start + page_size
    next_cursor = str(next_start) if next_start < total else None
    remaining = max(0, total - next_start)

    items = [_build_row(e, destination, selected_names, itinerary_names) for e in page]
    return {
        "items": items,
        "cursor": next_cursor,
        "total_count": total,
        "remaining_count": remaining,
        "available_cities": available_cities,
        "available_kinds": available_kinds,
    }


_warmed_guides: set[str] = set()


def warm_guide(trip: dict[str, Any] | None) -> None:
    """Eagerly warm the destination-guide dataset so the first city/kind switch
    is instant instead of blocking on cold Places lookups.

    Builds the discovery pool (which warms the per-city ``top_places`` lists) then
    prefetches each candidate's details + one photo — matching what ``_build_row``
    needs. A no-op when Places is unconfigured; guarded so a trip version warms once.
    Intended to run fire-and-forget from a background task while the user reads the
    itinerary.
    """
    if not trip or not places_cache.is_configured():
        return
    sig = f"{trip.get('trip_id') or trip.get('id') or ''}|{trip.get('updated_at') or ''}"
    if sig in _warmed_guides:
        return
    _warmed_guides.add(sig)
    if len(_warmed_guides) > 64:  # crude bound — warming is idempotent anyway
        _warmed_guides.clear()
        _warmed_guides.add(sig)

    by_city: dict[str, list[str]] = {}
    for entry in discovery_pool(trip):
        by_city.setdefault(entry.get("city") or "", []).append(entry["name"])
    for city, names in by_city.items():
        places_cache.prefetch(names, city, max_photos=1, with_reviews=False)


def warm_view_items(trip: dict[str, Any] | None) -> None:
    """Warm the trip-panel gallery for the whole unfocused item set.

    Focus requests only block on the focused place; this runs afterwards from a
    background task so the rest of the gallery is warm for the next focus.
    """
    if not trip or not places_cache.is_configured():
        return
    refs = itinerary_items(trip, None)[:_MAX_GALLERY_ITEMS]
    places_cache.prefetch(
        [r["name"] for r in refs],
        str(trip.get("destination") or ""),
        max_photos=_MAX_PHOTOS_PER_ITEM,
    )


def _build_decisions(trip: dict[str, Any]) -> list[dict[str, Any]]:
    """Recorded comparisons, shaped for display. Read-only in this view."""
    if not get_settings().decisions_ui_enabled:
        return []
    out: list[dict[str, Any]] = []
    for decision in list_decisions(trip):
        out.append({
            "id": decision.id,
            "kind": decision.kind.value,
            "subject": decision.subject,
            "scope": decision.scope.model_dump(mode="json"),
            "rule": decision.rule.model_dump(mode="json"),
            "state": decision.state.value,
            "priced": decision.priced.value,
            "chosen_option_id": decision.active_option_id,
            "agent_option_id": decision.chosen_option_id,
            "override": (
                decision.override.model_dump(mode="json") if decision.override else None
            ),
            "effect": decision.effect.model_dump(mode="json"),
            "options": [
                {
                    "id": option.id,
                    "mode": option.mode.value,
                    "label": option.label,
                    "detail": option.detail,
                    "price": option.price.model_dump(mode="json") if option.price else None,
                    "priced": option.priced,
                    "unpriced_reason": (
                        option.unpriced_reason.value if option.unpriced_reason else None
                    ),
                    "duration_min": option.duration_min,
                    "door_to_door_min": option.door_to_door_min,
                    "duration_estimated": option.duration_estimated,
                    "rejected_because": option.rejected_because,
                    "source": option.source.model_dump(mode="json"),
                }
                for option in decision.options
            ],
        })
    return out


def build_view(
    trip: dict[str, Any] | None, focus: dict[str, Any] | None
) -> dict[str, Any]:
    """Build the complete, JSON-serializable trip-panel view-model.

    This is the frontend-agnostic contract. ``trip`` is the active trip dict
    (or ``None``); ``focus`` is ``{"kind", "name"}`` to zoom one item, else
    ``None``.
    """
    if not trip:
        return {
            "trip_id": None,
            "updated_at": None,
            "has_trip": False,
            "title": "Trip planner",
            "destination": "",
            "focus": None,
            "is_fallback": False,
            "empty_message": (
                "No active trip yet. Tell the agent where you want to go "
                "(e.g. *plan a 5-day trip to Goa in December for 2 adults*) "
                "and this panel will fill in with your itinerary, photos and "
                "reviews."
            ),
            "overview": None,
            "available_days": [],
            "items": [],
            "decisions": [],
        }

    destination = str(trip.get("destination") or "")
    fallback = is_fallback(trip, focus)
    refs = itinerary_items(trip, focus)[:_MAX_GALLERY_ITEMS]
    selected_names = {
        "hotel": _selected_names(trip, "hotel"),
        "attraction": _selected_names(trip, "attraction"),
    }
    itinerary_names = _itinerary_names(trip)
    city_map = _place_cities(trip)
    # A focus change re-renders a gallery the unfocused view already warmed, so
    # only the focused place blocks the response; the rest is warmed off-request.
    focus_name = str((focus or {}).get("name") or "").strip().lower()
    warm_names = [r["name"] for r in refs]
    if focus_name:
        warm_names = [n for n in warm_names if n.strip().lower() == focus_name] or warm_names[:1]
    places_cache.prefetch(warm_names, destination, max_photos=_MAX_PHOTOS_PER_ITEM)
    place_occurrences = _place_occurrence_index(trip)
    terminal_occurrences = _terminal_occurrence_index(trip)
    items = [
        _build_item(
            ref,
            destination,
            selected_names,
            itinerary_names,
            _terminal_occurrences(trip, ref["name"], terminal_occurrences)
            if ref["kind"] in {"airport", "station", "bus_station"}
            else _place_occurrences(trip, ref["name"], place_occurrences),
            city=city_map.get(ref["name"].strip().lower(), destination),
        )
        for ref in refs
    ]

    title = f"\u2708\ufe0f {destination}" if destination else "Trip planner"
    if focus and focus.get("name"):
        title = f"{title} \u2014 {focus['name']}"

    return {
        "trip_id": str(trip.get("trip_id") or "") or None,
        "updated_at": str(trip.get("updated_at") or "") or None,
        "has_trip": True,
        "title": title,
        "destination": destination,
        "focus": focus,
        "is_fallback": fallback,
        "empty_message": None,
        "overview": _build_overview(trip),
        "available_days": [
            int(day.get("day") or index + 1)
            for index, day in enumerate(trip.get("day_wise_itinerary") or [])
            if isinstance(day, dict)
        ],
        "items": items,
        "decisions": _build_decisions(trip),
    }


_MAX_NEWS_ITEMS = 4


def build_map_view(trip: dict[str, Any] | None) -> dict[str, Any]:
    """Build the interactive-map view-model (frontend-agnostic).

    Returns geocoded pins for the trip's hotels/activities (plus destination
    suggestions), each tagged with the itinerary day it belongs to, grouped
    into day-colored route bands. ``enabled`` reflects whether the browser
    Maps key is configured; the frontend hides the panel when it is false.
    Network use is limited to the (cached) Google Places lookups already used
    by the trip panel — no Routes/Directions calls happen here (the frontend
    draws per-day routes client-side).

    Resolving the pins, airport and itinerary here keeps them substitutable
    through this module; ``map_view`` performs the pure assembly.
    """
    key_configured = bool(_maps_browser_key())
    destination = str((trip or {}).get("destination") or "").strip()
    if not trip or not destination:
        return {
            "enabled": key_configured,
            "destination": destination,
            "center": None,
            "pins": [],
            "days": [],
            "available_days": [],
            "unscheduled_pin_ids": [],
            "airport": None,
            "empty_message": (
                "Start planning a trip and your hotels, attractions and daily "
                "routes will appear pinned on the map here."
            ),
        }

    pins = _map_pins(trip, destination)
    airport = None if any(pin["kind"] == "airport" for pin in pins) else _airport_pin(destination)
    itinerary_days = {
        int(day["day"]): day for day in build_itinerary(trip).get("days", [])
    }
    return map_view.build(trip, destination, pins, airport, itinerary_days, key_configured)


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
    if len(terminal_refs) != 2 or mode not in {"Flight", "Train", "Bus"}:
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
    if not arrival and departure_minutes is not None:
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
        duration_min: int,
        time_estimated: bool,
    ) -> dict[str, Any]:
        operation = departure_operation if role == "departure" else arrival_operation
        return {
            "name": name,
            "kind": kind,
            "time": time,
            "arrival_time": "",
            "duration_min": duration_min,
            "duration_estimated": True,
            "operational_time_display": (
                f"{_route_duration_display(duration_min)} {operation}"
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

    stop["name"] = f"{mode}: {terminal_refs[0][1]} to {terminal_refs[1][1]}"
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
        _terminal_stop(
            terminal_refs[1][1],
            terminal_refs[1][0],
            arrival,
            "arrival",
            arrival_buffer,
            arrival_estimated,
        ),
    ]


def _road_origin_stop(stop: dict[str, Any]) -> dict[str, Any] | None:
    if _intercity_transfer_mode(stop["name"], stop["kind"]) != "Drive":
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
    weekday_lines = summary.get("weekday_descriptions") or []
    open_now = summary.get("open_now")
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
    if not opening and open_now is True:
        opening = "Open now"
    elif not opening and open_now is False:
        opening = "May be closed now"

    concern = ""
    if matched and "closed" in matched.lower() and day_name:
        concern = f"Likely closed on {day_name}; review day assignment."
    elif open_now is False:
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


def _place_coords(name: str, destination: str) -> tuple[float, float] | None:
    """Look up a place's (lat, lng) from the cache. Network-but-cached; returns
    ``None`` when Places isn't configured or the place can't be resolved."""
    if not name or not destination or not places_cache.is_configured():
        return None
    try:
        coords = places_cache.place_coords(name, destination)
    except Exception:  # noqa: BLE001 — never let geocoding break the itinerary
        return None
    if coords:
        return (float(coords[0]), float(coords[1]))
    try:
        info = places_cache.get_details(name, destination) or {}
    except Exception:  # noqa: BLE001
        info = {}
    lat, lng = info.get("lat"), info.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return (float(lat), float(lng))

    # Retry without parenthetical qualifiers ("Place (Area)") which often
    # reduce match quality in text search.
    plain = re.sub(r"\s*\([^)]*\)", "", str(name or "")).strip()
    if plain and plain.lower() != str(name or "").strip().lower():
        try:
            coords = places_cache.place_coords(plain, destination)
        except Exception:  # noqa: BLE001
            return None
        if coords:
            return (float(coords[0]), float(coords[1]))
    return None


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
        route_mode = _intercity_transfer_mode(s["name"], s["kind"])
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


def _has_intercity_transfer(stops: list[dict[str, Any]]) -> bool:
    return any(
        _intercity_transfer_mode(str(stop.get("name") or ""), str(stop.get("kind") or ""))
        for stop in stops
    )


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
            if _intercity_transfer_mode(
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
            if _intercity_transfer_mode(
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

        if _has_intercity_transfer(stops):
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


def build_destination_overview(
    destination: str, *, include_news: bool = True
) -> dict[str, Any]:
    """Build a destination-level overview shown before any trip exists.

    Combines Google Places (photos, key attractions, reviews) with fresh
    Tavily news. Frontend-agnostic — consumed by ``GET /destination/overview``
    and rendered by the SPA. Network calls degrade gracefully: a missing API
    key just yields an empty section rather than an error.
    """
    destination = (destination or "").strip()
    if not destination:
        return {
            "destination": "",
            "summary": "",
            "rating": None,
            "review_count": 0,
            "photos": [],
            "key_attractions": [],
            "reviews": [],
            "news": [],
            "map_url": "",
        }

    attraction_names = places_cache.top_places(
        destination, "attraction", n=_MAX_OVERVIEW_ATTRACTIONS
    )
    places_cache.prefetch(attraction_names, destination, max_photos=2)

    photos: list[str] = []
    key_attractions: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    summary = ""
    for name in attraction_names:
        info = places_cache.get_summary(name, destination) or {}
        pics = places_cache.get_photos(name, destination, max_photos=2)
        photos.extend(pics)
        if not summary and info.get("editorial_summary"):
            summary = info["editorial_summary"]
        key_attractions.append(
            {
                "name": info.get("name") or name,
                "rating": info.get("rating"),
                "review_count": info.get("review_count"),
                "summary": info.get("editorial_summary") or "",
                "photo": pics[0] if pics else None,
            }
        )
        for r in (info.get("reviews") or [])[:1]:
            text = (r.get("text") or "").strip()
            if text:
                reviews.append(
                    {
                        "place": info.get("name") or name,
                        "rating": r.get("rating"),
                        "text": text,
                        "author": r.get("author") or "Guest",
                    }
                )

    rated = [a["rating"] for a in key_attractions if a.get("rating")]
    agg_rating = round(sum(rated) / len(rated), 1) if rated else None
    agg_reviews = sum(
        int(a["review_count"]) for a in key_attractions if a.get("review_count")
    )

    news: list[dict[str, str]] = []
    if include_news:
        news = _fetch_destination_news(destination)

    return {
        "destination": destination,
        "summary": summary,
        "rating": agg_rating,
        "review_count": agg_reviews,
        "photos": photos[:_MAX_GALLERY_ITEMS],
        "key_attractions": key_attractions,
        "reviews": reviews[:_MAX_REVIEWS_PER_ITEM * 3],
        "news": news,
        "map_url": build_map_url(destination, [a["name"] for a in key_attractions[:5]]),
    }


def _fetch_destination_news(destination: str) -> list[dict[str, str]]:
    """Fetch fresh travel news for ``destination`` via Tavily; never raises."""
    try:
        from tripplanner.tools import web_search

        data = web_search.search_raw(
            f"latest positive travel news, new openings and good updates for {destination}",
            max_results=_MAX_NEWS_ITEMS,
            topic="news",
        )
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for r in data.get("results", [])[:_MAX_NEWS_ITEMS]:
        if r.get("title"):
            out.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
            )
    return out

