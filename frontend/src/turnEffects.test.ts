import { describe, expect, it } from "vitest";
import { diffTurnEffects } from "./turnEffects";
import type { TripItem, TripView } from "./types";

function view(items: Partial<TripItem>[]): TripView {
  return {
    items: items.map((item) => ({
      kind: "attraction",
      name: "Place",
      selected: true,
      rating: null,
      review_count: null,
      address: "",
      summary: "",
      website: "",
      photos: [],
      reviews: [],
      occurrences: [],
      ...item,
    })),
  } as TripView;
}

describe("diffTurnEffects", () => {
  it("names stops a turn added", () => {
    const before = view([{ name: "Louvre", occurrences: [{ day: 1, stop: 1, time: "10:00" }] }]);
    const after = view([
      { name: "Louvre", occurrences: [{ day: 1, stop: 1, time: "10:00" }] },
      { name: "Orsay", kind: "attraction", occurrences: [{ day: 2, stop: 3, time: "11:00" }] },
    ]);

    expect(diffTurnEffects(before, after)).toEqual([
      { kind: "attraction", name: "Orsay", day: 2, stop: 3, change: "added" },
    ]);
  });

  it("reads a stop that changed slot as moved rather than removed and added", () => {
    const before = view([{ name: "Louvre", occurrences: [{ day: 1, stop: 1, time: "10:00" }] }]);
    const after = view([{ name: "Louvre", occurrences: [{ day: 3, stop: 2, time: "14:00" }] }]);

    expect(diffTurnEffects(before, after)).toEqual([
      { kind: "attraction", name: "Louvre", day: 3, stop: 2, change: "moved" },
    ]);
  });

  it("names stops a turn dropped", () => {
    const before = view([{ name: "Louvre", occurrences: [{ day: 1, stop: 1, time: "10:00" }] }]);

    expect(diffTurnEffects(before, view([]))).toEqual([
      { kind: "attraction", name: "Louvre", day: 1, stop: 1, change: "removed" },
    ]);
  });

  it("ignores unselected places and unchanged plans", () => {
    const before = view([
      { name: "Louvre", occurrences: [{ day: 1, stop: 1, time: "10:00" }] },
      { name: "Skipped", selected: false, occurrences: [{ day: 1, stop: 9, time: "18:00" }] },
    ]);
    const after = view([{ name: "Louvre", occurrences: [{ day: 1, stop: 1, time: "10:00" }] }]);

    expect(diffTurnEffects(before, after)).toEqual([]);
  });

  it("caps a full rebuild to a readable list", () => {
    const after = view(
      Array.from({ length: 9 }, (_, index) => ({
        name: `Stop ${index}`,
        occurrences: [{ day: 1, stop: index, time: "09:00" }],
      })),
    );

    expect(diffTurnEffects(null, after)).toHaveLength(6);
  });
});
