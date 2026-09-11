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

import re
from typing import Any

from tripplanner.config import get_settings
from tripplanner.decisions.provenance import build_provenance
from tripplanner.decisions.store import list_decisions
from tripplanner.decisions.trip_cost import (
    build_cost_ledger,
    compare_trip_decisions,
    plan_price_rechecks,
)
from tripplanner.tools import user_preferences
from tripplanner.tools.trip_effort import coherence_notes, pacing_statement
from tripplanner.tools.trip_validation import planning_completion_gaps
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
from tripplanner.web import destination_overview as _destination_overview
from tripplanner.web.destination_overview import (  # noqa: F401
    _MAX_NEWS_ITEMS,
    _fetch_destination_news,
    _overview_places,
)
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
from tripplanner.web.place_guide import (  # noqa: F401
    _BROWSE_KINDS,
    _FALLBACK_CITY_PLACES,
    _GUIDE_MAX_LIMIT,
    _GUIDE_PAGE_SIZE,
    _HOTEL_ALIASES,
    _MAX_PHOTOS_PER_ITEM,
    _MAX_REVIEWS_PER_ITEM,
    _RESTAURANT_ALIASES,
    _TRANSPORT_KINDS,
    _TRANSPORT_PREFIXES,
    _arrival_city,
    _build_item,
    _build_row,
    _clean_city,
    _derive_route_cities,
    _is_transport_stop,
    _place_cities,
    _trip_cities,
    browse_kind,
    discovery_pool,
    paged_places,
    warm_guide,
    warm_view_items,
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


def build_destination_overview(
    destination: str, *, include_news: bool = True
) -> dict[str, Any]:
    return _destination_overview.build_destination_overview(
        destination,
        include_news=include_news,
        places_loader=_overview_places,
    )

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


def _member_text(value: Any) -> str:
    """One readable phrase from a per-traveller field.

    Chat learning stores these as lists ("mobility": ["uses walking stick"]),
    while the profile editor stores a plain string. Both reach this view.
    """
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


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
        mobility = next(
            (text for m in senior_members if (text := _member_text(m.get("mobility")))), ""
        )
        label = "\U0001f475 Senior-friendly" + (f" ({mobility})" if mobility else "")
        out.append(label)
    if pet_members:
        out.append("\U0001f43e Pet-friendly")

    diets: set[str] = set()
    for m in members:
        d = _member_text(m.get("dietary"))
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
    cost_evidence = build_cost_ledger(trip).as_dict()
    offer_benefits = (
        prefs.get("offer_benefits")
        if isinstance(prefs, dict) and isinstance(prefs.get("offer_benefits"), list)
        else []
    )
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
        "cost_evidence": cost_evidence,
        "offer_comparisons": compare_trip_decisions(trip, benefits=offer_benefits),
        "price_rechecks": plan_price_rechecks(trip),
        "price_recheck_results": [
            row
            for row in trip.get("price_recheck_results") or []
            if isinstance(row, dict)
        ],
        "cost_baseline": _build_cost_baseline(trip, symbol),
        "provenance": build_provenance(trip),
        "budget": build_budget(trip, cost_evidence=cost_evidence),
        "weather": build_weather(trip),
        "effort_notes": coherence_notes(trip),
        "pacing_statement": pacing_statement(trip),
        "family_pills": family_pills(prefs),
        "constraints": [
            str(c).strip()
            for c in (trip.get("trip_constraints") or [])
            if str(c).strip()
        ],
    }


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
                    "mode": option.mode.value if option.mode else None,
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
                    "lodging": (
                        option.lodging.model_dump(
                            mode="json",
                            exclude={"provider_ref"},
                        )
                        if option.lodging
                        else None
                    ),
                    "flight": (
                        option.flight.model_dump(
                            mode="json",
                            exclude={"provider_ref"},
                        )
                        if option.flight
                        else None
                    ),
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
            "feedback": {"count": 0},
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
    settings = get_settings()
    photo_limit = settings.google_places_max_photos_per_request
    photo_names = warm_names[:photo_limit]
    places_cache.prefetch(photo_names, destination, max_photos=1, with_reviews=False)
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
            with_reviews=bool(focus_name and ref["name"].strip().lower() == focus_name),
            max_photos=(
                min(_MAX_PHOTOS_PER_ITEM, settings.google_places_max_photos_per_place)
                if ref["name"] in photo_names
                else 0
            ),
        )
        for ref in refs
    ]

    title = f"\u2708\ufe0f {destination}" if destination else "Trip planner"
    if trip.get("forked_from"):
        title = f"{title} \u00b7 my copy"
    if focus and focus.get("name"):
        title = f"{title} \u2014 {focus['name']}"

    return {
        "trip_id": str(trip.get("trip_id") or "") or None,
        "updated_at": str(trip.get("updated_at") or "") or None,
        "has_trip": True,
        "title": title,
        "forked_from": str(trip.get("forked_from") or "") or None,
        "destination": destination,
        "focus": focus,
        "is_fallback": fallback,
        "empty_message": None,
        "feedback": dict(trip.get("feedback") or {"count": 0}),
        "overview": _build_overview(trip),
        "alerts": planning_completion_gaps(trip),
        "available_days": [
            int(day.get("day") or index + 1)
            for index, day in enumerate(trip.get("day_wise_itinerary") or [])
            if isinstance(day, dict)
        ],
        "items": items,
        "decisions": _build_decisions(trip),
    }



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
            "unmapped_stops": [],
            "airport": None,
            "empty_message": (
                "Start planning a trip and your hotels, attractions and daily "
                "routes will appear pinned on the map here."
            ),
        }

    unmapped: list[dict[str, Any]] = []
    pins = _map_pins(trip, destination, unmapped)
    airport = None if any(pin["kind"] == "airport" for pin in pins) else _airport_pin(destination)
    itinerary_days = {
        int(day["day"]): day for day in build_itinerary(trip).get("days", [])
    }
    return map_view.build(
        trip, destination, pins, airport, itinerary_days, key_configured, unmapped
    )



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


from tripplanner.web.itinerary_view import (  # noqa: E402, F401
    _COST_HINT_BANDS,
    _DEFAULT_STOP_DURATION_MIN,
    _PRICE_LEVEL_HINT,
    _STOP_KINDS,
    _append_return_to_stay,
    _cost_hint,
    _duration_hint,
    _estimate_hotel_arrival_times,
    _first_sentence,
    _google_maps_day_url,
    _google_travel_mode,
    _has_intercity_transfer,
    _implied_terminal_hop,
    _infer_stop_kind,
    _insert_transfer_day_stay_anchor,
    _insight_hint,
    _is_overnight_travel_day,
    _itinerary_from_selections,
    _itinerary_place_coords,
    _measure_local_route,
    _nearest_neighbor_order,
    _normalize_stop,
    _opening_hint,
    _ordered_selected,
    _popularity_score,
    _reachability_hint,
    _render_day_stops,
    _road_origin_stop,
    _selected_price_map,
    _split_contiguous,
    _terminal_kind,
    _transport_terminal_stops,
    _weekday_name,
    _wrap_day_in_stay,
    build_itinerary,
)
