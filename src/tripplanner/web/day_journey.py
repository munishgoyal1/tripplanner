"""Transfer-day journey model for the Map (UX Lab #14, Option A).

An ordinary sightseeing day is a **closed circuit**: it leaves the stay, visits
local places, and returns. A transfer day is an **open journey**: origin-local
travel, one inter-city movement, then destination-local travel. The Map has to
render that journey completely, in itinerary order, with the terminals it
actually passes through.

This module owns that single idea. It walks a day's itinerary stops once and
produces a :class:`DayJourney` — the ordered path, the inter-city edges, and
the pins the day contributes to the map — so the view-model builder never has
to re-derive transfer semantics from loose state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tripplanner.web.map_pins import _route_circuit_id
from tripplanner.web.transport import (
    _canonical_transport_name,
    _intercity_transfer_mode,
    _normalized_stop_kind,
    _transport_terminal_refs,
)

TERMINAL_KINDS = frozenset({"airport", "station", "bus_station"})

# A ground transfer keeps flowing through stops made on the way; they are not
# the arrival that closes the inter-city leg.
_ENROUTE_KINDS = frozenset({"attraction", "meal", "restaurant"})
_GROUND_MODES = frozenset({"Drive", "Bus"})

Edge = tuple[str, str]

#: ``(name, kind) -> pin`` lookup against the trip's resolved map pins.
PinResolver = Callable[[Any, str], dict[str, Any] | None]


@dataclass
class DayJourney:
    """One day of the trip, expressed as a path the Map can draw."""

    day: int
    map_pin_ids: list[str] = field(default_factory=list)
    route_ids: list[str] = field(default_factory=list)
    intercity_edges: dict[Edge, str] = field(default_factory=dict)
    circuit_edges: dict[Edge, str] = field(default_factory=dict)
    transfer_mode: str | None = None

    @property
    def is_transfer(self) -> bool:
        return self.transfer_mode is not None


@dataclass
class _OpenTransfer:
    """An inter-city leg whose arrival has not been placed on the path yet."""

    mode: str
    circuit_id: str
    #: A known arrival terminal that must follow any en-route waypoints.
    arrival_id: str | None = None


class _JourneyWalk:
    """Single pass over one day's stops."""

    def __init__(self, day: int, resolve_pin: PinResolver) -> None:
        self.journey = DayJourney(day=day)
        self.saved_metrics: dict[str, dict[str, float]] = {}
        self._resolve_pin = resolve_pin
        self._open: _OpenTransfer | None = None

    # -- path primitives -------------------------------------------------

    def _place(self, pin_id: str) -> None:
        if pin_id not in self.journey.map_pin_ids:
            self.journey.map_pin_ids.append(pin_id)
        self.journey.route_ids.append(pin_id)

    def _connect(self, to_id: str, transfer: _OpenTransfer) -> None:
        if not self.journey.route_ids:
            return
        edge = (self.journey.route_ids[-1], to_id)
        self.journey.intercity_edges[edge] = transfer.mode
        self.journey.circuit_edges[edge] = transfer.circuit_id

    def _close_pending_arrival(self) -> None:
        """Place a deferred arrival terminal once its en-route stops are on the path."""
        transfer = self._open
        if not transfer or not transfer.arrival_id or not self.journey.route_ids:
            return
        self._connect(transfer.arrival_id, transfer)
        self._place(transfer.arrival_id)
        self._open = None

    # -- stops -----------------------------------------------------------

    def visit(self, stop: Any, stop_index: int) -> None:
        """Add one itinerary stop to the day's path."""
        raw_name = stop.get("name") if isinstance(stop, dict) else stop
        kind = str(stop.get("kind") or "").strip().lower() if isinstance(stop, dict) else ""
        mode_name = str(stop.get("mode") or "") if isinstance(stop, dict) else ""
        name = _canonical_transport_name(str(raw_name or ""), mode_name)
        kind = _normalized_stop_kind(name, kind, mode_name)

        mode = _intercity_transfer_mode(name, kind)
        if mode:
            self._visit_transfer(stop, stop_index, name, kind, mode)
            return
        self._visit_place(name, kind)

    def _visit_transfer(self, stop: Any, stop_index: int, name: str, kind: str, mode: str) -> None:
        # A new transfer supersedes any leg still waiting for its arrival.
        self._close_pending_arrival()

        self.journey.transfer_mode = mode
        circuit_id = _route_circuit_id(self.journey.day, stop_index, mode)
        transfer = _OpenTransfer(mode=mode, circuit_id=circuit_id)
        metrics = _saved_metrics(stop)
        if metrics:
            self.saved_metrics[circuit_id] = metrics

        refs = _transport_terminal_refs(name, kind)
        terminal_ids = [
            str(pin["id"])
            for pin in (
                self._resolve_pin(terminal_name, terminal_kind)
                for terminal_kind, terminal_name in refs
            )
            if pin
        ]
        if len(terminal_ids) == len(refs) and len(terminal_ids) >= 2:
            self._place(terminal_ids[0])
            # A connection is a place the traveller actually passes through, so
            # each hop is drawn instead of one line that skips the stop.
            previous = terminal_ids[0]
            for terminal_id in terminal_ids[1:-1]:
                edge = (previous, terminal_id)
                self.journey.intercity_edges[edge] = mode
                self.journey.circuit_edges[edge] = circuit_id
                self._place(terminal_id)
                previous = terminal_id
            if mode == "Bus":
                # Bus arrivals come after the meal and viewpoint stops made en route.
                transfer.arrival_id = terminal_ids[-1]
                self._open = transfer
            else:
                edge = (previous, terminal_ids[-1])
                self.journey.intercity_edges[edge] = mode
                self.journey.circuit_edges[edge] = circuit_id
                self._place(terminal_ids[-1])
            return

        # Only one endpoint is mappable (a drive, or a half-geocoded flight):
        # start the path there and let the next real stop close the leg.
        if not self.journey.route_ids and refs:
            origin_pin = self._resolve_pin(refs[0][1], refs[0][0])
            if origin_pin:
                self._place(str(origin_pin["id"]))
        self._open = transfer

    def _visit_place(self, name: str, kind: str) -> None:
        if self._open and self._open.arrival_id and kind not in _ENROUTE_KINDS:
            self._close_pending_arrival()

        pin = self._resolve_pin(name, kind)
        if not pin:
            return
        pin_id = str(pin["id"])
        pin_kind = str(pin["kind"])

        transfer = self._open
        if transfer and self.journey.route_ids:
            if pin_kind not in TERMINAL_KINDS:
                self._connect(pin_id, transfer)
            # A ground transfer stays open through its waypoints until the stay.
            if transfer.mode not in _GROUND_MODES or pin_kind == "hotel":
                self._open = None
        self._place(pin_id)

    def finish(self) -> DayJourney:
        self._close_pending_arrival()
        return self.journey


