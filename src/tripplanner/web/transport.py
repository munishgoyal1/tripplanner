"""Transport-name parsing helpers for the trip-panel view-model.

Pure string logic (no network, no UI) for recognizing transfer stops and
deriving terminal references from free-form itinerary names. Split out of
``trip_view`` (tech-debt #7) as a leaf module so both the gallery and map-pin
builders can share it without an import cycle; ``trip_view`` re-exports these
names so existing callers and tests are unaffected.
"""

from __future__ import annotations

import re


def _transport_route_endpoints(name: str) -> tuple[str, str] | None:
    route = str(name or "").strip()
    route = re.sub(
        r"^(?:(?:drive|driving|road journey|road transfer|transfer|private car|"
        r"car(?: ride| transfer)?|taxi|flight|toy train|train|rail|bus)(?::|\s+))+(?:from\s+)?",
        "",
        route,
        flags=re.I,
    )
    route = re.sub(
        r"\s+(?:drive|driving|road journey|road transfer|by (?:private )?car|by road)$",
        "",
        route,
        flags=re.I,
    )
    endpoints = re.split(r"\s+(?:to|->|→)\s+", route, maxsplit=1, flags=re.I)
    if len(endpoints) != 2:
        return None
    origin, destination = (endpoint.strip() for endpoint in endpoints)
    if not origin or not destination:
        return None
    return origin, destination


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
    if kind == "flight":
        origin = origin if "airport" in origin.lower() else f"{origin} Airport"
        destination = (
            destination if "airport" in destination.lower() else f"{destination} Airport"
        )
        return [("airport", origin), ("airport", destination)]
    if "train" in lowered or "rail" in lowered:
        return [
            ("station", f"{origin} Railway Station"),
            ("station", f"{destination} Railway Station"),
        ]
    if "bus" in lowered:
        return [("bus_station", f"{origin} Bus Stand"), ("bus_station", f"{destination} Bus Stand")]
    if _intercity_transfer_mode(text, kind) == "Drive":
        return [("origin", origin)]
    return []


def _intercity_transfer_mode(name: str, kind: str) -> str | None:
    lowered = str(name or "").strip().lower()
    if kind == "flight":
        return "Flight"
    if kind != "transport":
        return None
    if "train" in lowered or "rail" in lowered:
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
