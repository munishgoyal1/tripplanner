import { describe, expect, it } from "vitest";
import {
  destinationFromToolArgs,
  destinationFromUserMessage,
  isPlanEditTool,
  progressHeading,
  stageTrail,
  waitHint,
} from "./useChatStream";

describe("stage trail", () => {
  it("reads as an accumulating trail with the live stage last", () => {
    expect(stageTrail(["your preferences", "travel", "stays"])).toBe(
      "your preferences \u2192 travel \u2192 stays",
    );
  });

  it("keeps a long build to one line by eliding the earliest stages", () => {
    expect(
      stageTrail(["your preferences", "travel", "stays", "places", "the itinerary"]),
    ).toBe("\u2026 \u2192 travel \u2192 stays \u2192 places \u2192 the itinerary");
  });

  it("says nothing before any stage has run", () => {
    expect(stageTrail([])).toBe("");
  });
});

describe("wait hint", () => {
  it("sets the expectation once, then leaves the clock to speak", () => {
    expect(waitHint(true, 0)).toBe("full builds take about 2\u20134 minutes");
    expect(waitHint(true, 60)).toBe("");
    expect(waitHint(true, 130)).toBe("still working, no need to refresh");
  });
});

describe("progress heading", () => {
  it("names the destination so a one-row composer still says where", () => {
    expect(progressHeading(false, "Goa")).toBe("Building your Goa itinerary");
    expect(progressHeading(true, "Paris", true)).toBe("Updating your Paris trip");
  });

  it("does not claim an update before the Assistant has edited anything", () => {
    expect(progressHeading(true, "Madhya Pradesh")).toBe("Working on your Madhya Pradesh trip");
  });

  it("stays generic rather than naming a place it does not know", () => {
    expect(progressHeading(false, null)).toBe("Building your itinerary");
    expect(progressHeading(true, "  ", true)).toBe("Updating your trip");
  });
});

describe("plan edit tools", () => {
  it("separates writing the plan from looking things up", () => {
    expect(isPlanEditTool("update_trip_plan")).toBe(true);
    expect(isPlanEditTool("add_selection")).toBe(true);
    expect(isPlanEditTool("search_hotels")).toBe(false);
    expect(isPlanEditTool("get_place_reviews")).toBe(false);
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

describe("destination from user message", () => {
  it("extracts destination from 'plan a [place] trip' phrasing", () => {
    expect(destinationFromUserMessage("plan a China trip")).toBe("China");
    expect(destinationFromUserMessage("can you plan a Japan trip for me?")).toBe("Japan");
  });

  it("handles 'trip to [place]' phrasing", () => {
    expect(destinationFromUserMessage("I want a trip to Paris")).toBe("Paris");
    expect(destinationFromUserMessage("planning a trip to New York in August")).toBe("New York");
  });

  it("handles 'travel to [place]' and 'visit [place]' phrasing", () => {
    expect(destinationFromUserMessage("I'd like to travel to Thailand")).toBe("Thailand");
    expect(destinationFromUserMessage("want to visit Barcelona")).toBe("Barcelona");
  });

  it("handles '[place] trip' phrasing", () => {
    expect(destinationFromUserMessage("Plan my Bali trip")).toBe("Bali");
    expect(destinationFromUserMessage("Tokyo trip next month?")).toBe("Tokyo");
  });

  it("rejects messages without trip-planning keywords", () => {
    expect(destinationFromUserMessage("what's the weather in London?")).toBeNull();
    expect(destinationFromUserMessage("add a restaurant in Rome")).toBeNull();
  });

  it("rejects invalid or missing destinations", () => {
    expect(destinationFromUserMessage("plan a trip")).toBeNull();
    expect(destinationFromUserMessage("trip to a")).toBeNull();
  });

  it("rejects very long messages to avoid false positives", () => {
    const longMsg = "plan a " + "x".repeat(500);
    expect(destinationFromUserMessage(longMsg)).toBeNull();
  });
});
