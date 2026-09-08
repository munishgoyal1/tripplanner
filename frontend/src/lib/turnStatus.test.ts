import { describe, expect, it } from "vitest";
import { answerGist, changeSummary, completionStatus, requestEcho } from "./turnStatus";
import type { TurnEffect } from "../types";

const stop = (name: string, change: TurnEffect["change"], day = 1): TurnEffect => ({
  kind: "attraction",
  name,
  day,
  stop: 0,
  change,
});

describe("request echo", () => {
  it("quotes the user's own words for a composer that no longer shows them", () => {
    expect(requestEcho("what is total estimated time on road")).toBe(
      "\u201cwhat is total estimated time on road\u201d",
    );
  });

  it("cuts at a word boundary instead of mid-word", () => {
    expect(requestEcho("plan a five day trip to Madhya Pradesh in December", 20)).toBe(
      "\u201cplan a five day\u2026\u201d",
    );
  });

  it("says nothing when there is nothing to echo", () => {
    expect(requestEcho("   ")).toBe("");
  });
});

describe("answer gist", () => {
  it("carries the answer the collapsed chat is hiding", () => {
    expect(
      answerGist("Here's the total estimated time on road: **~20 hours 28 minutes**. Let me know."),
    ).toBe("Here's the total estimated time on road: ~20 hours 28 minutes.");
  });

  it("drops list markers and code blocks", () => {
    expect(answerGist("```json\n{}\n```\n- Indore to Ujjain: 3h 30m")).toBe(
      "Indore to Ujjain: 3h 30m",
    );
  });
});

describe("change summary", () => {
  it("names a single change", () => {
    expect(changeSummary([stop("Sayaji Indore", "added", 2)])).toBe("Added Sayaji Indore on Day 2.");
    expect(changeSummary([stop("Kaanch Mandir", "moved", 4)])).toBe(
      "Moved Kaanch Mandir to Day 4.",
    );
  });

  it("counts a bulk change instead of listing everything", () => {
    expect(
      changeSummary([stop("A", "added"), stop("B", "added"), stop("C", "removed")]),
    ).toBe("Added 2 stops and removed 1.");
  });
});

describe("completion status", () => {
  const base = {
    destination: "Madhya Pradesh",
    startedWithoutTrip: false,
    proposalOnly: false,
    effects: [] as TurnEffect[],
    reply: "",
  };

  it("does not report an update for a question that changed nothing", () => {
    const status = completionStatus({
      ...base,
      reply: "Total estimated road time is about 20 hours 28 minutes.",
    });
    expect(status.message).toBe("Answered in chat \u2014 nothing changed");
    expect(status.detail).toBe("Total estimated road time is about 20 hours 28 minutes.");
  });

  it("reports what actually moved when the plan changed", () => {
    const status = completionStatus({
      ...base,
      effects: [stop("Essentia Luxury Hotel Indore", "added", 1)],
      alert: "Day 3 was packed, so I moved Kaanch Mandir to Day 4.",
    });
    expect(status.message).toBe("Updated your Madhya Pradesh trip");
    expect(status.detail).toBe(
      "Added Essentia Luxury Hotel Indore on Day 1. Day 3 was packed, so I moved Kaanch Mandir to Day 4.",
    );
  });

  it("announces a first build by name", () => {
    const status = completionStatus({ ...base, destination: "Goa", startedWithoutTrip: true });
    expect(status.message).toBe("Your Goa itinerary is ready");
  });

  it("keeps a review honest about having changed nothing", () => {
    expect(completionStatus({ ...base, proposalOnly: true }).message).toBe(
      "Review ready \u2014 nothing changed yet",
    );
  });
});
