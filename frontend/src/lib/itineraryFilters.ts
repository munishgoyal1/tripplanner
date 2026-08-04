import type { ItineraryStop, MapDay, MapLeg, MapView } from "../types";

export type ItineraryFilter = "flight" | "road" | "train" | "hotel";

function normalized(value: string): string {
  return value.trim().toLowerCase();
}

function filterForMode(mode: string): ItineraryFilter | null {
  const value = normalized(mode);
  if (value === "flight") return "flight";
  if (value === "train" || value === "rail") return "train";
  if (["bus", "car", "drive", "driving", "road"].includes(value)) return "road";
  return null;
}

export function filterForItineraryStop(stop: ItineraryStop): ItineraryFilter | null {
  if (stop.kind === "hotel") return "hotel";
  if (stop.kind === "flight") return "flight";
  if (!stop.route_circuit_id && !["transport", "other"].includes(stop.kind)) return null;
  const name = normalized(stop.name);
  if (/\b(?:train|rail)\b/.test(name)) return "train";
  if (stop.route_circuit_id || /\b(?:bus|car|drive|driving|road)\b/.test(name)) return "road";
  return null;
}

export function itineraryStopMatchesFilters(
  stop: ItineraryStop,
  filters: readonly ItineraryFilter[],
): boolean {
  if (filters.length === 0) return true;
  const filter = filterForItineraryStop(stop);
  return filter != null && filters.includes(filter);
}

function filterForLeg(leg: MapLeg): ItineraryFilter | null {
  return leg.intercity ? filterForMode(leg.mode) : null;
}

export function filterMapView(
  view: MapView,
  filters: readonly ItineraryFilter[],
): MapView {
  if (filters.length === 0) return view;
  const selected = new Set(filters);
  const pinById = new Map(view.pins.map((pin) => [pin.id, pin] as const));
  const retainedPinIds = new Set<string>();
  const retainedCircuitIds = new Set<string>();
  const driveCircuits = selected.has("road") ? view.drive_circuits ?? [] : [];
  driveCircuits.forEach((circuit) => {
    retainedCircuitIds.add(circuit.id);
  });

  const days = view.days.flatMap((day): MapDay[] => {
    const dayPinIds = new Set<string>();
    const dayCircuits = driveCircuits.filter((circuit) => circuit.day === day.day);
    dayCircuits.forEach((circuit) => circuit.pin_ids.forEach((id) => dayPinIds.add(id)));
    const sourceLegs = [...(day.legs ?? [])];
    dayCircuits.flatMap((circuit) => circuit.legs).forEach((leg) => {
      if (!sourceLegs.some((candidate) => (
        candidate.from_pin_id === leg.from_pin_id
        && candidate.to_pin_id === leg.to_pin_id
        && candidate.route_circuit_id === leg.route_circuit_id
      ))) {
        sourceLegs.push(leg);
      }
    });
    const legs = sourceLegs.filter((leg) => {
      const filter = filterForLeg(leg);
      return (filter != null && selected.has(filter))
        || (leg.route_circuit_id != null && retainedCircuitIds.has(leg.route_circuit_id));
    });
    legs.forEach((leg) => {
      dayPinIds.add(leg.from_pin_id);
      dayPinIds.add(leg.to_pin_id);
    });
    day.pin_ids.forEach((id) => {
      const pin = pinById.get(id);
      if (!pin) return;
      if (selected.has("hotel") && pin.kind === "hotel" && pin.selected) {
        dayPinIds.add(id);
      }
    });
    const sourcePinIds = [...day.pin_ids];
    dayCircuits.flatMap((circuit) => circuit.pin_ids).forEach((id) => {
      if (!sourcePinIds.includes(id)) sourcePinIds.push(id);
    });
    const pinIds = sourcePinIds.filter((id) => dayPinIds.has(id));
    if (pinIds.length === 0 && legs.length === 0) return [];
    pinIds.forEach((id) => retainedPinIds.add(id));
    return [{
      ...day,
      pin_ids: pinIds,
      circuit_pin_ids: (day.circuit_pin_ids ?? day.pin_ids)
        .filter((id) => dayPinIds.has(id)),
      legs,
    }];
  });
  const visibleDays = new Set(days.map((day) => day.day));
  const pins = view.pins.filter((pin) => retainedPinIds.has(pin.id));
  return {
    ...view,
    pins,
    days,
    drive_circuits: driveCircuits.filter((circuit) => visibleDays.has(circuit.day)),
    available_days: view.available_days.filter((day) => visibleDays.has(day)),
    unscheduled_pin_ids: [],
    airport: selected.has("flight") ? view.airport : null,
    empty_message: pins.length === 0 ? "No itinerary items match these filters." : view.empty_message,
  };
}