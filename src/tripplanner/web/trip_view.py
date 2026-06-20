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

from tripplanner.tools import user_preferences
from tripplanner.web import places_cache

_MAX_GALLERY_ITEMS = 10
_MAX_PHOTOS_PER_ITEM = 3
_MAX_REVIEWS_PER_ITEM = 2
_FALLBACK_HOTELS = 2
_FALLBACK_ATTRACTIONS = 8

# ISO code → display symbol. Anything not listed is shown verbatim (already a
# symbol, or an exotic code we just print as-is).
_CURRENCY_SYMBOLS = {
    "INR": "\u20b9",
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "JPY": "\u00a5",
    "THB": "\u0e3f",
    "AED": "AED ",
    "AUD": "A$",
    "SGD": "S$",
    "CAD": "C$",
    "CHF": "CHF ",
}
_PRICE_KEYS = ("price", "total_price", "total", "cost", "amount", "fare")
_TRAVELER_RE = re.compile(
    r"(\d+)\s*(adults?|children|child|kids?|elderly|seniors?|infants?|people|travell?ers?|pax)",
    re.I,
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


def fmt_money(value: Any, symbol: str = "\u20b9") -> str:
    if isinstance(value, (int, float)) and value:
        return f"{symbol}{value:,.0f}"
    return "\u2014"


def currency_symbol(trip: dict[str, Any] | None) -> str:
    """Resolve the plan's sticky display currency to a render-ready symbol.

    The trip agent stores its chosen currency on the plan (``currency``) as
    either an ISO code (``"USD"``) or a symbol (``"$"``). Defaults to ₹ to match
    the agent's domestic-India default.
    """
    raw = str((trip or {}).get("currency") or "").strip()
    if not raw:
        return "\u20b9"
    return _CURRENCY_SYMBOLS.get(raw.upper(), raw)


def _to_number(value: Any) -> float:
    """Best-effort numeric coercion ("₹8,500", "8500", 8500.0 → 8500.0)."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.]", "", value.replace(",", ""))
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    return 0.0


def _sum_item_prices(items: Any) -> float:
    """Sum the first price-like field on each selected item dict."""
    total = 0.0
    for it in items or []:
        if not isinstance(it, dict):
            continue
        for k in _PRICE_KEYS:
            if k in it:
                n = _to_number(it[k])
                if n:
                    total += n
                    break
    return total


def traveler_count(travelers: Any) -> int:
    """Headcount from a free-form travelers string ("2 adults, 1 child" → 3).

    Only counts numbers that precede a traveler word so trailing ages
    ("(ages 5)") don't inflate the total. Falls back to 1.
    """
    if isinstance(travelers, (int, float)) and not isinstance(travelers, bool):
        return int(travelers) or 1
    matches = _TRAVELER_RE.findall(str(travelers or ""))
    count = sum(int(m[0]) for m in matches)
    return count or 1


def build_budget(trip: dict[str, Any] | None) -> dict[str, Any] | None:
    """Live budget meter view-model: spend, per-traveler split, remaining-vs-target.

    Pure aggregation over the active trip — no network. Returns ``None`` when
    there's nothing to show (no spend recorded and no target set), so the
    frontend can hide the meter entirely.

    ``spent`` prefers the agent-maintained ``total_cost`` (authoritative) and
    falls back to summing per-item prices. ``target`` comes from the optional
    ``budget`` field the agent sets when the user states a budget for the trip.
    """
    if not trip:
        return None

    symbol = currency_symbol(trip)
    breakdown = {
        "flights": round(_sum_item_prices(trip.get("selected_flights")), 2),
        "hotels": round(_sum_item_prices(trip.get("selected_hotels")), 2),
        "activities": round(_sum_item_prices(trip.get("selected_activities")), 2),
    }
    from_items = sum(breakdown.values())
    total_cost = _to_number(trip.get("total_cost"))
    spent = round(total_cost if total_cost else from_items, 2)
    target = _to_number(trip.get("budget"))

    if spent <= 0 and target <= 0:
        return None

    heads = traveler_count(trip.get("travelers"))
    per_traveler = round(spent / heads, 2) if heads else spent

    out: dict[str, Any] = {
        "currency": symbol,
        "spent": spent,
        "spent_display": fmt_money(spent, symbol),
        "travelers": heads,
        "per_traveler": per_traveler,
        "per_traveler_display": fmt_money(per_traveler, symbol),
        "breakdown": {k: v for k, v in breakdown.items() if v > 0},
        "target": None,
        "target_display": "",
        "remaining": None,
        "remaining_display": "",
        "pct_used": None,
        "over_budget": False,
    }

    if target > 0:
        remaining = round(target - spent, 2)
        out.update(
            {
                "target": round(target, 2),
                "target_display": fmt_money(target, symbol),
                "remaining": remaining,
                "remaining_display": fmt_money(abs(remaining), symbol),
                "pct_used": int(round(min(spent / target, 9.99) * 100)),
                "over_budget": spent > target,
            }
        )
    return out


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

    destination = str(trip.get("destination") or "").strip()
    if destination:
        for name in places_cache.top_places(destination, "hotel", n=_FALLBACK_HOTELS):
            _add("hotel", name)
        for name in places_cache.top_places(destination, "attraction", n=_FALLBACK_ATTRACTIONS):
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


# ---------------------------------------------------------------------------
# view-model assembly (may hit Places for photos/reviews)
# ---------------------------------------------------------------------------


def _build_overview(trip: dict[str, Any]) -> dict[str, Any]:
    counts = {
        "flights": len(trip.get("selected_flights") or []),
        "hotels": len(trip.get("selected_hotels") or []),
        "activities": len(trip.get("selected_activities") or []),
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
    }


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
    items = [
        _build_item(ref, destination, selected_names, itinerary_names) for ref in refs
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
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, name: str) -> None:
        key = (kind, (name or "").strip().lower())
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
        for s in stops:
            if isinstance(s, dict):
                name = str(s.get("name") or "").strip()
                kind = str(s.get("kind") or "").strip().lower()
            else:
                name = str(s or "").strip()
                kind = ""
            if not name:
                continue
            if kind not in {"hotel", "attraction"}:
                kind = _infer_kind_from_name(name)
            _add(kind, name)
            explicit_day_by_name.setdefault(name.lower(), day_num)

    # 2) User selected places (ensure presence even if stops list is absent).
    for h in trip.get("selected_hotels") or []:
        if isinstance(h, dict) and h.get("name"):
            _add("hotel", str(h["name"]))
    for a in trip.get("selected_activities") or []:
        if isinstance(a, dict) and a.get("name"):
            _add("attraction", str(a["name"]))

    # 3) Destination suggestions to fill context around the chosen items.
    if destination:
        for name in places_cache.top_places(destination, "hotel", n=_FALLBACK_HOTELS):
            _add("hotel", name)
        for name in places_cache.top_places(
            destination, "attraction", n=_MAX_OVERVIEW_ATTRACTIONS
        ):
            _add("attraction", name)

    places_cache.prefetch([n for _, n in refs], destination, max_photos=1)

    pins: list[dict[str, Any]] = []
    for i, (kind, name) in enumerate(refs):
        info = places_cache.get_summary(name, destination) or {}
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
                "name": info.get("name") or name,
                "kind": kind,
                "selected": is_sel,
                "day": explicit_day_by_name.get(name.strip().lower())
                or _day_for_place(name, itinerary),
                "lat": lat,
                "lng": lng,
                "rating": info.get("rating"),
                "address": info.get("address") or "",
                "photo": photos[0] if photos else None,
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
    info = places_cache.get_summary(f"{destination} International Airport", destination)
    if not info or info.get("lat") is None or info.get("lng") is None:
        return None
    return {
        "id": "airport",
        "name": info.get("name") or f"{destination} Airport",
        "kind": "airport",
        "lat": info["lat"],
        "lng": info["lng"],
    }


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between two (lat, lng) points."""
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def _route_stats_for_day(
    pin_ids: list[str], pin_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Estimate day route metrics from ordered pins.

    We avoid billed routing calls in this view-model. Distances are straight-
    line totals along the day path; durations are coarse estimates by likely
    local transfer mode.
    """
    coords: list[tuple[float, float]] = []
    for pid in pin_ids:
        p = pin_by_id.get(pid)
        if not p:
            continue
        lat, lng = p.get("lat"), p.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            coords.append((float(lat), float(lng)))

    if len(coords) < 2:
        return {
            "distance_km": 0.0,
            "duration_min": 0,
            "mode": "walk",
            "distance_display": "0.0 km",
            "duration_display": "0 min",
        }

    distance = 0.0
    for i in range(1, len(coords)):
        distance += _haversine_km(coords[i - 1], coords[i])

    if distance <= 3:
        mode, speed = "walk", 4.5
    elif distance <= 20:
        mode, speed = "local transit", 18.0
    else:
        mode, speed = "car transfer", 35.0

    duration_min = int(round((distance / speed) * 60)) if speed > 0 else 0
    distance_1 = round(distance, 1)
    return {
        "distance_km": distance_1,
        "duration_min": duration_min,
        "mode": mode,
        "distance_display": f"{distance_1:.1f} km",
        "duration_display": f"{duration_min} min",
    }


def _route_stats_for_day_coords(coords: list[tuple[float, float]]) -> dict[str, Any]:
    """Estimate day route metrics from an ordered list of (lat, lng) tuples.

    Same logic as _route_stats_for_day, but takes pre-computed coordinates
    instead of pin_ids. Used by build_itinerary to calculate per-day routes.
    """
    if len(coords) < 2:
        return {
            "distance_km": 0.0,
            "duration_min": 0,
            "mode": "walk",
            "distance_display": "0.0 km",
            "duration_display": "0 min",
        }

    distance = 0.0
    for i in range(1, len(coords)):
        distance += _haversine_km(coords[i - 1], coords[i])

    if distance <= 3:
        mode, speed = "walk", 4.5
    elif distance <= 20:
        mode, speed = "local transit", 18.0
    else:
        mode, speed = "car transfer", 35.0

    duration_min = int(round((distance / speed) * 60)) if speed > 0 else 0
    distance_1 = round(distance, 1)
    return {
        "distance_km": distance_1,
        "duration_min": duration_min,
        "mode": mode,
        "distance_display": f"{distance_1:.1f} km",
        "duration_display": f"{duration_min} min",
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
            "unscheduled_pin_ids": [],
            "airport": None,
            "empty_message": (
                "Start planning a trip and your hotels, attractions and daily "
                "routes will appear pinned on the map here."
            ),
        }

    pins = _map_pins(trip, destination)
    airport = _airport_pin(destination)

    # Group pins by day, preserving insertion order within each day.
    by_day: dict[int, list[str]] = {}
    unscheduled: list[str] = []
    for p in pins:
        if p["day"]:
            by_day.setdefault(p["day"], []).append(p["id"])
        else:
            unscheduled.append(p["id"])

    pin_by_id = {p["id"]: p for p in pins}
    days = []
    for d in sorted(by_day):
        ids = by_day[d]
        days.append(
            {
                "day": d,
                "label": f"Day {d}",
                "color": _day_color(d),
                "pin_ids": ids,
                "route": _route_stats_for_day(ids, pin_by_id),
            }
        )

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

    return {
        "enabled": key_configured,
        "destination": destination,
        "center": center,
        "pins": pins,
        "days": days,
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
_STOP_KINDS = {"hotel", "attraction", "flight", "meal", "transport", "other"}
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
        kind = str(raw.get("kind") or "").strip().lower()
        if kind not in _STOP_KINDS:
            kind = _infer_stop_kind(name, hotels, activities)
        dur = raw.get("duration_min")
        return {
            "name": name,
            "kind": kind,
            "time": str(raw.get("time") or "").strip(),
            "duration_min": dur if isinstance(dur, (int, float)) else None,
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


def _reachability_hint(stops: list[dict[str, Any]], route: dict[str, Any]) -> str:
    names = [str(s.get("name") or "").strip() for s in stops if str(s.get("name") or "").strip()]
    if len(names) < 2:
        return ""

    first = names[0]
    second = names[1]
    mode = str(route.get("mode") or "").strip().lower()
    if mode == "walk":
        return f"Start at {first}, then walk to {second}; most stops are in a compact area."
    if mode == "local transit":
        return (
            f"Start from {first}, take a short cab to {second}, and use metro/local transit "
            "for the remaining hops."
        )
    return f"Hire a cab from {first} to {second}, then continue the day circuit by taxi."


def _google_travel_mode(route_mode: str) -> str:
    mode = str(route_mode or "").strip().lower()
    if mode == "walk":
        return "walking"
    if mode == "local transit":
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
        info = places_cache.get_summary(name, destination) or {}
    except Exception:  # noqa: BLE001 — never let geocoding break the itinerary
        return None
    lat, lng = info.get("lat"), info.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return (float(lat), float(lng))

    # Retry without parenthetical qualifiers ("Place (Area)") which often
    # reduce match quality in text search.
    plain = re.sub(r"\s*\([^)]*\)", "", str(name or "")).strip()
    if plain and plain.lower() != str(name or "").strip().lower():
        try:
            info2 = places_cache.get_summary(plain, destination) or {}
        except Exception:  # noqa: BLE001
            return None
        lat2, lng2 = info2.get("lat"), info2.get("lng")
        if isinstance(lat2, (int, float)) and isinstance(lng2, (int, float)):
            return (float(lat2), float(lng2))
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
        
        if i == 1 and hotels:
            for hname in hotels:
                summary = places_cache.get_summary(hname, destination) or {}
                opening, concern = _opening_hint(summary, "")
                stops.append({
                    "name": hname, "kind": "hotel", "time": "", "duration_min": None,
                    "note": "Your base", "booked": False, "selected": True, "color": color,
                    "opening_hours": opening,
                    "cost_display": _cost_hint("hotel", summary, 0.0, symbol),
                    "insight": _insight_hint(hname, "hotel", summary),
                    "concern": concern,
                })
                # Add hotel coords to day route.
                c = coords.get(hname) or _place_coords(hname, destination)
                if c:
                    day_coords.append(c)
        
        for name in chunk:
            summary = places_cache.get_summary(name, destination) or {}
            opening, concern = _opening_hint(summary, "")
            stops.append({
                "name": name, "kind": "attraction", "time": "", "duration_min": None,
                "note": "", "booked": False, "selected": True, "color": color,
                "opening_hours": opening,
                "cost_display": _cost_hint("attraction", summary, 0.0, symbol),
                "insight": _insight_hint(name, "attraction", summary),
                "concern": concern,
            })
            # Add attraction coords to day route.
            c = coords.get(name)
            if c:
                day_coords.append(c)
        
        if not stops:
            continue
        
        primary = chunk[0] if chunk else (anchor or f"Day {i}")
        route = _route_stats_for_day_coords(day_coords)
        
        days.append({
            "day": i,
            "date": "",
            "title": f"Day {i} · {primary}" if len(chunks) > 1 else primary,
            "summary": "Suggested first-draft plan grouped by area — ask the "
            "planner to fine-tune times, meals, and pacing.",
            "color": color,
            "stops": stops,
            "route": route,
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
    activities = _selected_names(trip, "attraction")
    destination = str((trip or {}).get("destination") or "")
    symbol = currency_symbol(trip)
    selected_prices = _selected_price_map(trip)
    itin = trip.get("day_wise_itinerary") or []

    # Pre-load all place coords so we can calculate route stats per day.
    # Use EVERY itinerary stop name, not just selected buckets, so added meals,
    # markets, and non-selected places still contribute to route metrics.
    place_coords_map: dict[str, tuple[float, float]] = {}
    stop_names: set[str] = set(list(hotels) + list(activities))
    for entry in itin:
        if not isinstance(entry, dict):
            continue
        for raw in entry.get("stops") or []:
            if isinstance(raw, dict):
                name = str(raw.get("name") or "").strip()
            else:
                name = str(raw or "").strip()
            if name:
                stop_names.add(name)

    for name in stop_names:
        coords = _place_coords(name, destination)
        if coords:
            place_coords_map[name.strip().lower()] = coords

    days: list[dict[str, Any]] = []
    total_stops = 0
    total_booked = 0
    for idx, entry in enumerate(itin):
        if not isinstance(entry, dict):
            entry = {"plan": str(entry)}
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        stops = []
        day_coords: list[tuple[float, float]] = []
        for raw in entry.get("stops") or []:
            s = _normalize_stop(raw, hotels, activities)
            if s:
                summary = places_cache.get_summary(s["name"], destination) or {}
                opening, concern = _opening_hint(summary, str(entry.get("date") or ""))
                s["duration_min"] = _duration_hint(s["kind"], s.get("duration_min"))
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
                if not s.get("insight"):
                    s["insight"] = _insight_hint(s["name"], s["kind"], summary)
                s["color"] = _day_color(day_num)
                stops.append(s)
                # Accumulate coords for route stats.
                coords = place_coords_map.get(str(s["name"] or "").strip().lower())
                if coords:
                    day_coords.append(coords)
                total_stops += 1
                if s["booked"]:
                    total_booked += 1
        
        # Calculate route stats for the day.
        route = _route_stats_for_day_coords(day_coords)
        
        days.append(
            {
                "day": day_num,
                "date": str(entry.get("date") or "").strip(),
                "title": str(entry.get("title") or "").strip() or f"Day {day_num}",
                "summary": str(entry.get("summary") or entry.get("plan") or "").strip(),
                "color": _day_color(day_num),
                "stops": stops,
                "route": route,
                "reachability": _reachability_hint(stops, route),
                "google_maps_url": _google_maps_day_url(
                    destination, stops, route.get("mode", "")
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

