import type { TripView, DestinationOverview, MapView, MapsConfig, SavedTrip } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL || "/api";

// Stable per-browser identity so trip state + chat history follow the user
// across reloads. The backend keys conversation memory and trip storage by it.
export function getUserId(): string {
  const KEY = "multiagent_user_id";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = `web-${crypto.randomUUID()}`;
    localStorage.setItem(KEY, id);
  }
  return id;
}

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
  localStorage.setItem("multiagent_user_id", id);
  localStorage.setItem("multiagent_display_name", trimmed);
  return id;
}

export function signOut(): void {
  localStorage.removeItem("multiagent_user_id");
  localStorage.removeItem("multiagent_display_name");
}

export function getDisplayName(): string {
  return localStorage.getItem("multiagent_display_name") || "";
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
export async function syncAuth(): Promise<AuthSession> {
  try {
    const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
    const session: AuthSession = await res.json();
    if (session.authenticated && session.user_id) {
      localStorage.setItem("multiagent_user_id", session.user_id);
      if (session.display_name) {
        localStorage.setItem("multiagent_display_name", session.display_name);
      }
    }
    return session;
  } catch {
    return { authenticated: false };
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

export interface ToolEventExtras {
  args?: string;
  duration_ms?: number;
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onTool: (name: string, phase: "start" | "end", extras?: ToolEventExtras) => void;
  onDone: (reply: string) => void;
  onError: (message: string) => void;
}

// POST /chat/stream and parse the Server-Sent Events stream incrementally.
export async function streamChat(message: string, h: StreamHandlers): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, user_id: getUserId() }),
  });
  if (!res.body) {
    h.onError("No response stream from server.");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const ev = parseFrame(frame);
      if (!ev) continue;
      dispatch(ev.event, ev.data, h);
    }
  }
}

function parseFrame(frame: string): { event: string; data: any } | null {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return null;
  }
}

function dispatch(event: string, data: any, h: StreamHandlers): void {
  switch (event) {
    case "token":
      h.onToken(data.text ?? "");
      break;
    case "tool":
      h.onTool(data.name ?? "", data.phase ?? "start", {
        args: typeof data.args === "string" ? data.args : undefined,
        duration_ms: typeof data.duration_ms === "number" ? data.duration_ms : undefined,
      });
      break;
    case "done":
      h.onDone(data.reply ?? "");
      break;
    case "error":
      h.onError(data.message ?? "Unknown error.");
      break;
  }
}

export async function fetchTripView(focus?: {
  kind: string;
  name: string;
}): Promise<TripView> {
  const params = new URLSearchParams({ user_id: getUserId() });
  if (focus?.name) {
    params.set("focus_kind", focus.kind);
    params.set("focus_name", focus.name);
  }
  const res = await fetch(`${BASE}/trip/view?${params.toString()}`);
  return res.json();
}

export async function selectItem(kind: string, name: string): Promise<TripView> {
  const res = await fetch(`${BASE}/trip/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, name, user_id: getUserId() }),
  });
  const json = await res.json();
  return json.view as TripView;
}

export async function deselectItem(kind: string, name: string): Promise<TripView> {
  const res = await fetch(`${BASE}/trip/deselect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, name, user_id: getUserId() }),
  });
  const json = await res.json();
  return json.view as TripView;
}

/** List the user's saved trips (the "My trips" switcher). */
export async function fetchSavedTrips(): Promise<SavedTrip[]> {
  const params = new URLSearchParams({ user_id: getUserId() });
  const res = await fetch(`${BASE}/trips?${params.toString()}`);
  const json = await res.json();
  return (json.trips ?? []) as SavedTrip[];
}

/** Make a saved trip active (auto-saving whatever was active). */
export async function switchTrip(tripId: string): Promise<TripView | null> {
  const res = await fetch(`${BASE}/trips/switch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trip_id: tripId, user_id: getUserId() }),
  });
  const json = await res.json();
  return json.ok ? (json.view as TripView) : null;
}

/** Delete a saved trip; returns the refreshed saved-trips list. */
export async function deleteTrip(tripId: string): Promise<SavedTrip[]> {
  const res = await fetch(`${BASE}/trips/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trip_id: tripId, user_id: getUserId() }),
  });
  const json = await res.json();
  return (json.trips ?? []) as SavedTrip[];
}

