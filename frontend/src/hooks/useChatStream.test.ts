import { describe, expect, it } from "vitest";
import { destinationFromToolArgs, progressHeading } from "./useChatStream";

describe("progress heading", () => {
  it("names the destination so a one-row composer still says where", () => {
    expect(progressHeading(false, "Goa")).toBe("Building your Goa itinerary");
    expect(progressHeading(true, "Paris")).toBe("Updating your Paris trip");
  });

  it("stays generic rather than naming a place it does not know", () => {
    expect(progressHeading(false, null)).toBe("Building your itinerary");
    expect(progressHeading(true, "  ")).toBe("Updating your trip");
  });
});

describe("destination from tool args", () => {
  it("reads the place the agent itself passed to the planning tool", () => {
    expect(
      destinationFromToolArgs("create_trip_plan", "destination=Goa, departure_date=2026-07-01"),
    ).toBe("Goa");
  });

  it("ignores tools that are not planning the trip", () => {
    expect(destinationFromToolArgs("search_hotels", "destination=Goa")).toBeNull();
  });

  it("refuses a truncated or empty value rather than showing a fragment", () => {
    expect(destinationFromToolArgs("create_trip_plan", "origin=Bangalore")).toBeNull();
    expect(destinationFromToolArgs("update_trip_plan", "destination=None")).toBeNull();
  });
});
