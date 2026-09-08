import type { MapAirport, MapPin } from "../../types";

export function isAirportTarget(pin: MapPin | MapAirport): pin is MapAirport {
  return pin.id === "airport";
}

export function isInspectableMapPin(
  pin: MapPin | MapAirport | null,
): pin is MapPin {
  return !!pin && !isAirportTarget(pin);
}

export function isJourneyTerminal(pin: MapPin | MapAirport): boolean {
  return ["airport", "station", "bus_station", "origin"].includes(pin.kind);
}

export function scheduleMapOverlayDraw(draw: () => void): () => void {
  const frame = window.requestAnimationFrame(draw);
  return () => window.cancelAnimationFrame(frame);
}
