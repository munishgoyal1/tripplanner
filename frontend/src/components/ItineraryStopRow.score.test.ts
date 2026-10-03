// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { ItineraryStop } from "../types";
import { mustVisitScore } from "./ItineraryStopRow";

function stop(kind: string, popularity_score?: number): ItineraryStop {
  return { name: "Place", kind, popularity_score } as ItineraryStop;
}

describe("mustVisitScore", () => {
  it("bands the 0-100 score on a ten-point scale", () => {
    expect(mustVisitScore(stop("attraction", 95))).toMatchObject({ value: 9.5, band: "Must visit" });
    expect(mustVisitScore(stop("attraction", 90))).toMatchObject({ value: 9, band: "Must visit" });
    expect(mustVisitScore(stop("meal", 82))).toMatchObject({ value: 8.2, band: "Good to visit" });
    expect(mustVisitScore(stop("attraction", 61))).toMatchObject({ value: 6.1, band: "May visit" });
    expect(mustVisitScore(stop("attraction", 44))).toMatchObject({ value: 4.4, band: "Optional" });
  });

  it("scores places to visit, not hotels, journeys or unrated stops", () => {
    expect(mustVisitScore(stop("hotel", 95))).toBeNull();
    expect(mustVisitScore(stop("airport", 95))).toBeNull();
    expect(mustVisitScore(stop("attraction"))).toBeNull();
  });
});
