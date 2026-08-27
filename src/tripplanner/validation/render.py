"""Checks over what the trip actually renders, not just what it stores.

Every defect reported this week was legal at plan level and wrong on screen: a
plan may hold two airports and a stay without contradicting itself, while the
map it produces asks the traveller to drive between continents. These checks
therefore build the real view-models and read them the way a person would.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from tripplanner.validation.corpus import CorpusRecord
from tripplanner.validation.findings import Finding, symptom_of
from tripplanner.web.schedule import MAX_GROUND_LEG_KM

#: No single leg of a day plausibly takes longer than this.
MAX_LEG_MINUTES = 16 * 60
_GROUND_MODES = frozenset({"Walk", "Taxi", "Drive", "Bus", "Metro", "Cab", "Car"})

RULE_CRASH = "R0"
RULE_GROUND_LEG = "R1"
RULE_LEG_DURATION = "R2"
RULE_EMPTY_LEG = "R3"
RULE_UNMAPPED = "R4"

RENDER_RULES: tuple[tuple[str, str], ...] = (
    (RULE_CRASH, "A stored trip must be renderable at all."),
    (RULE_GROUND_LEG, "A leg drawn as ground travel must be a distance you could drive."),
    (RULE_LEG_DURATION, "No single leg of a day may take longer than a day."),
    (RULE_EMPTY_LEG, "A flight or train between two points in the same place is not a journey."),
    (RULE_UNMAPPED, "An itinerary stop must reach the map or say why it did not."),
)


def _lookup(places: dict[str, Any]):
    normalized_places: dict[str, Any] = {}
    by_name: dict[str, list[tuple[str, Any]]] = {}
    for key, entry in places.items():
        name, _, city = str(key).partition("|")
        wanted = name.strip().lower()
        cached_city = city.strip().lower()
        normalized_places[f"{wanted}|{cached_city}"] = entry or {}
        by_name.setdefault(wanted, []).append((cached_city, entry or {}))

    def destination_matches(city: str, cached_city: str, entry: Any) -> bool:
        wanted = city.strip().lower()
        if not wanted:
            return True
        locations = [cached_city, str((entry or {}).get("address") or "").strip().lower()]
        return any(
            location
            and (
                wanted == location
                or wanted in {part.strip() for part in location.split(",")}
                or (cached_city and (cached_city in wanted or wanted in cached_city))
            )
            for location in locations
        )

    def get_details(name: str, city: str = "", **_kwargs: Any) -> dict[str, Any] | None:
        wanted = str(name or "").strip().lower()
        destination = str(city or "").strip().lower()
        exact_key = f"{wanted}|{destination}"
        if exact_key in normalized_places:
            return dict(normalized_places[exact_key]) or None
        compatible = [
            entry
            for cached_city, entry in by_name.get(wanted, [])
            if destination_matches(destination, cached_city, entry)
        ]
        identities = {
            str(entry.get("place_id") or "").strip()
            or f"{entry.get('lat')}|{entry.get('lng')}"
            for entry in compatible
        }
        if len(identities) != 1:
            return None
        preferred = next(
            (
                entry
                for entry in compatible
                if str(entry.get("name") or "").strip().lower() == wanted
            ),
            compatible[0],
        )
        return dict(preferred) or None

    return get_details


@contextmanager
def render_facts(places: dict[str, Any]) -> Iterator[None]:
    """Build the view-models from stored place facts instead of a provider."""
    from tripplanner.web import places_cache, trip_view

    get_details = _lookup(places)
    saved = {
        "get_details": places_cache.get_details,
        "get_summary": places_cache.get_summary,
        "get_photos": places_cache.get_photos,
        "top_places": places_cache.top_places,
        "prefetch": places_cache.prefetch,
        "_maps_browser_key": trip_view._maps_browser_key,
    }
    places_cache.get_details = get_details
    places_cache.get_summary = get_details
    places_cache.get_photos = lambda *a, **k: []
    places_cache.top_places = lambda *a, **k: []
    places_cache.prefetch = lambda *a, **k: None
    trip_view._maps_browser_key = lambda: "audit"
    try:
        yield
    finally:
        places_cache.get_details = saved["get_details"]
        places_cache.get_summary = saved["get_summary"]
        places_cache.get_photos = saved["get_photos"]
        places_cache.top_places = saved["top_places"]
        places_cache.prefetch = saved["prefetch"]
        trip_view._maps_browser_key = saved["_maps_browser_key"]


def _leg_findings(
    record: CorpusRecord, view: dict[str, Any], names: list[str]
) -> list[Finding]:
    found: list[Finding] = []
    pins = {str(pin["id"]): pin for pin in view.get("pins") or []}

    def _name(pin_id: Any) -> str:
        return str((pins.get(str(pin_id)) or {}).get("name") or "somewhere")

    for day in view.get("days") or []:
        number = day.get("day")
        for leg in day.get("legs") or []:
            mode = str(leg.get("mode") or "")
            distance = float(leg.get("distance_km") or 0.0)
            minutes = int(leg.get("duration_min") or 0)
            start, end = _name(leg.get("from_pin_id")), _name(leg.get("to_pin_id"))
            if mode in _GROUND_MODES and distance > MAX_GROUND_LEG_KM:
                message = (
                    f"Day {number} draws {start} to {end} as {mode} over "
                    f"{distance:.0f} km."
                )
                found.append(
                    Finding(RULE_GROUND_LEG, symptom_of(message, names), message,
                            record.id, record.provenance, number)
                )
            if minutes > MAX_LEG_MINUTES:
                message = (
                    f"Day {number} spends {minutes // 60} hours going from {start} to {end}."
                )
                found.append(
                    Finding(RULE_LEG_DURATION, symptom_of(message, names), message,
                            record.id, record.provenance, number)
                )
            if leg.get("intercity") and distance <= 1.0 and mode not in _GROUND_MODES:
                message = (
                    f"Day {number} draws an inter-city {mode} from {start} to {end} "
                    "that covers no distance."
                )
                found.append(
                    Finding(RULE_EMPTY_LEG, symptom_of(message, names), message,
                            record.id, record.provenance, number)
                )
    return found


def _unmapped_findings(
    record: CorpusRecord, view: dict[str, Any], names: list[str]
) -> list[Finding]:
    located = {
        str(key).partition("|")[0]
        for key, entry in record.places.items()
        if isinstance(entry, dict)
        and entry.get("lat") is not None
        and entry.get("lng") is not None
    }
    found: list[Finding] = []
    for stop in view.get("unmapped_stops") or []:
        reason = str(stop.get("reason") or "")
        name = str(stop.get("name") or "")
        if reason == "not_a_place":
            continue
        # Missing or coordinate-less stored facts say nothing about whether the
        # app could map the place. Only speak when this audit can locate it.
        if reason == "no_location" and name.strip().lower() not in located:
            continue
        message = (
            f"{name or 'A stop'} on Day {stop.get('day')} never reached "
            f"the map ({reason or 'no reason given'})."
        )
        found.append(
            Finding(RULE_UNMAPPED, symptom_of(message, names), message, record.id,
                    record.provenance, stop.get("day"))
        )
    return found


def check_render(record: CorpusRecord) -> list[Finding]:
    """Build the itinerary and map this trip would show, then read them."""
    from tripplanner.validation.checks import plan_names
    from tripplanner.web import trip_view

    if not record.places:
        # Without place facts every leg is unmeasurable, and a check that cannot
        # measure must stay silent rather than report a clean render.
        return []
    names = plan_names(record.plan)
    with render_facts(record.places):
        try:
            view = trip_view.build_map_view(record.plan)
            trip_view.build_itinerary(record.plan)
        except Exception as error:  # noqa: BLE001 - a crash is the strongest finding
            message = f"Rendering the trip raised {type(error).__name__}: {error}"
            return [
                Finding(RULE_CRASH, symptom_of(message, names), message, record.id,
                        record.provenance)
            ]

    return [*_leg_findings(record, view, names), *_unmapped_findings(record, view, names)]
