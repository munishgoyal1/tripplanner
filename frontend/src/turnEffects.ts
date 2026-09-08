import type { TripView, TurnEffect } from "./types";

const MAX_EFFECTS = 6;

interface Slot {
  kind: string;
  name: string;
  day: number;
  stop: number;
}

function slotsOf(view: TripView | null): Map<string, Slot> {
  const out = new Map<string, Slot>();
  for (const item of view?.items ?? []) {
    if (!item.selected) continue;
    for (const occurrence of item.occurrences) {
      out.set(`${item.name}|${occurrence.day}|${occurrence.stop}`, {
        kind: item.kind,
        name: item.name,
        day: occurrence.day,
        stop: occurrence.stop,
      });
    }
  }
  return out;
}

/**
 * Name the stops a turn changed so a reply can move Itinerary, Map, and Details.
 * A name that disappears from one slot and reappears in another reads as "moved"
 * rather than as an unrelated removal plus addition.
 */
export function diffTurnEffects(before: TripView | null, after: TripView | null): TurnEffect[] {
  const previous = slotsOf(before);
  const next = slotsOf(after);
  const added: Slot[] = [];
  const removed: Slot[] = [];
  for (const [key, slot] of next) if (!previous.has(key)) added.push(slot);
  for (const [key, slot] of previous) if (!next.has(key)) removed.push(slot);

  const removedNames = new Set(removed.map((slot) => slot.name));
  const effects: TurnEffect[] = [];
  const seen = new Set<string>();
  const push = (slot: Slot, change: TurnEffect["change"]) => {
    if (seen.has(slot.name)) return;
    seen.add(slot.name);
    effects.push({ kind: slot.kind, name: slot.name, day: slot.day, stop: slot.stop, change });
  };

  for (const slot of added) push(slot, removedNames.has(slot.name) ? "moved" : "added");
  for (const slot of removed) push(slot, "removed");
  return effects.slice(0, MAX_EFFECTS);
}