def _saved_metrics(stop: Any) -> dict[str, float] | None:
    if not isinstance(stop, dict):
        return None
    metrics = {
        metric: float(stop[metric])
        for metric in ("distance_km", "duration_min")
        if isinstance(stop.get(metric), (int, float)) and stop[metric] > 0
    }
    return metrics or None


def plan_day_journeys(
    entries: Any,
    *,
    resolve_pin: PinResolver,
) -> tuple[dict[int, DayJourney], dict[str, dict[str, float]]]:
    """Build every day's journey, plus owner-saved transfer metrics by circuit."""
    journeys: dict[int, DayJourney] = {}
    saved_metrics: dict[str, dict[str, float]] = {}
    for idx, entry in enumerate(entries or []):
        if not isinstance(entry, dict) or not isinstance(entry.get("stops"), list):
            continue
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        walk = _JourneyWalk(day_num, resolve_pin)
        for stop_index, stop in enumerate(entry["stops"], start=1):
            walk.visit(stop, stop_index)
        journeys[day_num] = walk.finish()
        saved_metrics.update(walk.saved_metrics)
    return journeys, saved_metrics


def start_journey_from_stay(
    journey: DayJourney,
    stay_id: str,
    *,
    kind_of: Callable[[str], str],
    extra_stay_ids: list[str] | None = None,
) -> None:
    """Anchor a transfer day on the stay it actually departs from.

    The itinerary records a generic origin for the first leg of a trip; once the
    traveller already has a stay, that stay — not the city centroid — is where
    the day begins, so every edge that left the origin is rebound to it.
    """
    route_ids = journey.route_ids
    if route_ids and kind_of(route_ids[0]) == "origin":
        origin_id = route_ids.pop(0)
        _rebind_edges(journey.intercity_edges, origin_id, stay_id)
        _rebind_edges(journey.circuit_edges, origin_id, stay_id)

    journey.route_ids = [stay_id, *(pin_id for pin_id in route_ids if pin_id != stay_id)]
    if len(journey.route_ids) >= 2 and journey.transfer_mode:
        journey.intercity_edges.setdefault(
            (journey.route_ids[0], journey.route_ids[1]), journey.transfer_mode
        )
    for extra_id in extra_stay_ids or []:
        if extra_id not in journey.route_ids:
            journey.route_ids.append(extra_id)


def _rebind_edges(edges: dict[Edge, Any], from_id: str, to_id: str) -> None:
    replacements = {
        (to_id, end_id): value for (start_id, end_id), value in edges.items() if start_id == from_id
    }
    if not replacements:
        return
    for edge in [edge for edge in edges if edge[0] == from_id]:
        del edges[edge]
    edges.update(replacements)


def frame_pin_ids(
    route_ids: list[str],
    intercity_edges: dict[Edge, str],
    *,
    kind_of: Callable[[str], str],
) -> list[str]:
    """The part of the journey worth framing when the day is selected.

    A transfer day spans two cities, so fitting the whole path would zoom past
    useful working scale. Frame the destination-side circuit, or — when the day
    ends at the terminal and nothing remains to do there — the origin side.
    """
    if not intercity_edges or "Drive" in intercity_edges.values():
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
    has_destination_stop = any(kind_of(pin_id) not in TERMINAL_KINDS for pin_id in destination_ids)
    return destination_ids if has_destination_stop else route_ids[: start_index + 1]
