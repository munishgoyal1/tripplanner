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

from tripplanner.web.map_pins import _haversine_km, _route_circuit_id
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
_TRANSFER_DESTINATION_KINDS = {
    "Flight": "airport",
    "Train": "station",
    "Bus": "bus_station",
    "Drive": "hotel",
}

#: The journey a pair of terminals implies when the plan never named the leg.
_TERMINAL_MODES = {"airport": "Flight", "station": "Train", "bus_station": "Bus"}
IMPLIED_HOP_MIN_KM = 100.0
MAX_TERMINAL_GROUND_KM = 300.0


def implied_terminal_hop_mode(from_kind: str, to_kind: str, distance_km: float) -> str | None:
    """The inter-city mode two back-to-back terminals imply, if they imply one.

    A plan that lists a departure and an arrival terminal without naming the leg
    between them still moved the traveller between cities; reading it as a local
    day is what turns an ocean crossing into a drive.
    """
    if from_kind not in _TERMINAL_MODES or distance_km < IMPLIED_HOP_MIN_KM:
        return None
    return _TERMINAL_MODES.get(to_kind)

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
    detached_pin_ids: list[str] = field(default_factory=list)
    transfer_mode: str | None = None
    route_disconnected: bool = False

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
    #: Ground edges are committed only after a compatible destination is found.
    pending_edges: list[Edge] = field(default_factory=list)


