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
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote

from tripplanner.config import get_settings
from tripplanner.tools import user_preferences
from tripplanner.web import places_cache

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

# Transport-name helpers live in ``transport`` (tech-debt #7), a leaf module
# shared by the gallery and map-pin builders; re-exported here for callers/tests.
from tripplanner.web.transport import (  # noqa: F401
    _canonical_transport_name,
    _intercity_transfer_mode,
    _normalized_stop_kind,
    _transport_route_endpoints,
    _transport_terminal_refs,
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

_MAX_GALLERY_ITEMS = 10
_MAX_PHOTOS_PER_ITEM = 3
_MAX_REVIEWS_PER_ITEM = 2
_FALLBACK_HOTELS = 2
_FALLBACK_ATTRACTIONS = 8


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


def itinerary_items(
    trip: dict[str, Any] | None, focus: dict[str, Any] | None
) -> list[dict[str, str]]:
    """Return ``[{kind, name}, ...]`` for the things to show.

    User's selected hotels and activities come first, followed by the destination's top hotels &
    attractions that aren't already selected — so adding something to the trip
    never hides the rest of the places you can still browse.

    When focused, keep the broader list but move the focused place to the top
    so the details pane can still surface alternatives for quick edits.
    """
    if not trip:
        return []

    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, name: str) -> None:
        key = (kind, name.strip().lower())
        if name and key not in seen:
            seen.add(key)
            items.append({"kind": kind, "name": name})

    for h in trip.get("selected_hotels") or []:
        if isinstance(h, dict) and h.get("name"):
            _add("hotel", str(h["name"]))
    for a in trip.get("selected_activities") or []:
        if isinstance(a, dict) and a.get("name"):
            _add("attraction", str(a["name"]))

    for day in trip.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                name = str(stop.get("name") or "").strip()
                kind = str(stop.get("kind") or "attraction").strip().lower()
            else:
                name = str(stop or "").strip()
                kind = "attraction"
            if name:
                _add(kind or "attraction", name)

    destination = str(trip.get("destination") or "").strip()
    if destination and len(items) < _MAX_GALLERY_ITEMS:
        for name in places_cache.top_places(destination, "hotel", n=_FALLBACK_HOTELS):
            _add("hotel", name)
        remaining = max(0, _MAX_GALLERY_ITEMS - len(items))
        for name in places_cache.top_places(
            destination, "attraction", n=min(_FALLBACK_ATTRACTIONS, remaining)
        ):
            _add("attraction", name)

    if focus and focus.get("name"):
        fk = str(focus.get("kind") or "attraction").strip().lower() or "attraction"
        fn = str(focus.get("name") or "").strip()
        if fn:
            # Ensure focus target exists and appears first.
            _add(fk, fn)
            key = (fk, fn.lower())
            items.sort(key=lambda it: 0 if (it["kind"], it["name"].strip().lower()) == key else 1)

    return items


def _selected_names(trip: dict[str, Any] | None, kind: str) -> set[str]:
    if not trip:
        return set()
    key = "selected_hotels" if kind == "hotel" else "selected_activities"
    out: set[str] = set()
    for it in trip.get(key) or []:
        if isinstance(it, dict) and it.get("name"):
            out.add(str(it["name"]).strip().lower())
    return out


def _itinerary_names(trip: dict[str, Any] | None) -> set[str]:
    """Lowercased names of every place already woven into the day-by-day
    itinerary. A place can be part of the itinerary without sitting in the
    ``selected_*`` buckets (e.g. the agent placed it directly), and the UI
    should treat those as already in the trip — showing "Remove", not "Add".
    """
    if not trip:
        return set()
    out: set[str] = set()
    for day in trip.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        stops = day.get("stops")
        if not isinstance(stops, list):
            continue
        for s in stops:
            if isinstance(s, dict):
                name = str(s.get("name") or "").strip()
            else:
                name = str(s or "").strip()
            if name:
                out.add(name.lower())
    return out


