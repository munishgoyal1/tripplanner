import { describe, expect, it } from "vitest";
import type { ItineraryStop, MapView } from "../types";
import { filterMapView, itineraryStopMatchesFilters } from "./itineraryFilters";

const route = {
  distance_km: 100,
  duration_min: 120,
  mode: "Drive",
  distance_display: "100 km",
  duration_display: "2 hr",
};

function pin(id: string, kind: string, day: number) {
  return {
    id,
    name: id,
    kind,
    selected: true,
    day,
    lat: day,
    lng: day,
    rating: null,
    address: "",
    photo: null,
    occurrences: [{ day, stop: 1, time: "09:00" }],
  };
}

describe("itinerary union filters", () => {
  it("unions selected itinerary categories without renumbering days", () => {
    const stops = [
      { name: "Flight: BLR to BHO", kind: "flight" },
      { name: "Drive from Bhopal to Indore", kind: "transport", route_circuit_id: "drive-2" },
      { name: "Train: Indore to Ujjain", kind: "transport" },
      { name: "Jehan Numa Palace", kind: "hotel" },
      { name: "Sanchi", kind: "attraction" },
    ] as ItineraryStop[];

    expect(stops
      .filter((stop) => itineraryStopMatchesFilters(stop, ["flight", "hotel"]))
      .map((stop) => stop.name)).toEqual(["Flight: BLR to BHO", "Jehan Numa Palace"]);
  });

  it("keeps selected transport endpoints and complete drive waypoints on the map", () => {
    const view: MapView = {
      enabled: true,
      destination: "Madhya Pradesh",
      center: null,
      pins: [
        pin("blr", "airport", 1), pin("bho", "airport", 1),
        pin("origin", "origin", 2), pin("break", "meal", 2), pin("indore-hotel", "hotel", 2),
        pin("indore-station", "station", 3), pin("ujjain-station", "station", 3),
        pin("sanchi", "attraction", 4), pin("bhopal-hotel", "hotel", 4),
      ],
      days: [
        { day: 1, label: "Day 1", color: "#2563eb", pin_ids: ["blr", "bho"], route: { ...route, mode: "Flight" }, legs: [{ ...route, mode: "Flight", from_pin_id: "blr", to_pin_id: "bho", intercity: true }] },
        { day: 2, label: "Day 2", color: "#e11d48", pin_ids: ["origin", "indore-hotel"], route, legs: [] },
        { day: 3, label: "Day 3", color: "#6b7280", pin_ids: ["indore-station", "ujjain-station"], route: { ...route, mode: "Train" }, legs: [{ ...route, mode: "Train", from_pin_id: "indore-station", to_pin_id: "ujjain-station", intercity: true }] },
        { day: 4, label: "Day 4", color: "#0d9488", pin_ids: ["bhopal-hotel", "sanchi", "ujjain-station"], route },
      ],
      drive_circuits: [{ id: "drive-2", day: 2, mode: "Drive", label: "Bhopal to Indore", pin_ids: ["origin", "break", "indore-hotel"], legs: [{ ...route, from_pin_id: "origin", to_pin_id: "break", intercity: true, route_circuit_id: "drive-2" }, { ...route, from_pin_id: "break", to_pin_id: "indore-hotel", intercity: true, route_circuit_id: "drive-2" }], route }],
      available_days: [1, 2, 3, 4],
      unscheduled_pin_ids: ["sanchi"],
      airport: null,
      empty_message: null,
    };

    const filtered = filterMapView(view, ["road", "train"]);

    expect(filtered.days.map((day) => day.day)).toEqual([2, 3]);
    expect(filtered.pins.map((candidate) => candidate.id)).toEqual([
      "origin", "break", "indore-hotel", "indore-station", "ujjain-station",
    ]);
    expect(filtered.drive_circuits?.[0]?.pin_ids).toEqual(["origin", "break", "indore-hotel"]);
    expect(filtered.days[0].legs).toHaveLength(2);
    expect(filtered.days[1].legs?.[0]?.mode).toBe("Train");
  });
});