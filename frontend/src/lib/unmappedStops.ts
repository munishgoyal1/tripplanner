import { useSyncExternalStore } from "react";

import type { UnmappedStop } from "../types";

// The map knows which stops it could not pin; the itinerary is where the user
// notices one missing. Publishing through a small channel keeps that fact out
// of every component signature between them, the way notices already do.

let stops: UnmappedStop[] = [];
const listeners = new Set<() => void>();

export function publishUnmappedStops(next: UnmappedStop[]): void {
  const incoming = next ?? [];
  const unchanged =
    incoming.length === stops.length
    && incoming.every((stop, index) => stop.name === stops[index]?.name && stop.tier === stops[index]?.tier);
  if (unchanged) return;
  stops = incoming;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useUnmappedStop(name: string): UnmappedStop | null {
  const current = useSyncExternalStore(subscribe, () => stops, () => stops);
  const needle = name.trim().toLowerCase();
  // A label names no place, so its row has nothing to answer for.
  return (
    current.find((stop) => stop.tier !== "label" && stop.name.trim().toLowerCase() === needle)
    ?? null
  );
}
