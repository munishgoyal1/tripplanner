import { describe, expect, it } from "vitest";
import { kindForGooglePlace, optionsForStopDay, placeNameMatches } from "./MapPanel";

describe("placeNameMatches", () => {
  it("matches exact and canonicalized restaurant names", () => {
    expect(placeNameMatches("Peter Cat", "Peter Cat")).toBe(true);
    expect(placeNameMatches("Peter Cat Restaurant, Park Street", "Peter Cat")).toBe(true);
    expect(placeNameMatches("Peter Cat", "Peter Cat Kolkata")).toBe(true);
  });

  it("does not match unrelated restaurants or empty names", () => {
    expect(placeNameMatches("Peter Cat", "Mocambo")).toBe(false);
    expect(placeNameMatches("", "Peter Cat")).toBe(false);
  });
});

describe("map stop selection", () => {
  it("infers hotel stops from Google place types", () => {
    expect(kindForGooglePlace(["lodging", "point_of_interest"])).toBe("hotel");
    expect(kindForGooglePlace(["restaurant", "food"])).toBe("meal");
    expect(kindForGooglePlace(["museum", "tourist_attraction"])).toBe("attraction");
    expect(kindForGooglePlace(undefined)).toBe("attraction");
  });

  it("passes an explicit day only when selected", () => {
    expect(optionsForStopDay("auto")).toBeUndefined();
    expect(optionsForStopDay("2")).toEqual({ day: 2 });
    expect(optionsForStopDay("0")).toBeUndefined();
  });
});
