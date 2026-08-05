import { beforeEach, describe, expect, it } from "vitest";
import { saveTurnMeta, withStoredTurnMeta } from "./turnMetadata";
import type { ChatMessage } from "./types";

const transcript: ChatMessage[] = [
  { role: "user", text: "Move the Louvre to day 3" },
  {
    role: "assistant",
    text: "Moved it.",
    ts: 1_700_000_000_000,
    seconds: 42,
    effects: [{ kind: "attraction", name: "Louvre", day: 3, stop: 1, change: "moved" }],
  },
];

describe("turnMetadata", () => {
  beforeEach(() => localStorage.clear());

  it("restores timing and stop links onto a server transcript", () => {
    saveTurnMeta("trip-1", transcript);

    const restored = withStoredTurnMeta(
      "trip-1",
      transcript.map((message) => ({ role: message.role, text: message.text })),
    );

    expect(restored[1].seconds).toBe(42);
    expect(restored[1].ts).toBe(1_700_000_000_000);
    expect(restored[1].effects).toEqual(transcript[1].effects);
  });

  it("keeps each trip's turns separate", () => {
    saveTurnMeta("trip-1", transcript);

    const restored = withStoredTurnMeta(
      "trip-2",
      transcript.map((message) => ({ role: message.role, text: message.text })),
    );

    expect(restored[1].seconds).toBeUndefined();
  });

  it("does not attach timing to a turn whose text changed", () => {
    saveTurnMeta("trip-1", transcript);

    const restored = withStoredTurnMeta("trip-1", [
      { role: "user", text: "Move the Louvre to day 3" },
      { role: "assistant", text: "Something else entirely." },
    ]);

    expect(restored[1].seconds).toBeUndefined();
  });

  it("survives unreadable storage", () => {
    localStorage.setItem("tripplanner_turn_meta_v1", "{not json");

    expect(withStoredTurnMeta("trip-1", transcript)).toEqual(transcript);
  });
});
