"""Deterministic whole-corpus probes for business-logic defects.

Each probe is pure over one saved plan and returns human-readable hits. They
measure patterns first seen by whole-itinerary judging, so prevalence can be
reported for the entire corpus rather than for a judged sample. They are
candidates for promotion into the audit rule registry, not rules yet.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from tripplanner.tools import day_order, trip_validation

_PLACEHOLDER = re.compile(
    r"\b(?:tbd|tbc|to be decided)\b"
    r"|^(?:hotel|local restaurant|restaurant|lunch|dinner|breakfast|brunch)"
    r"(?:\s+(?:in|at|near)\b.*|\s*\(.*\))?\s*$",
    re.IGNORECASE,
)
_SYNTHETIC_CARRIERS = frozenset({"duffel airways", "nuitée air", "nuitee air"})
_MOVE_KINDS = frozenset({"transport", "flight", "train", "drive", "transfer"})


def _minutes(value: Any) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def _days(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [day for day in plan.get("day_wise_itinerary") or [] if isinstance(day, dict)]


def _stops(day: dict[str, Any]) -> list[dict[str, Any]]:
    return [stop for stop in day.get("stops") or [] if isinstance(stop, dict)]


def _is_move(stop: dict[str, Any]) -> bool:
    name = str(stop.get("name") or "").lower()
    return str(stop.get("kind") or "").lower() in _MOVE_KINDS or bool(
        re.match(r"(?:drive|train|flight|transfer|shinkansen|ferry|bus)\b", name)
    )


def out_of_order(plan: dict[str, Any]) -> list[str]:
    """Shared with the save-time repair in ``tools.day_order`` so both agree."""
    return day_order.out_of_order(plan)


def stay_after_departure(plan: dict[str, Any]) -> list[str]:
    """Shared with the save-time repair in ``tools.day_order`` so both agree."""
    return day_order.misplaced_stays(plan)


def unused_nights(plan: dict[str, Any]) -> list[str]:
    """Shared with the save-time repair in ``tools.day_order`` so both agree."""
    return day_order.unused_nights(plan)


def placeholder_stops(plan: dict[str, Any]) -> list[str]:
    return [
        f"Day {day.get('day')}: {stop.get('name')}"
        for day in _days(plan)
        for stop in _stops(day)
        if _PLACEHOLDER.search(str(stop.get("name") or "").strip())
    ]


def synthetic_fares(plan: dict[str, Any]) -> list[str]:
    return [
        f"{flight.get('airline')} {flight.get('price')} {flight.get('currency')}"
        for flight in plan.get("selected_flights") or []
        if isinstance(flight, dict)
        and str(flight.get("airline") or "").strip().casefold() in _SYNTHETIC_CARRIERS
    ]


def implausible_road_speed(plan: dict[str, Any]) -> list[str]:
    """Shared with the completion gate so the probe and the planner agree."""
    return trip_validation.implausible_drive_warnings(plan)


def summary_drift(plan: dict[str, Any]) -> list[str]:
    """Shared with the completion gate so the probe and the planner agree."""
    return trip_validation.summary_drift_warnings(plan)


def unpriced(plan: dict[str, Any]) -> list[str]:
    try:
        total = float(plan.get("total_cost") or 0)
    except (TypeError, ValueError):
        total = 0.0
    return [] if total > 0 else ["total_cost is 0"]


PROBES: dict[str, tuple[str, Callable[[dict[str, Any]], list[str]]]] = {
    "placeholder_stops": ("Placeholder stops presented as planned", placeholder_stops),
    "unpriced": ("Trip has no priced total", unpriced),
    "out_of_order": ("Stops listed out of time order", out_of_order),
    "stay_after_departure": ("Hotel stop after the day's departing journey", stay_after_departure),
    "summary_drift": ("Day summary names another day's stop", summary_drift),
    "unused_nights": ("Stay checks out after the traveller has left", unused_nights),
    "implausible_road_speed": (
        "Long drive averaging over 75 km/h door to door",
        implausible_road_speed,
    ),
    "synthetic_fares": ("Provider test-mode fare saved as a real fare", synthetic_fares),
}


def run(plans: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply every probe to every plan; return prevalence with examples."""
    results = []
    for key, (title, probe) in PROBES.items():
        affected = {slug: probe(plan) for slug, plan in plans.items()}
        affected = {slug: hits for slug, hits in affected.items() if hits}
        examples = [f"{slug}: {hits[0]}" for slug, hits in sorted(affected.items())[:3]]
        results.append(
            {
                "key": key,
                "title": title,
                "trips": len(affected),
                "evaluated": len(plans),
                "hits": sum(len(hits) for hits in affected.values()),
                "examples": examples,
            }
        )
    return results


def _tokens(text: str) -> set[str]:
    import unicodedata

    spaced = re.sub(r"[^\w\s]", " ", text)
    folded = unicodedata.normalize("NFKD", spaced).encode("ascii", "ignore").decode().lower()
    return {token for token in re.findall(r"[a-z0-9]+", folded) if len(token) > 2}


def place_identity(places: dict[str, Any]) -> dict[str, Any]:
    """Cached place lookups whose resolved name shares no word with the stop name.

    Keys are ``name|city`` as written by the places cache. A resolution that
    shares no word with what was asked is a likely wrong pin (a tour agency for
    "India Gate", a restaurant for "Harajuku") and was a paid lookup either way.
    """
    resolved = {
        key: value for key, value in places.items() if isinstance(value, dict) and value.get("name")
    }
    mismatched = {
        key: str(value["name"])
        for key, value in resolved.items()
        if not _tokens(str(key).split("|", 1)[0]) & _tokens(str(value["name"]))
    }
    top: dict[str, int] = {}
    for name in mismatched.values():
        top[name] = top.get(name, 0) + 1
    return {
        "resolved": len(resolved),
        "mismatched": len(mismatched),
        "examples": [
            f"{key.split('|')[0]} ({key.split('|', 1)[1] or 'no city'}) -> {name}"
            for key, name in sorted(mismatched.items())
            if len(_tokens(key.split("|")[0])) >= 2
        ][:8],
        "most_common": sorted(top.items(), key=lambda item: -item[1])[:5],
    }
