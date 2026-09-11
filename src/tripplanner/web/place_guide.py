"""Destination-guide discovery and gallery item shaping.

Split out of ``trip_view`` so itinerary assembly, guide paging, and the
view-model facade can be read independently. ``trip_view`` re-exports the
public names so existing callers and tests stay on the facade.
"""

from __future__ import annotations

import re
from typing import Any

from tripplanner.config import get_settings
from tripplanner.web import places_cache
from tripplanner.web.gallery import (
    _itinerary_names,
    _selected_names,
    itinerary_items,
)
from tripplanner.web.transport import _transport_route_endpoints

_MAX_PHOTOS_PER_ITEM = 1
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


def _build_item(
    ref: dict[str, str],
    destination: str,
    selected_names: dict[str, set[str]],
    itinerary_names: set[str] | None = None,
    occurrences: list[dict[str, Any]] | None = None,
    city: str = "",
    with_reviews: bool = False,
    max_photos: int = 0,
) -> dict[str, Any]:
    name = ref["name"]
    kind = ref.get("kind", "place")
    lookup_context = city or destination
    info = (
        places_cache.get_summary(name, lookup_context)
        if with_reviews
        else places_cache.get_details(name, lookup_context)
    ) or {}
    photos = (
        places_cache.get_photos(name, lookup_context, max_photos=max_photos)
        if max_photos > 0
        else []
    )
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
    settings = get_settings()
    refs = itinerary_items(trip, None)[: settings.google_places_max_photos_per_request]
    places_cache.prefetch(
        [r["name"] for r in refs],
        str(trip.get("destination") or ""),
        max_photos=min(_MAX_PHOTOS_PER_ITEM, settings.google_places_max_photos_per_place),
        with_reviews=False,
    )


