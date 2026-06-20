import type { TripView, DestinationOverview, MapView, MapsConfig, SavedTrip, Itinerary } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL || "/api";

// Stable per-browser identity so trip state + chat history follow the user
// across reloads. The backend keys conversation memory and trip storage by it.
export function getUserId(): string {
  const KEY = "tripplanner_user_id";
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
  localStorage.setItem("tripplanner_user_id", id);
  localStorage.setItem("tripplanner_display_name", trimmed);
  return id;
}

export function signOut(): void {
  localStorage.removeItem("tripplanner_user_id");
  localStorage.removeItem("tripplanner_display_name");
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
// Returns both the session AND the guest_id that was active BEFORE the mirror
// (so callers can offer to migrate guest data when a sign-in just occurred).
export async function syncAuth(): Promise<AuthSession & { prev_guest_id?: string }> {
  try {
    const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
    const session: AuthSession = await res.json();
    if (session.authenticated && session.user_id) {
      const prevId = localStorage.getItem("tripplanner_user_id") ?? "";
      const guestId = prevId.startsWith("web-") ? prevId : undefined;
      localStorage.setItem("tripplanner_user_id", session.user_id);
      if (session.display_name) {
        localStorage.setItem("tripplanner_display_name", session.display_name);
      }
      return { ...session, prev_guest_id: guestId };
    }
    return session;
  } catch {
    return { authenticated: false };
  }
}

/** Ask the server how much data a guest (web-*) account has. */
export async function fetchGuestDataSummary(guestId: string): Promise<{ has_data: boolean; trip_count: number }> {
  try {
    const res = await fetch(`${BASE}/account/guest-data-summary?user_id=${encodeURIComponent(guestId)}`);
    return res.json();
  } catch {
    return { has_data: false, trip_count: 0 };
  }
}

/** Migrate trips and preferences from a guest identity into the authenticated account. */
export async function migrateGuestData(
  authUserId: string,
  guestId: string
): Promise<{ ok: boolean; copied_trips: number; copied_prefs: boolean }> {
  try {
    const res = await fetch(`${BASE}/account/migrate-guest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: authUserId, guest_id: guestId }),
    });
    return res.json();
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

export interface ToolEventExtras {
  args?: string;
  duration_ms?: number;
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onTool: (name: string, phase: "start" | "end", extras?: ToolEventExtras) => void;
  onDone: (reply: string, tripId?: string) => void;
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
      h.onDone(data.reply ?? "", typeof data.trip_id === "string" ? data.trip_id : undefined);
      break;
    case "error":
      h.onError(data.message ?? "Unknown error.");
      break;
  }
}

/** Restore the persisted transcript for a trip (or the current active trip). */
export async function fetchChatHistory(
  tripId?: string
): Promise<{ role: "user" | "assistant"; text: string }[]> {
  const params = new URLSearchParams({ user_id: getUserId() });
  if (tripId) params.set("trip_id", tripId);
  try {
    const res = await fetch(`${BASE}/chat/history?${params.toString()}`, {
      cache: "no-store",
    });
    const json = await res.json();
    return (json.messages ?? []) as { role: "user" | "assistant"; text: string }[];
  } catch {
    return [];
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

export interface SelectItemOptions {
  start_day?: number;
  end_day?: number;
  replace_stay?: boolean;
}

export interface SelectionPlacement {
  day: number;
  stop: number;
  name: string;
}

export async function selectItem(
  kind: string,
  name: string,
  options?: SelectItemOptions
): Promise<{ view: TripView; alerts: string[]; placement?: SelectionPlacement | null; placements?: SelectionPlacement[] }> {
  const res = await fetch(`${BASE}/trip/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, name, user_id: getUserId(), ...(options || {}) }),
  });
  const json = await res.json();
  return {
    view: json.view as TripView,
    alerts: (json.alerts ?? []) as string[],
    placement: (json.placement ?? null) as SelectionPlacement | null,
    placements: (json.placements ?? []) as SelectionPlacement[],
  };
}

