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

  it("restores turns saved while the greeting still led the transcript", () => {
    const greeting: ChatMessage = { role: "assistant", text: "Where are you traveling from?" };
    saveTurnMeta("trip-1", [greeting, ...transcript]);

    const restored = withStoredTurnMeta(
      "trip-1",
      transcript.map((message) => ({ role: message.role, text: message.text })),
    );

    expect(restored[1].seconds).toBe(42);
    expect(restored[1].ts).toBe(1_700_000_000_000);
  });

  it("carries pre-trip turns into the trip they created", () => {
    saveTurnMeta("__active__", transcript);

    const restored = withStoredTurnMeta(
      "trip-new",
      transcript.map((message) => ({ role: message.role, text: message.text })),
    );

    expect(restored[1].seconds).toBe(42);
  });

  it("keeps a trip's own timing once it has some", () => {
    saveTurnMeta("__active__", transcript);
    saveTurnMeta("trip-1", [
      { role: "user", text: "Only turn" },
      { role: "assistant", text: "Only reply", ts: 5, seconds: 7 },
    ]);

    const restored = withStoredTurnMeta(
      "trip-1",
      transcript.map((message) => ({ role: message.role, text: message.text })),
    );

    expect(restored[1].seconds).toBeUndefined();
  });

  it("keeps stored timing when a failed reload leaves only the greeting", () => {
    saveTurnMeta("trip-1", transcript);

    saveTurnMeta("trip-1", [{ role: "assistant", text: "Where are you traveling from?" }]);

    const restored = withStoredTurnMeta(
      "trip-1",
      transcript.map((message) => ({ role: message.role, text: message.text })),
    );

    expect(restored[1].seconds).toBe(42);
  });

  it("separates repeated identical turns", () => {
    saveTurnMeta("trip-1", [
      { role: "user", text: "Again" },
      { role: "assistant", text: "Done.", ts: 1, seconds: 10 },
      { role: "user", text: "Again" },
      { role: "assistant", text: "Done.", ts: 2, seconds: 20 },
    ]);

    const restored = withStoredTurnMeta("trip-1", [
      { role: "user", text: "Again" },
      { role: "assistant", text: "Done." },
      { role: "user", text: "Again" },
      { role: "assistant", text: "Done." },
    ]);

    expect(restored[1].seconds).toBe(10);
    expect(restored[3].seconds).toBe(20);
  });
});
