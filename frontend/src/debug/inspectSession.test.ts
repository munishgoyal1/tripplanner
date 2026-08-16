import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Read as text through Vite rather than node:fs: this is a browser project, so
// its tsconfig carries no Node types, and a path relative to the module beats
// one relative to whatever directory the runner happened to start in.
import mainSource from "../main.tsx?raw";

const USER_KEY = "tripplanner_user_id";
const GUEST_KEY = "tripplanner_guest_session";
const RESTORE_KEY = "tripplanner_inspect_restore";

async function load(enabled: boolean) {
  vi.stubEnv("VITE_DEBUG_TOOLS", enabled ? "1" : "");
  vi.resetModules();
  return import("./inspectSession");
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllEnvs());

describe("inspect deep link", () => {
  it("adopts the inspected identity so every pane shows that user's trip", async () => {
    const session = await load(true);
    localStorage.setItem(USER_KEY, "google-owner");
    localStorage.setItem(GUEST_KEY, "stale-token");

    const request = session.beginInspection("?inspect=corpus-hampi&trip=hampi_2027-01-05");

    expect(request).toEqual({ userId: "corpus-hampi", tripId: "hampi_2027-01-05" });
    expect(localStorage.getItem(USER_KEY)).toBe("corpus-hampi");
    expect(localStorage.getItem(GUEST_KEY)).toBeNull();
  });

  it("does nothing at all when debug tools are off", async () => {
    const session = await load(false);
    localStorage.setItem(USER_KEY, "google-owner");

    expect(session.beginInspection("?inspect=corpus-hampi")).toBeNull();
    expect(localStorage.getItem(USER_KEY)).toBe("google-owner");
    expect(session.inspectedUserId()).toBeNull();
  });

  it("returns to the owner's own workspace after several inspections", async () => {
    const session = await load(true);
    localStorage.setItem(USER_KEY, "google-owner");

    session.beginInspection("?inspect=corpus-hampi");
    session.beginInspection("?inspect=corpus-goa");
    expect(session.inspectedUserId()).toBe("corpus-goa");

    session.endInspection();

    expect(localStorage.getItem(USER_KEY)).toBe("google-owner");
    expect(localStorage.getItem(RESTORE_KEY)).toBeNull();
    expect(session.inspectedUserId()).toBeNull();
  });

  it("leaves a plain visit untouched", async () => {
    const session = await load(true);
    localStorage.setItem(USER_KEY, "google-owner");

    expect(session.beginInspection("?day=3")).toBeNull();
    expect(session.inspectedUserId()).toBeNull();
    expect(localStorage.getItem(USER_KEY)).toBe("google-owner");
  });

  it("reads a trip-less request, since a user id alone is enough to browse", async () => {
    const session = await load(true);

    expect(session.readInspectRequest("?inspect=corpus-hampi")).toEqual({
      userId: "corpus-hampi",
      tripId: null,
    });
  });
});

describe("inspecting a browser whose identity lives in a cookie", () => {
  it("still marks the session when localStorage holds no identity yet", async () => {
    // A Google session is mirrored into localStorage only after the first
    // render, so at this point there is usually nothing there to remember.
    const session = await load(true);

    session.beginInspection("?inspect=corpus-probe&trip=pondicherry_2026-11-07_2026-11-09");

    expect(session.inspectedUserId()).toBe("corpus-probe");
    expect(localStorage.getItem(RESTORE_KEY)).toBe("");
  });

  it("leaves no identity behind when there was none to begin with", async () => {
    const session = await load(true);
    session.beginInspection("?inspect=corpus-probe");

    session.endInspection();

    expect(localStorage.getItem(USER_KEY)).toBeNull();
    expect(session.inspectedUserId()).toBeNull();
  });

  it("marks the session even when the inspected id matches the current one", async () => {
    const session = await load(true);
    localStorage.setItem(USER_KEY, "corpus-probe");

    session.beginInspection("?inspect=corpus-probe");

    expect(session.inspectedUserId()).toBe("corpus-probe");
  });
});

describe("the app's entry point", () => {
  it("renders without waiting on the debug path", () => {
    // An earlier version awaited inspection before rendering, so one rejected
    // dynamic import left the whole SPA blank.
    const renderLine = mainSource
      .split("\n")
      .find((line: string) => line.includes("createRoot"));

    expect(renderLine).toBeDefined();
    // Top-level, so unindented and with nothing able to await it.
    expect(renderLine).toBe(renderLine!.trimStart());
    expect(mainSource).toMatch(/void runInspection\(\)/);
  });
});