class _JourneyWalk:
    """Single pass over one day's stops."""

    def __init__(self, day: int, resolve_pin: PinResolver) -> None:
        self.journey = DayJourney(day=day)
        self.saved_metrics: dict[str, dict[str, float]] = {}
        self._resolve_pin = resolve_pin
        self._open: _OpenTransfer | None = None
        self._pin_by_id: dict[str, dict[str, Any]] = {}

    # -- path primitives -------------------------------------------------

    def _remember(self, pin: dict[str, Any]) -> str:
        pin_id = str(pin["id"])
        self._pin_by_id[pin_id] = pin
        return pin_id

    def _include_map_pin(self, pin_id: str) -> None:
        if pin_id not in self.journey.map_pin_ids:
            self.journey.map_pin_ids.append(pin_id)

    def _place(self, pin_id: str) -> None:
        self._include_map_pin(pin_id)
        self.journey.route_ids.append(pin_id)

    def _detach(self, pin_id: str) -> None:
        self._include_map_pin(pin_id)
        if pin_id not in self.journey.detached_pin_ids:
            self.journey.detached_pin_ids.append(pin_id)

    def _reset_route(self) -> None:
        for pin_id in self.journey.route_ids:
            self._detach(pin_id)
        self.journey.route_ids.clear()
        self.journey.route_disconnected = True

    def _connect(self, to_id: str, transfer: _OpenTransfer) -> None:
        if not self.journey.route_ids:
            return
        edge = (self.journey.route_ids[-1], to_id)
        self.journey.intercity_edges[edge] = transfer.mode
        self.journey.circuit_edges[edge] = transfer.circuit_id

    def _commit_pending(self, to_id: str, transfer: _OpenTransfer) -> None:
        if not self.journey.route_ids:
            return
        edges = [*transfer.pending_edges, (self.journey.route_ids[-1], to_id)]
        for edge in edges:
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
        if self._open and not self._open.arrival_id and self._open.mode not in _GROUND_MODES:
            self._reset_route()
            self._open = None
        # Place a known arrival before resolving the next transfer's departure.
        self._close_pending_arrival()

        self.journey.transfer_mode = mode
        circuit_id = _route_circuit_id(self.journey.day, stop_index, mode)
        transfer = _OpenTransfer(mode=mode, circuit_id=circuit_id)
        metrics = _saved_metrics(stop)
        if metrics:
            self.saved_metrics[circuit_id] = metrics

        refs = _transport_terminal_refs(name, kind)
        resolved_terminals = [
            (index, self._remember(pin))
            for index, (terminal_kind, terminal_name) in enumerate(refs)
            if (pin := self._resolve_pin(terminal_name, terminal_kind))
        ]
        terminal_ids = [pin_id for _, pin_id in resolved_terminals]
        previous_transfer = self._open
        if previous_transfer and previous_transfer.mode in _GROUND_MODES and terminal_ids:
            self._commit_pending(terminal_ids[0], previous_transfer)
            self._open = None
        if len(terminal_ids) == len(refs) and len(terminal_ids) >= 2:
            origin_pin = self._pin_by_id[terminal_ids[0]]
            if not self._imply_terminal_hop(
                origin_pin, terminal_ids[0], str(origin_pin.get("kind") or "")
            ):
                self._reset_route()
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

        # A partial transfer may only remain open from a known departure. Without
        # that identity, the next local map pin is not evidence of an arrival.
        origin_id = next(
            (pin_id for index, pin_id in resolved_terminals if index == 0),
            None,
        )
        if origin_id and (mode != "Drive" or not self.journey.route_ids):
            self._place(origin_id)
        if origin_id or (mode == "Drive" and self.journey.route_ids):
            self._open = transfer
        elif terminal_ids:
            self._detach(terminal_ids[-1])

    def _visit_place(self, name: str, kind: str) -> None:
        if self._open and self._open.arrival_id and kind not in _ENROUTE_KINDS:
            self._close_pending_arrival()

        pin = self._resolve_pin(name, kind)
        if not pin:
            return
        pin_id = self._remember(pin)
        pin_kind = str(pin["kind"])

        transfer = self._open
        if transfer and self.journey.route_ids:
            expected_kind = _TRANSFER_DESTINATION_KINDS.get(transfer.mode)
            if transfer.arrival_id:
                if pin_kind not in TERMINAL_KINDS:
                    self._connect(pin_id, transfer)
                # A known ground arrival stays open through its waypoints.
                if transfer.mode not in _GROUND_MODES or pin_kind == "hotel":
                    self._open = None
            elif pin_kind == expected_kind:
                self._commit_pending(pin_id, transfer)
                self._open = None
            elif transfer.mode in _GROUND_MODES and pin_kind in _ENROUTE_KINDS:
                transfer.pending_edges.append((self.journey.route_ids[-1], pin_id))
            else:
                # An unresolved transfer cannot borrow a local pin as its
                # destination. Start a destination-side path without drawing
                # ground travel across the unresolved inter-city gap.
                self._open = None
                self._reset_route()
        elif not transfer and not self._imply_terminal_hop(pin, pin_id, pin_kind):
            self._detach(pin_id)
            return
        self._place(pin_id)

    def _imply_terminal_hop(
        self, pin: dict[str, Any], pin_id: str, pin_kind: str
    ) -> bool:
        """Draw the leg the plan forgot to name between two distant terminals."""
        if not self.journey.route_ids:
            return True
        previous = self._pin_by_id.get(self.journey.route_ids[-1])
        if not previous:
            return True
        coords = [(place.get("lat"), place.get("lng")) for place in (previous, pin)]
        if not all(isinstance(value, (int, float)) for pair in coords for value in pair):
            return True
        (from_lat, from_lng), (to_lat, to_lng) = coords
        distance = _haversine_km(
            (float(from_lat), float(from_lng)), (float(to_lat), float(to_lng))
        )
        previous_kind = str(previous.get("kind") or "")
        mode = implied_terminal_hop_mode(
            previous_kind,
            pin_kind,
            distance,
        )
        if not mode:
            one_terminal = (previous_kind in TERMINAL_KINDS) != (pin_kind in TERMINAL_KINDS)
            return not (one_terminal and distance > MAX_TERMINAL_GROUND_KM)
        self.journey.intercity_edges[(self.journey.route_ids[-1], pin_id)] = mode
        self.journey.transfer_mode = mode
        return True

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
    if journey.route_disconnected:
        if stay_id not in journey.map_pin_ids:
            journey.map_pin_ids.insert(0, stay_id)
        for extra_id in extra_stay_ids or []:
            if extra_id not in journey.map_pin_ids:
                journey.map_pin_ids.append(extra_id)
        return
    if route_ids and kind_of(route_ids[0]) == "origin":
        origin_id = route_ids.pop(0)
        _rebind_edges(journey.intercity_edges, origin_id, stay_id)
        _rebind_edges(journey.circuit_edges, origin_id, stay_id)

    # An excursion that came home must still come home after the reorder: moving
    # the stay to the front without this drops the return and leaves the day
    # ending at whatever it saw last.
    returns_to_stay = bool(route_ids) and route_ids[-1] == stay_id
    journey.route_ids = [stay_id, *(pin_id for pin_id in route_ids if pin_id != stay_id)]
    if stay_id not in journey.map_pin_ids:
        journey.map_pin_ids.insert(0, stay_id)
    if returns_to_stay and len(journey.route_ids) > 1:
        journey.route_ids.append(stay_id)
    if (
        len(journey.route_ids) >= 2
        and journey.transfer_mode == "Drive"
        and not journey.intercity_edges
        and kind_of(journey.route_ids[1]) == "hotel"
    ):
        journey.intercity_edges[(journey.route_ids[0], journey.route_ids[1])] = "Drive"
    for extra_id in extra_stay_ids or []:
        if extra_id not in journey.route_ids:
            journey.route_ids.append(extra_id)
        if extra_id not in journey.map_pin_ids:
            journey.map_pin_ids.append(extra_id)


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
