import type { MapLeg, MapPin, MapRoadCircuit, MapView } from "../../types";
import { hotelIdentityGroups, hotelIdentityMatches } from "./placeIdentity";

const FLIGHT_ROUTE_COLOR = "#2563eb";
const ROAD_ROUTE_COLOR = "#111827";
const TRAIN_ROUTE_COLOR = "#6b7280";

const TRANSPORT_ICON_PATHS = {
  flight: "M -9,-1 -3,-2 1,-7 3,-7 1,-2 8,-1 9,0 8,1 1,2 3,7 1,7 -3,2 -9,1 Z",
  bus: "M -8,-4 6,-4 8,-2 8,4 -8,4 Z M -4,-4 -4,1 M 2,-4 2,1",
  car: "M -7,-4 3,-4 7,-1 7,3 4,4 -7,4 Z M -3,-4 -3,1 M 2,-4 4,0",
  train: "M -8,-4 5,-4 8,-1 8,4 -8,4 Z M -4,-4 -4,1 M 2,-4 2,1 M -5,4 -7,7 M 5,4 7,7",
} as const;

function intercityRouteStyle(mode: string): Record<string, unknown> {
  const normalizedMode = mode.trim().toLowerCase();
  const transport = normalizedMode === "flight"
    ? "flight"
    : normalizedMode === "train" || normalizedMode === "rail"
      ? "train"
      : normalizedMode === "bus"
        ? "bus"
        : "car";
  const color = transport === "flight"
    ? FLIGHT_ROUTE_COLOR
    : transport === "train"
      ? TRAIN_ROUTE_COLOR
      : ROAD_ROUTE_COLOR;
  return {
    strokeColor: color,
    strokeOpacity: 0,
    strokeWeight: 3,
    icons: [
      {
        icon: { path: "M 0,-1 0,1", strokeColor: color, strokeOpacity: 0.95, scale: 3 },
        repeat: transport === "flight" ? "14px" : "10px",
      },
      {
        icon: {
          path: "M -6,0 A 6,6 0 1,0 6,0 A 6,6 0 1,0 -6,0 Z",
          fillColor: "#ffffff",
          fillOpacity: 0.95,
          strokeColor: color,
          strokeOpacity: 0.9,
          strokeWeight: 1,
          scale: 1,
        },
        offset: "50%",
      },
      {
        icon: {
          path: TRANSPORT_ICON_PATHS[transport],
          fillColor: color,
          fillOpacity: 1,
          strokeColor: color,
          strokeOpacity: 1,
          strokeWeight: 0.6,
          scale: 0.65,
        },
        offset: "50%",
      },
    ],
  };
}

export function isIntercityTravel(kind: string, name: string): boolean {
  if (kind === "flight") return true;
  if (kind === "transport") return true;
  const normalizedName = name.trim().toLowerCase();
  const directionalGroundTravel = /\b(?:drive|driving|car|road (?:journey|transfer))\b/.test(normalizedName)
    && /\bto\b|->|→/.test(normalizedName);
  return directionalGroundTravel
    || /^(?:toy\s+train|train):?\s+.+\s+to\s+.+/.test(normalizedName);
}

export function formatLegLabel(leg: { distance_display: string; duration_display: string }): string {
  return `${leg.distance_display} · ${leg.duration_display}`;
}

export function mapContextForScope(view: MapView, scope: number | "all" | null) {
  if (scope === null) return null;
  if (scope === "all") {
    return {
      label: "All days",
      title: view.destination,
      schedule: `${view.days.length} ${view.days.length === 1 ? "day" : "days"}`,
      travel: "Complete trip",
    };
  }
  const day = view.days.find((candidate) => candidate.day === scope);
  if (!day) return null;
  const schedule = day.schedule;
  return {
    label: day.label,
    title: day.context_name || view.destination,
    schedule: schedule
      ? `${schedule.duration_display} · ${schedule.start}–${schedule.end}${schedule.estimated ? " est." : ""}`
      : "Schedule unavailable",
    travel: `${day.route.duration_display} · ${day.route.distance_display} · ${day.route.mode}`,
  };
}

export function roadCircuitsForView(view: MapView): MapRoadCircuit[] {
  return view.road_circuits ?? view.drive_circuits ?? [];
}

export function roadCircuitForId(view: MapView, circuitId: string): MapRoadCircuit | null {
  return roadCircuitsForView(view).find((candidate) => candidate.id === circuitId) ?? null;
}

export function mapContextForRoadCircuit(view: MapView, circuitId: string) {
  const circuit = roadCircuitForId(view, circuitId);
  if (!circuit) return null;
  const scenicCount = circuit.waypoints?.filter((waypoint) => waypoint.role === "scenic").length ?? 0;
  const mealCount = circuit.waypoints?.filter((waypoint) => waypoint.role === "meal").length ?? 0;
  const stopParts = [
    scenicCount ? `${scenicCount} scenic ${scenicCount === 1 ? "stop" : "stops"}` : "",
    mealCount ? `${mealCount} meal ${mealCount === 1 ? "break" : "breaks"}` : "",
  ].filter(Boolean);
  return {
    label: `${circuit.mode} transfer · Day ${circuit.day}`,
    title: circuit.label,
    scheduleLabel: "Stops",
    schedule: stopParts.join(" · ") || "Direct road transfer",
    travelLabel: "Road",
    travel: `${circuit.route.duration_display} · ${circuit.route.distance_display}`,
  };
}

