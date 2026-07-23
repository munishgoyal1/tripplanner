import { describe, expect, it } from "vitest";
import { initialWorkspaceState, workspaceReducer } from "./workspaceState";

describe("workspaceReducer", () => {
  it("does not change trip revision for focus-only navigation", () => {
    const next = workspaceReducer(initialWorkspaceState, {
      type: "focus",
      place: { kind: "attraction", name: "Louvre Museum" },
    });

    expect(next.activePlace?.name).toBe("Louvre Museum");
    expect(next.tripRevision).toBe(0);
    expect(next.chatRevision).toBe(0);
  });

  it("advances only trip content revision for a mutation", () => {
    const next = workspaceReducer(initialWorkspaceState, { type: "trip-content-changed" });

    expect(next.tripRevision).toBe(1);
    expect(next.chatRevision).toBe(0);
  });

  it("clears place state and reloads all trip consumers on a switch", () => {
    const focused = {
      ...initialWorkspaceState,
      activePlace: { kind: "hotel", name: "Hotel Regina" },
      itineraryJump: { day: 2, name: "Louvre Museum", token: 1 },
    };
    const next = workspaceReducer(focused, { type: "trip-changed", tripId: "paris-1" });

    expect(next).toMatchObject({
      tripId: "paris-1",
      tripRevision: 1,
      chatRevision: 1,
      activePlace: null,
      itineraryJump: null,
    });
  });

  it("keeps the general transcript when the first trip is created", () => {
    const first = workspaceReducer(initialWorkspaceState, {
      type: "chat-trip-observed",
      tripId: "paris-1",
    });
    const switched = workspaceReducer(first, {
      type: "chat-trip-observed",
      tripId: "rome-1",
    });

    expect(first.chatRevision).toBe(0);
    expect(switched.chatRevision).toBe(1);
  });
});