def _planned_place_names(trip: dict[str, Any]) -> set[str]:
    names = _selected_names(trip, "attraction")
    for day in trip.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                kind = str(stop.get("kind") or "attraction").strip().lower()
                name = str(stop.get("name") or "").strip()
            else:
                kind = "attraction"
                name = str(stop or "").strip()
            if kind in {"attraction", "activity", "meal", "restaurant"} and name:
                names.add(name.lower())
    return names


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
    selected = key in selected_names.get(kind, set()) or key in (itinerary_names or set())
    return {
        "kind": kind,
        "name": info.get("name") or name,
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


def _place_occurrence_index(trip: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Map each lowercased stop name to its ordered occurrences.

    Built once per view so per-item / per-pin lookups avoid rescanning the
    whole itinerary.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for day_index, entry in enumerate(trip.get("day_wise_itinerary") or []):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else day_index + 1
        for stop_index, raw_stop in enumerate(entry.get("stops") or []):
            stop_name = raw_stop.get("name") if isinstance(raw_stop, dict) else raw_stop
            index.setdefault(str(stop_name or "").strip().lower(), []).append(
                {
                    "day": day_num,
                    "stop": stop_index + 1,
                    "time": str(raw_stop.get("time") or "").strip()
                    if isinstance(raw_stop, dict)
                    else "",
                }
            )
    return index


def _place_occurrences(
    trip: dict[str, Any],
    name: str,
    index: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    idx = index if index is not None else _place_occurrence_index(trip)
    return [dict(occurrence) for occurrence in idx.get(name.strip().lower(), [])]


def _terminal_occurrence_index(trip: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Map each lowercased transport-terminal name to its ordered occurrences."""
    index: dict[str, list[dict[str, Any]]] = {}
    for day_index, entry in enumerate(trip.get("day_wise_itinerary") or []):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else day_index + 1
        for stop_index, raw_stop in enumerate(entry.get("stops") or [], start=1):
            if not isinstance(raw_stop, dict):
                continue
            refs = _transport_terminal_refs(
                str(raw_stop.get("name") or ""),
                str(raw_stop.get("kind") or "").strip().lower(),
            )
            if not refs:
                continue
            occurrence = {
                "day": day_num,
                "stop": stop_index,
                "time": str(raw_stop.get("time") or "").strip(),
            }
            seen: set[str] = set()
            for _, terminal_name in refs:
                key = terminal_name.strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                index.setdefault(key, []).append(occurrence)
    return index


def _terminal_occurrences(
    trip: dict[str, Any],
    name: str,
    index: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    idx = index if index is not None else _terminal_occurrence_index(trip)
    return [dict(occurrence) for occurrence in idx.get(name.strip().lower(), [])]


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
        }

    destination = str(trip.get("destination") or "")
    fallback = is_fallback(trip, focus)
    refs = itinerary_items(trip, focus)[:_MAX_GALLERY_ITEMS]
    selected_names = {
        "hotel": _selected_names(trip, "hotel"),
        "attraction": _selected_names(trip, "attraction"),
    }
    itinerary_names = _itinerary_names(trip)
    places_cache.prefetch(
        [r["name"] for r in refs], destination, max_photos=_MAX_PHOTOS_PER_ITEM
    )
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
        )
        for ref in refs
    ]

    title = f"\u2708\ufe0f {destination}" if destination else "Trip planner"
    if focus and focus.get("name"):
        title = f"{title} \u2014 {focus['name']}"

    return {
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
    }


_MAX_OVERVIEW_ATTRACTIONS = 6
_MAX_NEWS_ITEMS = 4


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


def _map_pins(trip: dict[str, Any], destination: str) -> list[dict[str, Any]]:
    """Geocoded pins for selected items + destination top-places (suggestions)."""
    itinerary = trip.get("day_wise_itinerary") or []
    selected = {
        "hotel": _selected_names(trip, "hotel"),
        "attraction": _selected_names(trip, "attraction"),
    }
    itinerary_names = _itinerary_names(trip)

    # Structured itinerary stops are authoritative for what should appear on
    # the map and in which order/day. Keep an explicit day map so duplicated
    # names across sources don't lose their itinerary day assignment.
    explicit_day_by_name: dict[str, int] = {}

    # (kind, name) in display order: user picks first, then suggestions.
    refs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(kind: str, name: str) -> None:
        key = (name or "").strip().lower()
        if kind == "hotel" and any(
            existing_kind == "hotel" and _hotel_identity_matches(existing_name, name)
            for existing_kind, existing_name in refs
        ):
            return
        if name and key not in seen:
            seen.add(key)
            refs.append((kind, name))

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
            terminal_refs = _transport_terminal_refs(name, kind)
            if terminal_refs:
                if _intercity_transfer_mode(name, kind) == "Drive" and has_route_anchor:
                    continue
                for terminal_kind, terminal_name in terminal_refs:
                    _add(terminal_kind, terminal_name)
                    explicit_day_by_name.setdefault(terminal_name.lower(), day_num)
                continue
            if kind in {"flight", "transport"}:
                continue
            if kind not in {"hotel", "attraction", "meal", "restaurant"}:
                kind = _infer_kind_from_name(name)
            _add(kind, name)
            explicit_day_by_name.setdefault(name.lower(), day_num)
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

    places_cache.prefetch(
        [n for _, n in refs], destination, max_photos=1, with_reviews=False
    )

    place_occurrences = _place_occurrence_index(trip)
    pins: list[dict[str, Any]] = []
    for i, (kind, name) in enumerate(refs):
        info = places_cache.get_details(name, destination) or {}
        provider_name = str(info.get("name") or "").strip()
        if (
            provider_name
            and kind not in {"airport", "station", "bus_station"}
            and not _provider_name_matches(name, provider_name)
        ):
            continue
        lat, lng = info.get("lat"), info.get("lng")
        if lat is None or lng is None:
            continue
        photos = places_cache.get_photos(name, destination, max_photos=1)
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


def build_map_view(trip: dict[str, Any] | None) -> dict[str, Any]:
    """Build the interactive-map view-model (frontend-agnostic).

    Returns geocoded pins for the trip's hotels/activities (plus destination
    suggestions), each tagged with the itinerary day it belongs to, grouped
    into day-colored route bands. ``enabled`` reflects whether the browser
    Maps key is configured; the frontend hides the panel when it is false.
    Network use is limited to the (cached) Google Places lookups already used
    by the trip panel — no Routes/Directions calls happen here (the frontend
    draws per-day routes client-side).
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
    terminal_kinds = {"airport", "station", "bus_station"}
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
        elif pin["kind"] in terminal_kinds:
            pin["occurrences"] = _terminal_occurrences(
                trip, str(pin["_source_name"]), terminal_occurrences
            )

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
            (pin for candidate, pin in pin_by_name.items() if needle in candidate or candidate in needle),
            None,
        )
        if partial:
            return partial
        return None

    # Structured days are authoritative and may reuse the same place on
    # multiple days. A pin has one primary day for display, while day routes
    # can reference it wherever the itinerary includes it.
    by_day: dict[int, list[str]] = {}
    route_pin_ids_by_day: dict[int, list[str]] = {}
    intercity_modes_by_day: dict[int, dict[tuple[str, str], str]] = {}
    route_circuit_ids_by_day: dict[int, dict[tuple[str, str], str]] = {}
    transfer_metrics_by_circuit: dict[str, dict[str, float]] = {}
    transfer_mode_by_day: dict[int, str] = {}
    transfer_days: set[int] = set()
    for idx, entry in enumerate(trip.get("day_wise_itinerary") or []):
        if not isinstance(entry, dict) or not isinstance(entry.get("stops"), list):
            continue
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        route_ids = route_pin_ids_by_day.setdefault(day_num, [])
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
                    intercity_modes_by_day.setdefault(day_num, {})[edge] = "Bus"
                    if pending_route_circuit_id:
                        route_circuit_ids_by_day.setdefault(day_num, {})[
                            edge
                        ] = pending_route_circuit_id
                    route_ids.append(pending_bus_destination_id)
                    pending_bus_destination_id = None
                    pending_intercity_mode = None
                    pending_route_circuit_id = None
                transfer_days.add(day_num)
                transfer_mode_by_day[day_num] = mode
                circuit_id = _route_circuit_id(day_num, stop_index, mode)
                if isinstance(stop, dict):
                    saved_metrics = {
                        metric: float(stop[metric])
                        for metric in ("distance_km", "duration_min")
                        if isinstance(stop.get(metric), (int, float)) and stop[metric] > 0
                    }
                    if saved_metrics:
                        transfer_metrics_by_circuit[circuit_id] = saved_metrics
                terminal_refs = _transport_terminal_refs(str(name or ""), kind)
                terminal_ids: list[str] = []
                for terminal_kind, terminal_name in terminal_refs:
                    terminal_pin = _pin_for_stop(terminal_name, terminal_kind)
                    if terminal_pin:
                        terminal_ids.append(str(terminal_pin["id"]))
                if len(terminal_ids) == len(terminal_refs) and len(terminal_ids) >= 2:
                    for terminal_id in terminal_ids:
                        if terminal_id not in by_day.setdefault(day_num, []):
                            by_day[day_num].append(terminal_id)
                    route_ids.append(terminal_ids[0])
                    if mode == "Bus":
                        pending_intercity_mode = mode
                        pending_route_circuit_id = circuit_id
                        pending_bus_destination_id = terminal_ids[-1]
                    else:
                        route_ids.append(terminal_ids[-1])
                        intercity_modes_by_day.setdefault(day_num, {})[
                            (terminal_ids[0], terminal_ids[-1])
                        ] = mode
                        route_circuit_ids_by_day.setdefault(day_num, {})[
                            (terminal_ids[0], terminal_ids[-1])
                        ] = circuit_id
                else:
                    if not route_ids and terminal_refs:
                        origin_pin = _pin_for_stop(terminal_refs[0][1], terminal_refs[0][0])
                        if origin_pin:
                            origin_id = str(origin_pin["id"])
                            if origin_id not in by_day.setdefault(day_num, []):
                                by_day[day_num].append(origin_id)
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
                intercity_modes_by_day.setdefault(day_num, {})[edge] = "Bus"
                if pending_route_circuit_id:
                    route_circuit_ids_by_day.setdefault(day_num, {})[
                        edge
                    ] = pending_route_circuit_id
                route_ids.append(pending_bus_destination_id)
                pending_bus_destination_id = None
                pending_intercity_mode = None
                pending_route_circuit_id = None
            pin = _pin_for_stop(name, kind)
            if pin and pin["id"] not in by_day.setdefault(day_num, []):
                by_day[day_num].append(pin["id"])
            if pin:
                pin_id = str(pin["id"])
                if pending_intercity_mode and route_ids:
                    terminal_kinds = {"airport", "station", "bus_station"}
                    if pin["kind"] not in terminal_kinds:
                        intercity_modes_by_day.setdefault(day_num, {})[
                            (route_ids[-1], pin_id)
                        ] = pending_intercity_mode
                        if pending_route_circuit_id:
                            route_circuit_ids_by_day.setdefault(day_num, {})[
                                (route_ids[-1], pin_id)
                            ] = pending_route_circuit_id
                    if pending_intercity_mode not in {"Drive", "Bus"} or pin["kind"] == "hotel":
                        pending_intercity_mode = None
                        pending_route_circuit_id = None
                route_ids.append(pin_id)
        if pending_bus_destination_id and route_ids:
            edge = (route_ids[-1], pending_bus_destination_id)
            intercity_modes_by_day.setdefault(day_num, {})[edge] = "Bus"
            if pending_route_circuit_id:
                route_circuit_ids_by_day.setdefault(day_num, {})[
                    edge
                ] = pending_route_circuit_id
            route_ids.append(pending_bus_destination_id)

    unscheduled: list[str] = []
    for p in pins:
        if p["day"]:
            day_ids = by_day.setdefault(p["day"], [])
            if p["id"] not in day_ids:
                day_ids.append(p["id"])
        else:
            unscheduled.append(p["id"])

    pin_by_id = {p["id"]: p for p in pins}

    def _occurrence_stop(pin_id: str, day: int) -> int:
        pin = pin_by_id[pin_id]
        occurrence = next(
            (item for item in pin.get("occurrences") or [] if item.get("day") == day),
            None,
        )
        return int(occurrence.get("stop")) if occurrence and occurrence.get("stop") else 10_000

    def _local_pin_ids(day: int, route_ids: list[str]) -> list[str]:
        intercity_edges = intercity_modes_by_day.get(day) or {}
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
            pin_by_id[pin_id]["kind"] not in {"airport", "station", "bus_station"}
            for pin_id in destination_ids
        )
        return destination_ids if has_destination_stop else route_ids[: start_index + 1]

    def _resolved_stay_ids(day: int) -> list[str]:
        itinerary_day = itinerary_days.get(day) or {}
        resolved: list[str] = []
        for stop in itinerary_day.get("stops") or []:
            if stop.get("kind") != "hotel":
                continue
            pin = _pin_for_stop(stop.get("name"))
            if pin and str(pin["id"]) not in resolved:
                resolved.append(str(pin["id"]))
        return resolved

    def _carried_stay_id(day: int) -> str | None:
        itinerary_stops = (itinerary_days.get(day) or {}).get("stops") or []
        if not itinerary_stops:
            return None
        first_stop = itinerary_stops[0]
        if first_stop.get("kind") != "hotel" or (
            str(first_stop.get("note") or "").strip().lower()
            != "start from your stay"
        ):
            return None
        pin = _pin_for_stop(first_stop.get("name"))
        return str(pin["id"]) if pin else None

    stay_ids = [p["id"] for p in pins if p["kind"] == "hotel" and p["selected"]]
    days = []
    for d in sorted(by_day):
        ids = sorted(by_day[d], key=lambda pin_id: _occurrence_stop(pin_id, d))
        is_transfer_day = d in transfer_days
        resolved_stay_ids = _resolved_stay_ids(d)
        if resolved_stay_ids and not is_transfer_day:
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
        if stay_id and not is_transfer_day:
            ids = [stay_id, *(pid for pid in ids if pid != stay_id), stay_id]
            if len(set(ids)) == 1:
                ids = [stay_id]
        if is_transfer_day:
            route_ids = route_pin_ids_by_day.get(d, [])
            carried_stay_id = _carried_stay_id(d)
            if carried_stay_id:
                if route_ids and pin_by_id[route_ids[0]]["kind"] == "origin":
                    origin_id = route_ids.pop(0)
                    intercity_modes = intercity_modes_by_day.get(d) or {}
                    replacement_edges = {
                        (carried_stay_id, end_id): mode
                        for (start_id, end_id), mode in intercity_modes.items()
                        if start_id == origin_id
                    }
                    if replacement_edges:
                        intercity_modes_by_day.setdefault(d, {}).update(replacement_edges)
                        intercity_modes_by_day[d] = {
                            edge: mode
                            for edge, mode in intercity_modes_by_day[d].items()
                            if edge[0] != origin_id
                        }
                    route_circuit_ids = route_circuit_ids_by_day.get(d) or {}
                    replacement_circuit_edges = {
                        (carried_stay_id, end_id): circuit_id
                        for (start_id, end_id), circuit_id in route_circuit_ids.items()
                        if start_id == origin_id
                    }
                    if replacement_circuit_edges:
                        route_circuit_ids_by_day.setdefault(d, {}).update(
                            replacement_circuit_edges
                        )
                        route_circuit_ids_by_day[d] = {
                            edge: circuit_id
                            for edge, circuit_id in route_circuit_ids_by_day[d].items()
                            if edge[0] != origin_id
                        }
                route_ids = [
                    carried_stay_id,
                    *(pin_id for pin_id in route_ids if pin_id != carried_stay_id),
                ]
                if len(route_ids) >= 2:
                    first_edge = (route_ids[0], route_ids[1])
                    intercity_modes_by_day.setdefault(d, {}).setdefault(
                        first_edge, transfer_mode_by_day[d]
                    )
                for resolved_stay_id in resolved_stay_ids[1:]:
                    if resolved_stay_id not in route_ids:
                        route_ids.append(resolved_stay_id)
            ids = route_ids
        else:
            route_ids = [
                pid
                for pid in ids
                if pin_by_id[pid]["kind"] not in {"airport", "station", "bus_station"}
            ]
        intercity_modes = intercity_modes_by_day.get(d)
        legs = _route_legs_for_day(
            route_ids,
            pin_by_id,
            intercity_modes,
            route_circuit_ids_by_day.get(d),
            transfer_metrics_by_circuit,
        )
        route = _route_stats_for_day(route_ids, pin_by_id)
        if intercity_modes:
            distance = round(sum(float(leg["distance_km"]) for leg in legs), 1)
            duration = sum(int(leg["duration_min"]) for leg in legs)
            modes = list(dict.fromkeys(intercity_modes.values()))
            if any(not leg.get("intercity") for leg in legs):
                modes.append("local")
            route = {
                "distance_km": distance,
                "duration_min": duration,
                "mode": " + ".join(modes),
                "distance_display": f"{distance:.1f} km",
                "duration_display": _route_duration_display(duration),
            }
        days.append(
            {
                "day": d,
                "label": f"Day {d}",
                "context_name": str(
                    (itinerary_days.get(d) or {}).get("title") or destination
                ),
                "color": _day_color(d),
                "pin_ids": ids,
                "circuit_pin_ids": _local_pin_ids(d, route_ids),
                "route": route,
                "legs": legs,
            }
        )
    for day in days:
        itinerary_day = itinerary_days.get(int(day["day"]))
        if itinerary_day:
            day["schedule"] = itinerary_day.get("schedule")

    road_circuits: list[dict[str, Any]] = []
    days_by_number = {int(day["day"]): day for day in days}
    for idx, entry in enumerate(trip.get("day_wise_itinerary") or []):
        if not isinstance(entry, dict) or not isinstance(entry.get("stops"), list):
            continue
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        normalized = _normalize_map_stops(entry["stops"])
        if not any(stop["mode"] in {"Drive", "Bus"} for stop in normalized):
            continue
        day = days_by_number.get(day_num)
        origin_fallbacks: list[str] = []
        carried_stay = _carried_stay_id(day_num)
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
                normalized, stop_index - 1, _pin_for_stop, origin_fallbacks
            )
            if len(ordered) < 2:
                continue
            edges = list(zip(ordered, ordered[1:]))
            saved_metrics = transfer_metrics_by_circuit.get(circuit_id)
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
            circuit_pin_ids = [
                legs[0]["from_pin_id"], *(leg["to_pin_id"] for leg in legs)
            ]
            road_circuits.append({
                "id": circuit_id,
                "day": day_num,
                "mode": mode,
                "label": str(stop["name"] or mode),
                "pin_ids": circuit_pin_ids,
                "waypoints": [
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
                ],
                "legs": legs,
                "route": {
                    "distance_km": distance,
                    "duration_min": duration,
                    "mode": mode,
                    "distance_display": f"{distance:.1f} km",
                    "duration_display": _route_duration_display(duration),
                },
            })

    scheduled_ids = {pin_id for day in days for pin_id in day["pin_ids"]}
    unscheduled = [pin_id for pin_id in unscheduled if pin_id not in scheduled_ids]

    # Map center: average of all pin coords (incl. airport) for an initial
    # viewport; the frontend will fit bounds precisely.
    coords = [(p["lat"], p["lng"]) for p in pins]
    if airport:
        coords.append((airport["lat"], airport["lng"]))
    center = (
        {"lat": sum(c[0] for c in coords) / len(coords),
         "lng": sum(c[1] for c in coords) / len(coords)}
        if coords
        else None
    )
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

    if kind == "meal":
        return f"{symbol}500-1,500 pp (est.)"
    if kind == "attraction":
        return f"{symbol}300-1,200 tickets (est.)"
    if kind == "hotel":
        return f"{symbol}6,000-15,000 / night (est.)"
    return ""


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

    # Pre-load all place coords so we can calculate route stats per day.
    # Use EVERY itinerary stop name, not just selected buckets, so added meals,
    # markets, and non-selected places still contribute to route metrics.
    place_coords_map: dict[str, tuple[float, float]] = {}
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
    for name in stop_names.values():
        coords = _place_coords(name, destination)
        if coords:
            place_coords_map[name.strip().lower()] = coords

    days: list[dict[str, Any]] = []
    total_stops = 0
    total_booked = 0
    current_hotel = ordered_hotels[0] if ordered_hotels else ""
    for idx, entry in enumerate(itin):
        if not isinstance(entry, dict):
            entry = {"plan": str(entry)}
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        stops = []
        day_coords: list[tuple[float, float]] = []
        pending_bus_arrival: dict[str, Any] | None = None
        for raw_stop_index, raw in enumerate(entry.get("stops") or [], start=1):
            s = _normalize_stop(raw, hotels, activities)
            if s:
                route_mode = _intercity_transfer_mode(s["name"], s["kind"])
                if route_mode in {"Drive", "Bus"}:
                    s["route_circuit_id"] = _route_circuit_id(
                        day_num, raw_stop_index, route_mode
                    )
                is_place = s["kind"] not in {"flight", "transport"}
                summary = (
                    places_cache.get_details(s["name"], destination) or {}
                    if is_place
                    else {}
                )
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
                if pending_bus_arrival and s["kind"] not in {
                    "attraction",
                    "meal",
                    "restaurant",
                }:
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
                # Accumulate coords for route stats.
                for rendered_stop in rendered_stops:
                    coords = place_coords_map.get(
                        str(rendered_stop["name"] or "").strip().lower()
                    )
                    if coords:
                        day_coords.append(coords)
                if s["booked"]:
                    total_booked += 1

        if pending_bus_arrival:
            pending_bus_arrival["color"] = _day_color(day_num)
            stops.append(pending_bus_arrival)
            coords = place_coords_map.get(
                str(pending_bus_arrival["name"] or "").strip().lower()
            )
            if coords:
                day_coords.append(coords)

        hotel_stops = [stop for stop in stops if stop["kind"] == "hotel"]
        distinct_hotels = {
            str(stop.get("name") or "").strip().lower() for stop in hotel_stops
        }
        has_intercity_transfer = any(
            _intercity_transfer_mode(
                str(stop.get("name") or ""), str(stop.get("kind") or "")
            )
            for stop in stops
        )
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
        if (
            idx > 0
            and has_intercity_transfer
            and current_hotel
            and first_transfer_index >= 0
            and (first_hotel_index < 0 or first_transfer_index < first_hotel_index)
        ):
            anchor = _normalize_stop(
                {"name": current_hotel, "kind": "hotel"}, hotels, activities
            )
            if anchor:
                anchor["duration_min"] = None
                anchor["color"] = _day_color(day_num)
                anchor["note"] = "Start from your stay"
                if stops and stops[0]["kind"] == "origin":
                    stops.pop(0)
                stops.insert(0, anchor)
                hotel_stops.insert(0, anchor)
        if (
            not has_intercity_transfer
            and not _is_overnight_travel_day(entry)
            and len(distinct_hotels) < 2
        ):
            anchor = hotel_stops[0] if hotel_stops else None
            if anchor is None and current_hotel:
                anchor = _normalize_stop(
                    {"name": current_hotel, "kind": "hotel"}, hotels, activities
                )
                if anchor:
                    summary = places_cache.get_details(anchor["name"], destination) or {}
                    opening, concern = _opening_hint(
                        summary, str(entry.get("date") or "")
                    )
                    anchor["duration_min"] = None
                    anchor["opening_hours"] = opening
                    anchor["concern"] = concern
                    anchor["cost_display"] = _cost_hint(
                        "hotel",
                        summary,
                        selected_prices.get(anchor["name"].strip().lower(), 0.0),
                        symbol,
                    )
                    anchor["insight"] = _insight_hint(
                        anchor["name"], "hotel", summary
                    )
                    anchor["color"] = _day_color(day_num)
            if anchor:
                middle = [stop for stop in stops if stop["kind"] != "hotel"]
                if not middle:
                    stops = [dict(anchor)]
                else:
                    hotel_start = dict(anchor)
                    hotel_start["note"] = hotel_start.get("note") or "Start from your stay"
                    hotel_return = dict(hotel_stops[-1] if len(hotel_stops) > 1 else anchor)
                    hotel_return["note"] = hotel_return.get("note") or "Return to your stay"
                    stops = [hotel_start, *middle, hotel_return]

        if has_intercity_transfer and hotel_stops:
            last_hotel_index = max(
                index for index, stop in enumerate(stops) if stop["kind"] == "hotel"
            )
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
            if (
                last_transfer_index < last_hotel_index
                and hotel_coords
                and return_from_coords
            ):
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

        rendered_hotels = [stop for stop in stops if stop["kind"] == "hotel"]
        if rendered_hotels:
            current_hotel = str(rendered_hotels[-1].get("name") or current_hotel)

        local_indexes = _local_route_stop_indexes(stops)
        local_stops = [
            stop for stop_index, stop in enumerate(stops, start=1) if stop_index in local_indexes
        ]
        day_coords = []
        previous_coords: tuple[float, float] | None = None
        previous_name = ""
        for stop in local_stops:
            coords = place_coords_map.get(str(stop.get("name") or "").strip().lower())
            if coords:
                if previous_coords:
                    stop["travel_from_previous"] = _route_stats_for_distance(
                        _haversine_km(previous_coords, coords),
                        from_name=previous_name,
                        to_name=str(stop.get("name") or ""),
                    )
                day_coords.append(coords)
                previous_coords = coords
                previous_name = str(stop.get("name") or "")
        total_stops += sum(
            stop["kind"] not in {"airport", "station", "bus_station", "origin"}
            for stop in stops
        )

        # Calculate route stats for the day.
        route = _route_stats_for_day_coords(day_coords)
        transport_preferences = (
            (trip.get("preferences_snapshot") or {}).get("transport_preferences") or {}
        )
        _enrich_drive_transfer_timing(stops, place_coords_map, transport_preferences)
        _enrich_stop_timing(stops)
        for stop_index, stop in enumerate(stops[1:], start=1):
            previous = stops[stop_index - 1]
            if stop.get("kind") != "hotel" or stop.get("time"):
                continue
            estimated_time: int | None = None
            if previous.get("kind") == "airport":
                previous_time = _clock_minutes(previous.get("time"))
                has_transfer = isinstance(
                    (stop.get("travel_from_previous") or {}).get("duration_min"),
                    (int, float),
                ) and (stop.get("travel_from_previous") or {}).get("duration_min") > 0
                if previous_time is not None and has_transfer:
                    transfer_minutes = int(
                        (stop.get("travel_from_previous") or {}).get("duration_min") or 0
                    )
                    airport_exit_minutes = int(previous.get("duration_min") or 0)
                    estimated_time = (
                        previous_time + airport_exit_minutes + transfer_minutes
                    )
            elif _intercity_transfer_mode(
                str(previous.get("name") or ""), str(previous.get("kind") or "")
            ) == "Drive":
                estimated_time = _clock_minutes(
                    previous.get("arrival_time") or previous.get("departure_time")
                )
            if estimated_time is not None:
                stop["time"] = _clock_display(estimated_time)
                stop["time_estimated"] = True
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

