import type { MapLeg, MapPin, MapView } from "../../types";

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
  if (kind !== "transport") return false;
  const normalizedName = name.trim().toLowerCase();
  return ["train", "rail", "bus", "drive:", "road transfer", "private car"]
    .some((token) => normalizedName.includes(token));
}

export function formatLegLabel(leg: { distance_display: string; duration_display: string }): string {
  return `${leg.distance_display} · ${leg.duration_display}`;
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
    .filter((pin): pin is MapPin => !!pin && !["hotel", "airport", "station", "bus_station"].includes(pin.kind));
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
  const ordered = [...new Map(hotels.map((pin) => [pin.id, pin])).values()];
  const numbered = ordered.length > 1;
  return new Map(ordered.map((pin, index) => [pin.id, numbered ? `H${index + 1}` : "H"]));
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