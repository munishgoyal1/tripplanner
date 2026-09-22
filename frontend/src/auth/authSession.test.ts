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
// The deployment's sign-in providers are probed once per page and cached, so a
// bad answer is not a transient glitch: it hides "Sign in with Google" until
// the user reloads. Only a real answer may be cached.
describe("fetchAuthConfig", () => {
  async function load() {
    vi.resetModules();
    return import("./authSession");
  }

  it("does not cache a failed probe, so the next caller re-asks", async () => {
    const { fetchAuthConfig } = await load();
    const fetchMock = vi
      .fn()
      // A JSON error body, as FastAPI returns: the old code cached this as the
      // deployment's answer, so the button stayed hidden until a reload.
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "service unavailable" }), { status: 503 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ google: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchAuthConfig()).toEqual({ google: false });
    expect(await fetchAuthConfig()).toMatchObject({ google: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("never reads an error payload as the answer", async () => {
    const { fetchAuthConfig } = await load();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "rate limited" }), { status: 429 }),
      ),
    );

    expect(await fetchAuthConfig()).toEqual({ google: false });
  });

  it("caches a real answer so each page probes once", async () => {
    const { fetchAuthConfig } = await load();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ google: true, redirect_uri: "/api/auth/callback/google" }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchAuthConfig()).toEqual({
      google: true,
      redirect_uri: "/api/auth/callback/google",
    });
    expect(await fetchAuthConfig()).toEqual({
      google: true,
      redirect_uri: "/api/auth/callback/google",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
