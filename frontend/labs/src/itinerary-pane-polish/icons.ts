import {
  BedDouble, BusFront, CarFront, Footprints, Landmark, MapPin, Plane, PlaneLanding, PlaneTakeoff, Route, Ship,
  TrainFront, UtensilsCrossed,
} from "lucide-react";
import type { ItineraryStop } from "../../../src/types";

export function modeIcon(mode: string) {
  const value = mode.toLowerCase();
  if (value.includes("walk")) return Footprints;
  if (value.includes("boat") || value.includes("ferry")) return Ship;
  if (value.includes("train") || value.includes("rail")) return TrainFront;
  if (value.includes("bus") || value.includes("coach")) return BusFront;
  if (value.includes("flight")) return Plane;
  if (value.includes("drive") || value.includes("car") || value.includes("taxi")) return CarFront;
  return Route;
}

/** Line icons that stand in for production's emoji kind glyphs (harmonised options only). */
export function kindIcon(stop: ItineraryStop) {
  if (stop.kind === "hotel") return BedDouble;
  if (stop.kind === "meal" || stop.kind === "restaurant") return UtensilsCrossed;
  if (stop.kind === "flight") return Plane;
  if (stop.kind === "airport") return stop.terminal_role === "departure" ? PlaneTakeoff : PlaneLanding;
  if (stop.kind === "station") return TrainFront;
  if (stop.kind === "bus_station") return BusFront;
  if (stop.kind === "transport") return CarFront;
  if (stop.kind === "attraction") return Landmark;
  return MapPin;
}
