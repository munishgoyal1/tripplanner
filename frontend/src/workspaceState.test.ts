import { describe, expect, it } from "vitest";
import { initialWorkspaceState, workspaceReducer } from "./workspaceState";

describe("workspaceReducer", () => {
  it("does not change trip revision for focus-only navigation", () => {
    const next = workspaceReducer(initialWorkspaceState, {
      type: "focus",
      focus: {
        type: "place",
        place: { kind: "attraction", name: "Louvre Museum" },
        token: 1,
      },
    });

    expect(next.focus).toMatchObject({ type: "place", place: { name: "Louvre Museum" } });
    expect(next.tripRevision).toBe(0);
    expect(next.chatRevision).toBe(0);
  });

  it("clears a stale itinerary jump when exact focus changes", () => {
    const state = {
      ...initialWorkspaceState,
      itineraryJump: { day: 1, name: "Louvre Museum", token: 1 },
    };
    const next = workspaceReducer(state, {
      type: "focus",
      focus: {
        type: "place",
        place: { kind: "attraction", name: "Seine cruise", day: 1, stop: 2 },
        token: 2,
      },
    });

    expect(next.itineraryJump).toBeNull();
    expect(next.focus).toMatchObject({ type: "place", place: { name: "Seine cruise" } });
  });

  it("advances only trip content revision for a mutation", () => {
    const next = workspaceReducer(initialWorkspaceState, { type: "trip-content-changed" });

    expect(next.tripRevision).toBe(1);
    expect(next.chatRevision).toBe(0);
  });

  it("clears focus state and reloads all trip consumers on a switch", () => {
    const focused = {
      ...initialWorkspaceState,
      focus: { type: "circuit" as const, day: 2, token: 1 },
      itineraryJump: { day: 2, name: "Louvre Museum", token: 1 },
    };
    const next = workspaceReducer(focused, { type: "trip-changed", tripId: "paris-1" });

    expect(next).toMatchObject({
      tripId: "paris-1",
      tripRevision: 1,
      chatRevision: 1,
      focus: { type: "none" },
      itineraryJump: null,
    });
  });

  it("keeps the general transcript when the first trip is created", () => {
    const focused = {
      ...initialWorkspaceState,
      focus: {
        type: "place" as const,
        place: { kind: "attraction", name: "Louvre Museum" },
        token: 1,
      },
      itineraryJump: { day: 2, name: "Louvre Museum", token: 1 },
    };
    const first = workspaceReducer(focused, {
      type: "chat-trip-observed",
      tripId: "paris-1",
    });
    const switched = workspaceReducer(first, {
      type: "chat-trip-observed",
      tripId: "rome-1",
    });

    expect(first.chatRevision).toBe(0);
    expect(first.focus).toEqual({ type: "none" });
    expect(first.itineraryJump).toBeNull();
    expect(switched.chatRevision).toBe(1);
  });
});
