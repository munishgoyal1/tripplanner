// Auth + session identity for the web app. Owns per-browser identity, guest
// session tokens, the authenticated `apiFetch`, the shared API client, and the
// Google OAuth / guest-migration surface. Split out of `api.ts` (tech-debt #9);
// `api.ts` re-exports the public names so existing import sites resolve
// unchanged. Behavior is preserved exactly — no cache TTL or other changes.

import { TripplannerClient } from "@tripplanner/client";

export const BASE = import.meta.env.VITE_API_BASE_URL || "/api";
const GUEST_SESSION_KEY = "tripplanner_guest_session";
let guestSessionRequest: Promise<string | null> | null = null;

// Stable per-browser identity so trip state + chat history follow the user
// across reloads. The backend keys conversation memory and trip storage by it.
export function getUserId(): string {
  const KEY = "tripplanner_user_id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    // In local/emulator dev, VITE_DEV_GUEST_ID pins a stable guest identity that
    // the sandbox seed populates, so guest-mode testing opens with real data.
    const devGuest = import.meta.env.VITE_DEV_GUEST_ID as string | undefined;
    id = devGuest && devGuest.startsWith("web-") ? devGuest : `web-${crypto.randomUUID()}`;
    localStorage.setItem(KEY, id);
  }
  return id;
}

export async function getApiSessionToken(): Promise<string | null> {
  const userId = getUserId();
  if (!userId.startsWith("web-")) return null;
  const existing = localStorage.getItem(GUEST_SESSION_KEY);
  if (existing) return existing;
  if (!guestSessionRequest) {
    guestSessionRequest = fetch(`${BASE}/auth/guest/session`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const body = await response.json() as { token?: string };
        if (body.token) localStorage.setItem(GUEST_SESSION_KEY, body.token);
        return body.token || null;
      })
      .finally(() => { guestSessionRequest = null; });
  }
  return guestSessionRequest;
}

// While inspecting, the browser still carries the owner's session cookie, and a
// session outranks any claimed user_id -- so without this header every request
// would quietly return the owner's own workspace. Keys mirror debug/inspectSession;
// read inline so an unset flag leaves no reference to that module in the bundle.
function inspectedUser(): string | null {
  if (import.meta.env.VITE_DEBUG_TOOLS !== "1") return null;
  if (localStorage.getItem("tripplanner_inspect_restore") === null) return null;
  return localStorage.getItem("tripplanner_user_id");
}

function inspectHeaders(): Record<string, string> {
  const inspected = inspectedUser();
  return inspected ? { "X-Inspect-User": inspected } : {};
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await getApiSessionToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  for (const [name, value] of Object.entries(inspectHeaders())) headers.set(name, value);
  return fetch(input, { ...init, credentials: "include", headers });
}

export const sharedClient = new TripplannerClient(
  BASE,
  getUserId,
  getApiSessionToken,
  inspectHeaders,
);

// Whether the current identity is the anonymous, per-browser one (vs. a name
// the user explicitly signed in with). Used to show "Sign in" vs the name.
export function isAnonymousUser(): boolean {
  return getUserId().startsWith("web-");
}

// Sign in by claiming a stable identity. The same name on another device
// resolves to the same id, so preferences and trips follow the user. Passing
// "local" shares state with the CLI for convenient local testing.
export function signIn(name: string): string {
  const trimmed = name.trim();
  const id =
    trimmed.toLowerCase() === "local"
      ? "local"
      : `user-${trimmed.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")}`;
  localStorage.setItem("tripplanner_user_id", id);
  localStorage.setItem("tripplanner_display_name", trimmed);
  return id;
}

export function signOut(): void {
  localStorage.removeItem("tripplanner_user_id");
  localStorage.removeItem("tripplanner_display_name");
  localStorage.removeItem(GUEST_SESSION_KEY);
}

export function getDisplayName(): string {
  return localStorage.getItem("tripplanner_display_name") || "";
}

// ---------------------------------------------------------------------------
// Google OAuth. The backend owns the redirect dance and drops a signed,
// HttpOnly session cookie; here we just (a) ask whether it's configured,
// (b) read the current session, and (c) kick off / tear down login. When a
// Google session exists we mirror its user_id into localStorage so every
// existing param-based call (chat, trip, preferences) uses the Google identity
// — the `google-<sub>` id is stable across devices.
// ---------------------------------------------------------------------------
export interface AuthSession {
  authenticated: boolean;
  user_id?: string;
  display_name?: string;
  email?: string;
  picture?: string;
}

export async function fetchAuthConfig(): Promise<{ google: boolean; redirect_uri?: string }> {
  try {
    const res = await fetch(`${BASE}/auth/config`);
    return res.json();
  } catch {
    return { google: false };
  }
}

// Reads the session cookie. If authenticated, mirrors the identity into
// localStorage so the rest of the app picks it up transparently.
// Returns both the session and the identity that was active BEFORE the mirror
// (so callers can offer to migrate guest data or reset stale UI state when a
// sign-in just occurred).
export async function syncAuth(): Promise<AuthSession & { prev_guest_id?: string; prev_user_id?: string }> {
  try {
    const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
    const session: AuthSession = await res.json();
    if (session.authenticated && session.user_id) {
      const prevId = localStorage.getItem("tripplanner_user_id") ?? "";
      const guestId = prevId.startsWith("web-") ? prevId : undefined;
      // This runs after the first render, so mirroring unconditionally would
      // overwrite an inspected identity and silently restore the owner's own
      // workspace a moment after the inspected trip had loaded.
      if (!inspectedUser()) {
        localStorage.setItem("tripplanner_user_id", session.user_id);
      }
      if (session.display_name) {
        localStorage.setItem("tripplanner_display_name", session.display_name);
      }
      return { ...session, prev_guest_id: guestId, prev_user_id: prevId || undefined };
    }
    return session;
  } catch {
    return { authenticated: false };
  }
}

/** Ask the server how much data a guest (web-*) account has. */
export async function fetchGuestDataSummary(guestId: string): Promise<{
  has_data: boolean;
  trip_count: number;
  has_preferences?: boolean;
}> {
  try {
    const token = localStorage.getItem(GUEST_SESSION_KEY);
    const res = await fetch(`${BASE}/account/guest-data-summary?user_id=${encodeURIComponent(guestId)}`, {
      credentials: "include",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return res.json();
  } catch {
    return { has_data: false, trip_count: 0, has_preferences: false };
  }
}

/** Migrate trips and preferences from a guest identity into the authenticated account. */
export async function migrateGuestData(
  authUserId: string,
  guestId: string
): Promise<{ ok: boolean; copied_trips: number; copied_prefs: boolean }> {
  try {
    const token = localStorage.getItem(GUEST_SESSION_KEY);
    const res = await fetch(`${BASE}/account/migrate-guest`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ user_id: authUserId, guest_id: guestId }),
    });
    const result = await res.json();
    if (result.ok) localStorage.removeItem(GUEST_SESSION_KEY);
    return result;
  } catch {
    return { ok: false, copied_trips: 0, copied_prefs: false };
  }
}

export function loginWithGoogle(): void {
  const back = window.location.pathname + window.location.search;
  window.location.href = `${BASE}/auth/login/google?redirect=${encodeURIComponent(back)}`;
}

export async function logoutGoogle(): Promise<void> {
  try {
    await fetch(`${BASE}/auth/logout`, { method: "POST", credentials: "include" });
  } catch {
    /* ignore */
  }
  signOut();
}
