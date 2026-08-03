import type { MapAirport, MapPin, MapView } from "../../types";
import { pinMatchesFocus } from "./focusMatching";
import { pinsForDayCircuit, pinsForDayRoute } from "./routeDerivations";

export interface PinMarkerEntry {
  pin: MapPin;
  marker: any;
  normalIcon: any;
  focusedIcon: any;
  baseZIndex: number;
}

export function syncPinMarkerFocus(
  entries: PinMarkerEntry[],
  focusName?: string | null,
  focusDay?: number,
  focusStop?: number,
): void {
  entries.forEach(({ pin, marker, normalIcon, focusedIcon, baseZIndex }) => {
    const focused = pinMatchesFocus(pin, focusName, focusDay, focusStop);
    marker.setIcon(focused ? focusedIcon : normalIcon);
    marker.setZIndex(focused ? 1400 : baseZIndex);
  });
}

export function fitDayCircuit(
  google: any,
  map: any,
  view: MapView,
  dayNumber: number,
): boolean {
  const pins = pinsForDayCircuit(view, dayNumber);
  if (pins.length === 0) return false;
  const bounds = new google.maps.LatLngBounds();
  pins.forEach((pin) => bounds.extend({ lat: pin.lat, lng: pin.lng }));
  map.fitBounds(bounds, 64);
  return true;
}

export function fitDayRoute(
  google: any,
  map: any,
  view: MapView,
  dayNumber: number,
): boolean {
  const pins = pinsForDayRoute(view, dayNumber);
  if (pins.length === 0) return false;
  const bounds = new google.maps.LatLngBounds();
  pins.forEach((pin) => bounds.extend({ lat: pin.lat, lng: pin.lng }));
  map.fitBounds(bounds, 64);
  return true;
}

export function zoomToPin(map: any, pin: MapPin | MapAirport): void {
  map.panTo({ lat: pin.lat, lng: pin.lng });
  map.setZoom(15);
}

export function capCircuitZoom(map: any): void {
  if ((map.getZoom() ?? 0) > 14) map.setZoom(14);
}