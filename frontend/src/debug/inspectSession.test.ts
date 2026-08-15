import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