export async function deselectItem(kind: string, name: string): Promise<{ view: TripView; alerts: string[] }> {
  const res = await fetch(`${BASE}/trip/deselect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, name, user_id: getUserId() }),
  });
  const json = await res.json();
  return { view: json.view as TripView, alerts: (json.alerts ?? []) as string[] };
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

/** Start a fresh planning chat: clear the active trip + general chat bucket. */
export async function startNewTrip(): Promise<void> {
  await fetch(`${BASE}/trip/new`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId() }),
  });
}

/** Build the URL that downloads the active trip as an .ics calendar file. */
export function tripIcsUrl(): string {
  const params = new URLSearchParams({ user_id: getUserId() });
  return `${BASE}/trip/export.ics?${params.toString()}`;
}

export interface ExportOptions {
  include_photos: boolean;
  include_map_circuit: boolean;
  template: "minimal" | "detailed" | "family";
}

export function tripExportUrl(options: ExportOptions, autoPrint = false): string {
  const params = new URLSearchParams({
    user_id: getUserId(),
    include_photos: options.include_photos ? "1" : "0",
    include_map_circuit: options.include_map_circuit ? "1" : "0",
    template: options.template,
    auto_print: autoPrint ? "1" : "0",
  });
  return `${BASE}/trip/export/print?${params.toString()}`;
}

export function tripExportPdfUrl(options: ExportOptions): string {
  const params = new URLSearchParams({
    user_id: getUserId(),
    template: options.template,
  });
  return `${BASE}/trip/export.pdf?${params.toString()}`;
}

export type PdfExportResult =
  | { ok: true; blob: Blob; filename: string }
  | { ok: false; error?: string; message: string };

export async function downloadTripPdf(options: ExportOptions): Promise<PdfExportResult> {
  const res = await fetch(tripExportPdfUrl(options));
  const contentType = res.headers.get("content-type") || "";
  if (res.ok && contentType.includes("application/pdf")) {
    const disposition = res.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    return {
      ok: true,
      blob: await res.blob(),
      filename: match?.[1] || "trip-itinerary.pdf",
    };
  }

  let error = "pdf_export_failed";
  let message = "Could not generate the PDF.";
  try {
    const data = (await res.json()) as { error?: string; message?: string };
    error = data.error || error;
    message = data.message || message;
  } catch {
    // Keep the generic fallback if the server responded with non-JSON text.
  }
  return { ok: false, error, message };
}

export interface EmailExportResult {
  ok: boolean;
  message?: string;
  error?: string;
  mailto?: string;
}

export async function emailTripExport(
  email: string,
  options: ExportOptions,
): Promise<EmailExportResult> {
  const res = await fetch(`${BASE}/trip/export/email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: getUserId(),
      email,
      include_photos: options.include_photos,
      include_map_circuit: options.include_map_circuit,
      template: options.template,
    }),
  });
  return res.json();
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
  return String(json.url || "");
}

export async function importSharedTrip(token: string): Promise<TripView> {
  const res = await fetch(`${BASE}/trip/shared/${encodeURIComponent(token)}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId() }),
  });
  const json = await res.json();
  if (!res.ok || json.error || !json.view) {
    throw new Error(json.error || "could not import shared trip");
  }
  return json.view as TripView;
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
  profile_summary: string;
  profile_summary_updated_at?: string | null;
  /** "direct" = jump straight to full plan (default); "interactive" = agent may ask questions first */
  planning_mode: "direct" | "interactive";
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

export async function regenerateProfileSummary(): Promise<string> {
  const res = await fetch(`${BASE}/profile/summary/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "", name: "", user_id: getUserId() }),
  });
  const data = await res.json();
  return (data && data.profile_summary) || "";
}

export type PrivacyAction = "delete_trip_history" | "clear_all_data" | "delete_account";

export interface PrivacyActionResult {
  ok: boolean;
  action: PrivacyAction;
  deleted_trips: number;
  deleted_chats: number;
  deleted_usage: number;
  deleted_cache: number;
  preferences_reset: boolean;
  message: string;
  error?: string;
}

export async function runPrivacyAction(
  action: PrivacyAction,
  confirmText = "",
): Promise<PrivacyActionResult> {
  const res = await fetch(`${BASE}/account/privacy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId(), action, confirm_text: confirmText }),
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

/** Structured day-by-day itinerary for the Itinerary tab. */
export async function fetchItinerary(): Promise<Itinerary> {
  const params = new URLSearchParams({ user_id: getUserId() });
  const res = await fetch(`${BASE}/trip/itinerary?${params.toString()}`);
  return res.json();
}

/** Toggle one itinerary stop's booked flag; returns the refreshed itinerary. */
export async function setStopBooked(
  day: number,
  name: string,
  booked: boolean
): Promise<Itinerary> {
  const res = await fetch(`${BASE}/trip/stop/booked`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ day, name, booked, user_id: getUserId() }),
  });
  const json = await res.json();
  return json.itinerary as Itinerary;
}

