import type { MapPin } from "../../types";

export function placeNameMatches(candidate: string, focusName: string): boolean {
  const normalize = (value: string) => value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  const normalizedCandidate = normalize(candidate);
  const normalizedFocus = normalize(focusName);
  if (!normalizedCandidate || !normalizedFocus) return false;
  return normalizedCandidate === normalizedFocus
    || normalizedCandidate.includes(normalizedFocus)
    || normalizedFocus.includes(normalizedCandidate)
    || normalizedFocus.split(" ").every((token) => normalizedCandidate.split(" ").includes(token));
}

export function focusedDayForPin(pin: MapPin, focusDay?: number): number | null {
  return focusDay && pin.occurrences.some((occurrence) => occurrence.day === focusDay)
    ? focusDay
    : pin.day;
}

export function pinMatchesFocus(
  pin: MapPin,
  focusName?: string | null,
  focusDay?: number,
  focusStop?: number,
): boolean {
  if (
    !focusName
    || !(
      placeNameMatches(pin.name, focusName)
      || (pin.source_name && placeNameMatches(pin.source_name, focusName))
    )
  ) return false;
  return (focusDay == null && focusStop == null) || pin.occurrences.some((occurrence) => (
    (focusDay == null || occurrence.day === focusDay)
    && (focusStop == null || occurrence.stop === focusStop)
  ));
}