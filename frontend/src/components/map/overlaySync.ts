import type { MapAirport, MapPin, MapView } from "../../types";
import { pinMatchesFocus } from "./focusMatching";
import {
  airportIcon,
  dotIcon,
  hotelIcon,
  pinIcon,
  routeLegIcon,
  SUGGEST_COLOR,
  terminalIcon,
} from "./mapIcons";
import {
  formatLegLabel,
  hotelLabelsForDay,
  hotelReturnForDay,
  routeStyleForLeg,
  roadCircuitForId,
  visitOrdersForDay,
} from "./routeDerivations";
import { fitDayRoute, fitRoadCircuit, zoomToPin, type PinMarkerEntry } from "./viewportSync";

interface RouteFocus {
  day: number;
  circuitId?: string;
}

interface OverlayFocus {
  name?: string | null;
  day?: number;
  stop?: number;
}

interface SynchronizeMapOverlaysOptions {
  google: any;
  map: any;
  view: MapView;
  suppressFallbackRoutes?: boolean;
  activeDay: number | null;
  activeRouteCircuitId?: string | null;
  candidatePin: MapPin | null;
  focus: OverlayFocus;
  pendingFocus: MapPin | MapAirport | null;
  pendingRouteFocus: RouteFocus | number | null;
  previousOverlays: any[];
  onPinClick: (pin: MapPin) => void;
  onCandidateClick: (pin: MapPin) => void;
  onAirportClick: (airport: MapAirport) => void;
}

export interface MapOverlaySyncResult {
  overlays: any[];
  pinMarkers: PinMarkerEntry[];
  focusedPin: MapPin | MapAirport | null;
  consumedPendingFocus: boolean;
  consumedPendingRouteFocus: boolean;
}

export function clearMapOverlays(overlays: any[]): void {
  overlays.forEach((overlay) => overlay.setMap(null));
}

