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
from urllib.parse import quote

from multiagent.tools import user_preferences
from multiagent.web import places_cache

_MAX_GALLERY_ITEMS = 6
_MAX_PHOTOS_PER_ITEM = 3
_MAX_REVIEWS_PER_ITEM = 2
_FALLBACK_HOTELS = 2
_FALLBACK_ATTRACTIONS = 4

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

    Focused → just that one item. Otherwise the user's selected hotels and
    activities come first, followed by the destination's top hotels &
    attractions that aren't already selected — so adding something to the trip
    never hides the rest of the places you can still browse.
    """
    if focus and focus.get("name"):
        return [{"kind": focus.get("kind", "place"), "name": focus["name"]}]
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
    }


def _build_item(
    ref: dict[str, str], destination: str, selected_names: dict[str, set[str]]
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
    return {
        "kind": kind,
        "name": info.get("name") or name,
        "selected": name.strip().lower() in selected_names.get(kind, set()),
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
    places_cache.prefetch(
        [r["name"] for r in refs], destination, max_photos=_MAX_PHOTOS_PER_ITEM
    )
    items = [_build_item(ref, destination, selected_names) for ref in refs]

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
        from multiagent.config import get_settings

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
        from multiagent.config import get_settings

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

    # (kind, name) in display order: user picks first, then suggestions.
    refs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, name: str) -> None:
        key = (kind, (name or "").strip().lower())
        if name and key not in seen:
            seen.add(key)
            refs.append((kind, name))

    for h in trip.get("selected_hotels") or []:
        if isinstance(h, dict) and h.get("name"):
            _add("hotel", str(h["name"]))
    for a in trip.get("selected_activities") or []:
        if isinstance(a, dict) and a.get("name"):
            _add("attraction", str(a["name"]))
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
        is_sel = name.strip().lower() in selected.get(kind, set())
        pins.append(
            {
                "id": f"p{i}",
                "name": info.get("name") or name,
                "kind": kind,
                "selected": is_sel,
                "day": _day_for_place(name, itinerary),
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

    days = [
        {
            "day": d,
            "label": f"Day {d}",
            "color": _day_color(d),
            "pin_ids": by_day[d],
        }
        for d in sorted(by_day)
    ]

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
        }
    return None


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


def _itinerary_from_selections(trip: dict[str, Any] | None) -> dict[str, Any]:
    """Fallback itinerary when the agent never wrote a structured
    ``day_wise_itinerary``: synthesize a single "Your picks so far" day from the
    selected hotels + activities so the panel is never blank while a trip is
    being assembled. Each item is a clickable, selected stop. Pure / no network.
    """
    hotels = _ordered_selected(trip, "selected_hotels")
    activities = _ordered_selected(trip, "selected_activities")
    if not hotels and not activities:
        return {
            "has_itinerary": False,
            "destination": str((trip or {}).get("destination") or ""),
            "currency": currency_symbol(trip),
            "days": [],
            "stats": {"days": 0, "stops": 0, "booked": 0},
        }

    color = _day_color(1)
    stops: list[dict[str, Any]] = []
    for name in hotels:
        stops.append({
            "name": name, "kind": "hotel", "time": "", "duration_min": None,
            "note": "", "booked": False, "selected": True, "color": color,
        })
    for name in activities:
        stops.append({
            "name": name, "kind": "attraction", "time": "", "duration_min": None,
            "note": "", "booked": False, "selected": True, "color": color,
        })
    day = {
        "day": 1,
        "date": "",
        "title": "Your picks so far",
        "summary": "Places you've selected. Ask the planner to lay out a "
        "day-by-day itinerary to organize these into a schedule.",
        "color": color,
        "stops": stops,
    }
    return {
        "has_itinerary": True,
        "destination": str((trip or {}).get("destination") or ""),
        "currency": currency_symbol(trip),
        "days": [day],
        "stats": {"days": 1, "stops": len(stops), "booked": 0},
    }


def build_itinerary(trip: dict[str, Any] | None) -> dict[str, Any]:
    """Structured day-by-day itinerary view-model (frontend-agnostic).

    Each day carries a title, prose summary, day color, and an ordered list of
    structured stops. Every stop is cross-referenced against the trip's
    selections (``selected``) and carries its own ``booked`` flag so the UI can
    render booked checkmarks and make each stop clickable (to focus its photos
    or its map pin). When the agent never wrote a structured itinerary, falls
    back to a single day synthesized from the selections. Pure / no network.
    """
    if not trip or not (trip.get("day_wise_itinerary") or []):
        return _itinerary_from_selections(trip)

    hotels = _selected_names(trip, "hotel")
    activities = _selected_names(trip, "attraction")
    itin = trip.get("day_wise_itinerary") or []

    days: list[dict[str, Any]] = []
    total_stops = 0
    total_booked = 0
    for idx, entry in enumerate(itin):
        if not isinstance(entry, dict):
            entry = {"plan": str(entry)}
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        stops = []
        for raw in entry.get("stops") or []:
            s = _normalize_stop(raw, hotels, activities)
            if s:
                s["color"] = _day_color(day_num)
                stops.append(s)
                total_stops += 1
                if s["booked"]:
                    total_booked += 1
        days.append(
            {
                "day": day_num,
                "date": str(entry.get("date") or "").strip(),
                "title": str(entry.get("title") or "").strip() or f"Day {day_num}",
                "summary": str(entry.get("summary") or entry.get("plan") or "").strip(),
                "color": _day_color(day_num),
                "stops": stops,
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
        from multiagent.tools import web_search

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