/** Build the URL that downloads the active trip as an .ics calendar file. */
export function tripIcsUrl(): string {
  const params = new URLSearchParams({ user_id: getUserId() });
  return `${BASE}/trip/export.ics?${params.toString()}`;
}

/**
 * Mint a read-only share token for the active trip. Returns the absolute URL
 * (origin + path) that anyone can open without logging in. Throws on failure.
 */
export async function shareActiveTrip(): Promise<string> {
  const res = await fetch(`${BASE}/trip/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId(), kind: "share", name: "share" }),
  });
  const json = await res.json();
  if (json.error || !json.token) {
    throw new Error(json.error || "could not mint share link");
  }
  // The API returns a path; turn it into an absolute, copy-friendly URL.
  return `${window.location.origin}${json.url}`;
}

export interface Preferences {
  display_name: string;
  home_city: string;
  home_country: string;
  trip_style: string;
  budget_level: string;
  flight_class: string;
  prefer_direct_flights: boolean;
  hotel_star_rating_min: number;
  dietary: string[];
  interests: string[];
  dislikes: string[];
  about_me: string;
}

export async function fetchPreferences(): Promise<Preferences> {
  const params = new URLSearchParams({ user_id: getUserId() });
  const res = await fetch(`${BASE}/preferences?${params.toString()}`);
  return res.json();
}

export interface SavePrefsResult {
  ok: boolean;
  about_me_extracted: string[];
}

export async function savePreferences(prefs: Preferences): Promise<SavePrefsResult> {
  const res = await fetch(`${BASE}/preferences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...prefs, user_id: getUserId() }),
  });
  return res.json();
}

// ---------------------------------------------------------------------------
// Destination overview — module-level cache so flipping between trips (e.g.
// Dubai → Paris → Dubai) is instant after the first fetch and never shows an
// empty panel for places we've already loaded. The backend has its own 30-min
// Places cache; this avoids a network round-trip on top of that.
// ---------------------------------------------------------------------------
const OVERVIEW_TTL_MS = 30 * 60 * 1000;
interface OverviewEntry {
  at: number;
  data: DestinationOverview;
}
const overviewCache = new Map<string, OverviewEntry>();
const overviewInflight = new Map<string, Promise<DestinationOverview>>();

function overviewKey(destination: string | undefined, news: boolean): string {
  return `${(destination ?? "").toLowerCase().trim()}|${news ? 1 : 0}`;
}

export function getCachedOverview(
  destination?: string,
  news = true,
): DestinationOverview | null {
  const entry = overviewCache.get(overviewKey(destination, news));
  if (!entry) return null;
  if (Date.now() - entry.at > OVERVIEW_TTL_MS) return null;
  return entry.data;
}

export async function fetchDestinationOverview(
  destination?: string,
  news = true,
): Promise<DestinationOverview> {
  const key = overviewKey(destination, news);
  const fresh = getCachedOverview(destination, news);
  if (fresh) return fresh;
  const pending = overviewInflight.get(key);
  if (pending) return pending;

  const params = new URLSearchParams({ user_id: getUserId(), news: String(news) });
  if (destination) params.set("destination", destination);
  const req = fetch(`${BASE}/destination/overview?${params.toString()}`)
    .then((res) => res.json() as Promise<DestinationOverview>)
    .then((data) => {
      overviewCache.set(key, { at: Date.now(), data });
      overviewInflight.delete(key);
      return data;
    })
    .catch((err) => {
      overviewInflight.delete(key);
      throw err;
    });
  overviewInflight.set(key, req);
  return req;
}

// ---------------------------------------------------------------------------
// Interactive map. The browser Maps key is fetched once (it's static per
// deployment) and cached for the page lifetime. The map view-model is fetched
// on demand when the user opens the map panel.
// ---------------------------------------------------------------------------
let mapsConfigCache: MapsConfig | null = null;

export async function fetchMapsConfig(): Promise<MapsConfig> {
  if (mapsConfigCache) return mapsConfigCache;
  try {
    const res = await fetch(`${BASE}/maps/config`);
    mapsConfigCache = (await res.json()) as MapsConfig;
  } catch {
    mapsConfigCache = { enabled: false, key: "" };
  }
  return mapsConfigCache;
}

export async function fetchMapView(): Promise<MapView> {
  const params = new URLSearchParams({ user_id: getUserId() });
  const res = await fetch(`${BASE}/trip/map?${params.toString()}`);
  return res.json();
}