export function synchronizeMapOverlays({
  google,
  map,
  view,
  suppressFallbackRoutes = false,
  activeDay,
  activeRouteCircuitId,
  candidatePin,
  focus,
  pendingFocus,
  pendingRouteFocus,
  previousOverlays,
  onPinClick,
  onCandidateClick,
  onAirportClick,
}: SynchronizeMapOverlaysOptions): MapOverlaySyncResult {
  clearMapOverlays(previousOverlays);
  const overlays: any[] = [];
  const pinMarkers: PinMarkerEntry[] = [];

  const dayColor = new Map<number, string>();
  view.days.forEach((day) => dayColor.set(day.day, day.color));
  const visitOrderByPinId = new Map<string, number>();
  const orderDays = activeDay == null
    ? view.days
    : view.days.filter((day) => day.day === activeDay);
  orderDays.forEach((day) => {
    visitOrdersForDay(view, day.day).forEach((order, id) => {
      if (!visitOrderByPinId.has(id)) visitOrderByPinId.set(id, order);
    });
  });
  const hotelLabelByPinId = new Map<string, string>();
  orderDays.forEach((day) => {
    hotelLabelsForDay(view, day.day).forEach((label, id) => {
      if (!hotelLabelByPinId.has(id) || hotelLabelByPinId.get(id) === "H") {
        hotelLabelByPinId.set(id, label);
      }
    });
  });

  const focusedRoadCircuit = activeRouteCircuitId
    ? roadCircuitForId(view, activeRouteCircuitId)
    : null;
  const activeDayPinIds = new Set(activeDay === null
    ? []
    : focusedRoadCircuit?.pin_ids
      ?? view.days.find((day) => day.day === activeDay)?.pin_ids
      ?? []);
  const visible = (pin: MapPin) => activeDay === null || activeDayPinIds.has(pin.id);
  const bounds = new google.maps.LatLngBounds();
  let hasBounds = false;
  const pinById = new Map(view.pins.map((pin) => [pin.id, pin] as const));
  const roadWaypointRoleByPinId = new Map(
    focusedRoadCircuit?.waypoints?.map((waypoint) => [waypoint.pin_id, waypoint.role] as const)
      ?? [],
  );

  for (const pin of view.pins) {
    if (!visible(pin)) continue;
    const focused = pinMatchesFocus(pin, focus.name, focus.day, focus.stop);
    const visitOrder = visitOrderByPinId.get(pin.id);
    const markerDay = activeDay !== null && activeDayPinIds.has(pin.id)
      ? activeDay
      : pin.day;
    const iconFor = (isFocused: boolean) => {
      if (pin.kind === "hotel") return {
        url: hotelIcon(isFocused, hotelLabelByPinId.get(pin.id) ?? "H"),
        scaledSize: new google.maps.Size(34, 44),
        anchor: new google.maps.Point(17, 44),
      };
      if (["airport", "station", "bus_station", "origin"].includes(pin.kind)) return {
        url: pin.kind === "airport" ? airportIcon(isFocused) : terminalIcon(pin.kind),
        scaledSize: new google.maps.Size(34, 44),
        anchor: new google.maps.Point(17, 44),
      };
      const roadRole = roadWaypointRoleByPinId.get(pin.id);
      if (roadRole === "scenic" || roadRole === "meal") return {
        url: pinIcon("#111827", roadRole === "scenic" ? "S" : "M", isFocused),
        scaledSize: new google.maps.Size(34, 44),
        anchor: new google.maps.Point(17, 44),
      };
      if (markerDay && visitOrder) {
        const color = dayColor.get(markerDay) || "#64748b";
        return {
          url: pinIcon(color, String(visitOrder), isFocused),
          scaledSize: new google.maps.Size(34, 44),
          anchor: new google.maps.Point(17, 44),
        };
      }
      return {
        url: dotIcon(pin.selected ? "#0d9488" : SUGGEST_COLOR, isFocused),
        scaledSize: new google.maps.Size(isFocused ? 24 : 18, isFocused ? 24 : 18),
        anchor: new google.maps.Point(isFocused ? 12 : 9, isFocused ? 12 : 9),
      };
    };
    const normalIcon = iconFor(false);
    const focusedIcon = iconFor(true);
    const baseZIndex = pin.selected ? 1000 : pin.day ? 600 : 400;
    const marker = new google.maps.Marker({
      position: { lat: pin.lat, lng: pin.lng },
      map,
      title: pin.name,
      icon: focused ? focusedIcon : normalIcon,
      optimized: false,
      zIndex: focused ? 1400 : baseZIndex,
    });
    marker.addListener("click", () => onPinClick(pin));
    pinMarkers.push({ pin, marker, normalIcon, focusedIcon, baseZIndex });
    overlays.push(marker);
    bounds.extend({ lat: pin.lat, lng: pin.lng });
    hasBounds = true;
  }

  if (candidatePin) {
    const marker = new google.maps.Marker({
      position: { lat: candidatePin.lat, lng: candidatePin.lng },
      map,
      title: candidatePin.name,
      icon: {
        url: dotIcon("#e11d48"),
        scaledSize: new google.maps.Size(24, 24),
        anchor: new google.maps.Point(12, 12),
      },
      optimized: false,
      zIndex: 1200,
    });
    marker.addListener("click", () => onCandidateClick(candidatePin));
    overlays.push(marker);
    bounds.extend({ lat: candidatePin.lat, lng: candidatePin.lng });
    hasBounds = true;
  }

  if (view.airport) {
    const airport = view.airport;
    const marker = new google.maps.Marker({
      position: { lat: airport.lat, lng: airport.lng },
      map,
      title: airport.name,
      icon: {
        url: airportIcon(),
        scaledSize: new google.maps.Size(34, 44),
        anchor: new google.maps.Point(17, 44),
      },
      optimized: false,
      zIndex: 200,
    });
    marker.addListener("click", () => onAirportClick(airport));
    overlays.push(marker);
    if (activeDay === null) {
      bounds.extend({ lat: airport.lat, lng: airport.lng });
      hasBounds = true;
    }
  }

  for (const day of view.days) {
    if (activeDay !== null && day.day !== activeDay) continue;
    const legs = focusedRoadCircuit?.day === day.day
      ? focusedRoadCircuit.legs
      : activeRouteCircuitId
      ? (day.legs ?? []).filter((leg) => leg.route_circuit_id === activeRouteCircuitId)
      : day.legs ?? [];
    for (const leg of legs) {
      const start = pinById.get(leg.from_pin_id);
      const end = pinById.get(leg.to_pin_id);
      if (!start || !end) continue;
      overlays.push(new google.maps.Polyline({
        path: [
          { lat: start.lat, lng: start.lng },
          { lat: end.lat, lng: end.lng },
        ],
        geodesic: true,
        ...routeStyleForLeg(
          leg,
          day.color,
          start.kind === "hotel" && end.kind === "hotel",
        ),
        map,
      }));
    }
    if (legs.length === 0 && !suppressFallbackRoutes) {
      const routePinIds = focusedRoadCircuit?.day === day.day
        ? focusedRoadCircuit.pin_ids
        : day.pin_ids;
      const routePins = routePinIds
        .map((id) => pinById.get(id))
        .filter((pin): pin is MapPin => !!pin);
      for (let index = 1; index < routePins.length; index += 1) {
        const start = routePins[index - 1];
        const end = routePins[index];
        overlays.push(new google.maps.Polyline({
          path: [
            { lat: start.lat, lng: start.lng },
            { lat: end.lat, lng: end.lng },
          ],
          geodesic: true,
          ...routeStyleForLeg(
            { ...day.route, from_pin_id: start.id, to_pin_id: end.id },
            day.color,
            start.kind === "hotel" && end.kind === "hotel",
          ),
          map,
        }));
      }
    }

    if (activeDay === day.day) {
      for (const leg of legs) {
        const start = pinById.get(leg.from_pin_id);
        const end = pinById.get(leg.to_pin_id);
        if (!start || !end) continue;
        const label = formatLegLabel(leg);
        const labelOffset = leg.intercity ? 0.35 : 0.5;
        overlays.push(new google.maps.Marker({
          position: {
            lat: start.lat + (end.lat - start.lat) * labelOffset,
            lng: start.lng + (end.lng - start.lng) * labelOffset,
          },
          map,
          clickable: false,
          title: `${label} · ${leg.mode}`,
          icon: {
            url: routeLegIcon(label, day.color),
            scaledSize: new google.maps.Size(112, 26),
            anchor: new google.maps.Point(56, 13),
          },
          optimized: false,
          zIndex: 500,
        }));
      }
    }
  }

  if (activeDay !== null && !activeRouteCircuitId) {
    const hotelReturn = hotelReturnForDay(view, activeDay);
    const activeDayView = view.days.find((day) => day.day === activeDay);
    if (hotelReturn && activeDayView) {
      overlays.push(new google.maps.Marker({
        position: { lat: hotelReturn.pin.lat, lng: hotelReturn.pin.lng },
        map,
        clickable: false,
        title: `${hotelReturn.label} to ${hotelReturn.pin.name}`,
        icon: {
          url: routeLegIcon(hotelReturn.label, activeDayView.color),
          scaledSize: new google.maps.Size(112, 26),
          anchor: new google.maps.Point(56, 52),
        },
        optimized: false,
        zIndex: 1100,
      }));
    }
  }

  let consumedPendingFocus = false;
  let consumedPendingRouteFocus = false;
  let focusedPin: MapPin | MapAirport | null = null;
  if (pendingFocus) {
    zoomToPin(map, pendingFocus);
    consumedPendingFocus = true;
    focusedPin = pendingFocus;
  } else if (pendingRouteFocus !== null) {
    const focusDay = typeof pendingRouteFocus === "number"
      ? pendingRouteFocus
      : pendingRouteFocus.day;
    const focusCircuitId = typeof pendingRouteFocus === "number"
      ? undefined
      : pendingRouteFocus.circuitId;
    // Prefer the tight road-circuit fit; fall back to the whole-day route so a
    // missing/unbuilt circuit still consumes the pending focus instead of
    // silently retrying every redraw.
    if (
      (focusCircuitId && fitRoadCircuit(google, map, view, focusCircuitId))
      || fitDayRoute(google, map, view, focusDay)
    ) {
      consumedPendingRouteFocus = true;
    } else if (hasBounds && !bounds.isEmpty()) {
      map.fitBounds(bounds, 64);
    }
  } else if (hasBounds && !bounds.isEmpty()) {
    map.fitBounds(bounds, 64);
  }

  return {
    overlays,
    pinMarkers,
    focusedPin,
    consumedPendingFocus,
    consumedPendingRouteFocus,
  };
}