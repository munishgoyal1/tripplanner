import { describe, expect, it } from "vitest";

import { exactItineraryOccurrence } from "../../mobile/lib/itinerary-occurrence";
import { LatestRequestGate } from "../../mobile/lib/latest-request";

describe("native itinerary occurrence contract", () => {
  it("converts repeated itinerary rows to distinct one-based occurrences", () => {
    expect(exactItineraryOccurrence(2, 0)).toEqual({
      day: 2,
      stop: 1,
    });
    expect(exactItineraryOccurrence(2, 2)).toEqual({
      day: 2,
      stop: 3,
    });
  });
});

describe("native refresh request gate", () => {
  it("aborts and invalidates superseded refreshes", () => {
    const gate = new LatestRequestGate();
    const first = gate.start();
    const second = gate.start();

    expect(first.signal.aborted).toBe(true);
    expect(first.isCurrent()).toBe(false);
    expect(second.signal.aborted).toBe(false);
    expect(second.isCurrent()).toBe(true);

    gate.abort();
    expect(second.signal.aborted).toBe(true);
    expect(second.isCurrent()).toBe(false);
  });
});