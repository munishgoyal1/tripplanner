"""Transport-name parsing helpers for the trip-panel view-model.

Pure string logic (no network, no UI) for recognizing transfer stops and
deriving terminal references from free-form itinerary names. Split out of
``trip_view`` (tech-debt #7) as a leaf module so both the gallery and map-pin
builders can share it without an import cycle; ``trip_view`` re-exports these
names so existing callers and tests are unaffected.
"""

from __future__ import annotations

import re

_ROUTE_SEPARATOR_RE = re.compile(r"\s+(?:to|->|→)\s+|\s*(?:->|→)\s*", re.I)
_VIA_RE = re.compile(r"\s+via\s+", re.I)
_CONNECTION_SEPARATOR_RE = re.compile(r"\s*(?:,|&|\band\b|->|→)\s*", re.I)
_FLIGHT_WORD_RE = re.compile(r"\b(?:flight|fly|flying|flies|flown)\b", re.I)
_RAIL_WORD_RE = re.compile(r"\b(?:train|rail|shinkansen)\b", re.I)


def _strip_route_affixes(name: str) -> str:
    route = str(name or "").strip()
    route = re.sub(
        r"^(?:(?:drive|driving|road journey|road transfer|transfer|private car|"
        r"car(?: ride| transfer)?|taxi|flight|toy train|train|rail|shinkansen|bus)"
        r"(?::|\s+))+(?:from\s+)?",
        "",
        route,
        flags=re.I,
    )
    return re.sub(
        r"\s+(?:drive|driving|road journey|road transfer|by (?:private )?car|by road)$",
        "",
        route,
        flags=re.I,
    )


def _transport_route_waypoints(name: str) -> list[str]:
    """Every place the leg touches, in travel order.

    A connection is a place the traveller is actually in, so "Bengaluru to
    London via Doha" and "Bengaluru → Doha → London" both yield three stops.
    """
    route = _strip_route_affixes(name)
    if not route:
        return []
    main, *via_parts = _VIA_RE.split(route)
    legs = [part.strip() for part in _ROUTE_SEPARATOR_RE.split(main) if part.strip()]
    if len(legs) < 2:
        return []
    connections = [
        connection.strip()
        for part in via_parts
        for connection in _CONNECTION_SEPARATOR_RE.split(part)
        if connection.strip()
    ]
    return [legs[0], *connections, *legs[1:]]


def _transport_route_endpoints(name: str) -> tuple[str, str] | None:
    waypoints = _transport_route_waypoints(name)
    if len(waypoints) < 2:
        return None
    return waypoints[0], waypoints[-1]


def _named_terminal_ref(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    if "airport" in lowered:
        return ("airport", text)
    if "railway station" in lowered or "train station" in lowered:
        return ("station", text)
    if "bus stand" in lowered or "bus station" in lowered:
        return ("bus_station", text)
    return None


def _transport_terminal_refs(name: str, kind: str) -> list[tuple[str, str]]:
    text = str(name or "").strip()
    lowered = text.lower()
    if not text:
        return []
    named = _named_terminal_ref(text)
    if kind not in {"flight", "transport"}:
        return [named] if named else []

    endpoints = _transport_route_endpoints(text)
    if not endpoints:
        # A leg written as one terminal per stop ("… Airport, Delhi (DEL)") names a
        # real place, so the map must pin it rather than drop the stop.
        return [named] if named else []
    origin, destination = endpoints
    waypoints = _transport_route_waypoints(text)
    if _intercity_transfer_mode(text, kind) == "Flight":
        return [
            (
                "airport",
                waypoint if "airport" in waypoint.lower() else f"{waypoint} Airport",
            )
            for waypoint in waypoints
        ]
    if _RAIL_WORD_RE.search(lowered):
        return [("station", f"{waypoint} Railway Station") for waypoint in waypoints]
    if "bus" in lowered:
        return [("bus_station", f"{waypoint} Bus Stand") for waypoint in waypoints]
    if _intercity_transfer_mode(text, kind) == "Drive":
        return [("origin", origin)]
    return []


def _intercity_transfer_mode(name: str, kind: str) -> str | None:
    lowered = str(name or "").strip().lower()
    if kind == "flight":
        return "Flight"
    if kind != "transport":
        return None
    # A flight the plan filed as a generic transfer is still a flight; reading it
    # as a local hop is what turns an ocean crossing into a drive.
    if _FLIGHT_WORD_RE.search(lowered) and ("to" in lowered.split() or "→" in lowered):
        return "Flight"
    if _RAIL_WORD_RE.search(lowered):
        return "Train"
    if "bus" in lowered:
        return "Bus"
    drive_terms = r"drive|driving|car|road (?:journey|transfer)"
    directional_drive = bool(
        re.search(rf"\b(?:{drive_terms})\b", lowered)
        and (re.search(r"\bto\b|->|→", lowered) or lowered.startswith(("drive ", "driving ")))
    )
    if directional_drive:
        return "Drive"
    return None


def _normalized_stop_kind(name: str, kind: str, mode: str = "") -> str:
    normalized_kind = str(kind or "").strip().lower()
    normalized_mode = str(mode or "").strip().lower()
    if normalized_kind == "flight" or normalized_mode == "flight":
        return "flight"
    if normalized_mode in {"car", "drive", "train", "rail", "bus"} or (
        _intercity_transfer_mode(name, "transport")
    ):
        return "transport"
    return normalized_kind


def _canonical_transport_name(name: str, mode: str = "") -> str:
    text = str(name or "").strip()
    normalized_mode = str(mode or "").strip().lower()
    prefix = {
        "car": "Drive",
        "drive": "Drive",
        "train": "Train",
        "rail": "Train",
        "bus": "Bus",
    }.get(normalized_mode)
    if not prefix or _intercity_transfer_mode(text, "transport"):
        return text
    return f"{prefix}: {text}"
