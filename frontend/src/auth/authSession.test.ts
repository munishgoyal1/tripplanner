import { beforeEach, describe, expect, it, vi } from "vitest";

import { getUserId, syncAuth } from "./authSession";

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("syncAuth", () => {
  it("replaces a stale Google identity when its session is no longer authenticated", async () => {
    localStorage.setItem("tripplanner_user_id", "google-owner");
    localStorage.setItem("tripplanner_display_name", "Owner");
    localStorage.setItem("tripplanner_guest_session", "stale-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ authenticated: false }), { status: 200 }),
      ),
    );
    const identityChanged = vi.fn();
    window.addEventListener("tripplanner:identity-changed", identityChanged);

    const session = await syncAuth();

    expect(session).toMatchObject({
      authenticated: false,
      prev_user_id: "google-owner",
      user_id: expect.stringMatching(/^web-/),
    });
    expect(getUserId()).toBe(session.user_id);
    expect(localStorage.getItem("tripplanner_display_name")).toBeNull();
    expect(localStorage.getItem("tripplanner_guest_session")).toBeNull();
    expect(identityChanged).toHaveBeenCalledOnce();
    window.removeEventListener("tripplanner:identity-changed", identityChanged);
  });

  it("keeps a Google identity when the auth check itself fails", async () => {
    localStorage.setItem("tripplanner_user_id", "google-owner");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })));

    expect(await syncAuth()).toEqual({ authenticated: false });
    expect(getUserId()).toBe("google-owner");
  });
});