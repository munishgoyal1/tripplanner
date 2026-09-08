import type { SelectItemOptions } from "../../api";
import type { MapPin } from "../../types";

export function kindForGooglePlace(types: string[] | undefined): "attraction" | "hotel" | "meal" {
  if (types?.some((type) => type === "lodging" || type === "hotel")) return "hotel";
  if (types?.some((type) => type === "restaurant" || type === "meal_takeaway")) return "meal";
  return "attraction";
}

export function mapPinFromGooglePlace(place: any): MapPin | null {
  const name = String(place?.name || "").trim();
  const location = place?.geometry?.location;
  const lat = typeof location?.lat === "function" ? location.lat() : location?.lat;
  const lng = typeof location?.lng === "function" ? location.lng() : location?.lng;
  if (!name || !Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  let photo: string | null = null;
  try {
    photo = place.photos?.[0]?.getUrl?.({ maxWidth: 800 }) ?? null;
  } catch {
    photo = null;
  }
  return {
    id: `candidate:${String(place.place_id || name).trim().toLowerCase()}`,
    name,
    kind: kindForGooglePlace(place.types),
    selected: false,
    day: null,
    lat,
    lng,
    rating: typeof place.rating === "number" ? place.rating : null,
    address: String(place.formatted_address || ""),
    photo,
    occurrences: [],
  };
}

export function optionsForStopDay(day: string): SelectItemOptions | undefined {
  const parsed = Number(day);
  return day !== "auto" && Number.isInteger(parsed) && parsed > 0 ? { day: parsed } : undefined;
}