export function routeStyleForLeg(
  leg: MapLeg,
  dayColor: string,
  connectsHotels = false,
): Record<string, unknown> {
  if (connectsHotels && !leg.intercity) {
    return {
      strokeColor: dayColor,
      strokeOpacity: 0,
      strokeWeight: 3,
      icons: [{
        icon: { path: "M 0,-1 0,1", strokeColor: dayColor, strokeOpacity: 0.9, scale: 3 },
        repeat: "10px",
      }],
    };
  }
  if (!leg.intercity) {
    return { strokeColor: dayColor, strokeOpacity: 0.85, strokeWeight: 3 };
  }
  return intercityRouteStyle(leg.mode);
}

export function routePathForPinIds(pinIds: string[], pins: MapPin[]): Array<{ lat: number; lng: number }> {
  const pinById = new Map(pins.map((pin) => [pin.id, pin] as const));
  return pinIds
    .map((id) => pinById.get(id))
    .filter((pin): pin is MapPin => !!pin)
    .map((pin) => ({ lat: pin.lat, lng: pin.lng }));
}

export function visitOrdersForDay(view: MapView, dayNumber: number): Map<string, number> {
  const day = view.days.find((candidate) => candidate.day === dayNumber);
  const pins = (day?.pin_ids ?? [])
    .map((id) => view.pins.find((candidate) => candidate.id === id))
    .filter((pin): pin is MapPin => !!pin && !["hotel", "airport", "station", "bus_station", "origin"].includes(pin.kind));
  const ordered = [...new Map(pins.map((pin) => [pin.id, pin])).values()].sort((left, right) => {
    const leftStop = left.occurrences.find((occurrence) => occurrence.day === dayNumber)?.stop;
    const rightStop = right.occurrences.find((occurrence) => occurrence.day === dayNumber)?.stop;
    return (leftStop ?? Number.MAX_SAFE_INTEGER) - (rightStop ?? Number.MAX_SAFE_INTEGER);
  });
  return new Map(ordered.map((pin, index) => [pin.id, index + 1]));
}

export function hotelLabelsForDay(view: MapView, dayNumber: number): Map<string, string> {
  const day = view.days.find((candidate) => candidate.day === dayNumber);
  const hotels = (day?.pin_ids ?? [])
    .map((id) => view.pins.find((candidate) => candidate.id === id))
    .filter((pin): pin is MapPin => !!pin && pin.kind === "hotel");
  const identities = hotelIdentityGroups(hotels.map((pin) => pin.name));
  const labels = new Map(
    identities.map((identity, index) => [identity, identities.length > 1 ? `H${index + 1}` : "H"]),
  );
  return new Map(hotels.map((pin) => {
    const identity = identities.find((candidate) => hotelIdentityMatches(candidate, pin.name));
    return [pin.id, labels.get(identity!)!];
  }));
}

export function pinsForDayCircuit(view: MapView, dayNumber: number): MapPin[] {
  const day = view.days.find((candidate) => candidate.day === dayNumber);
  if (!day) return [];
  return (day.circuit_pin_ids ?? day.pin_ids)
    .map((id) => view.pins.find((pin) => pin.id === id))
    .filter((pin): pin is MapPin => !!pin);
}

export function pinsForDayRoute(view: MapView, dayNumber: number): MapPin[] {
  const day = view.days.find((candidate) => candidate.day === dayNumber);
  if (!day) return [];
  return day.pin_ids
    .map((id) => view.pins.find((pin) => pin.id === id))
    .filter((pin): pin is MapPin => !!pin);
}

export function hotelReturnForDay(
  view: MapView,
  dayNumber: number,
): { pin: MapPin; label: string } | null {
  const day = view.days.find((candidate) => candidate.day === dayNumber);
  if (
    !day
    || day.pin_ids.length < 2
    || day.pin_ids[0] !== day.pin_ids[day.pin_ids.length - 1]
  ) return null;
  const pin = view.pins.find((candidate) => candidate.id === day.pin_ids[0]);
  if (!pin || pin.kind !== "hotel") return null;
  const end = day.schedule?.end;
  return {
    pin,
    label: end ? `Return · ${end}${day.schedule?.estimated ? " est." : ""}` : "Return",
  };
}

export function pinsForRoadCircuit(view: MapView, circuitId: string): MapPin[] {
  const circuit = roadCircuitForId(view, circuitId);
  if (!circuit) return [];
  return circuit.pin_ids
    .map((id) => view.pins.find((pin) => pin.id === id))
    .filter((pin): pin is MapPin => !!pin);
}

export const pinsForDriveCircuit = pinsForRoadCircuit;