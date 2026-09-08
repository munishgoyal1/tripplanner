"""Gallery item selection and itinerary occurrence indexing for the trip panel.

Pure, network-light helpers that decide which places populate the browse
gallery and where each place / transport terminal appears across the
day-by-day itinerary. Split out of ``trip_view`` (tech-debt #7) as a leaf
module; ``trip_view`` re-exports these names so callers and tests are
unaffected. Only external dependency is ``places_cache`` (for fallback top
places) and the ``transport`` leaf for terminal references.
"""

from __future__ import annotations

from typing import Any

from tripplanner.web import places_cache
from tripplanner.web.transport import _transport_terminal_refs

_MAX_GALLERY_ITEMS = 10
_FALLBACK_HOTELS = 2
_FALLBACK_ATTRACTIONS = 8


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
