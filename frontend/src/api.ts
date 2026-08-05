import type { TripView, DestinationOverview, MapView, MapsConfig, PlannerReview, SavedTrip, Itinerary, PlaceGuidePage, TripWorkspaceView } from "./types";
import {
  type DeselectItemOptions,
  type SelectItemOptions,
  type SelectionPlacement,
  type TripInputRequest,
} from "@tripplanner/client";
import { BASE, apiFetch, getUserId, sharedClient } from "./auth/authSession";

export {
  fetchAuthConfig,
  fetchGuestDataSummary,
  getDisplayName,
  getUserId,
  isAnonymousUser,
  loginWithGoogle,
  logoutGoogle,
  migrateGuestData,
  signIn,
  signOut,
  syncAuth,
} from "./auth/authSession";
export type { AuthSession } from "./auth/authSession";

function ensureOk(response: Response, action: string): void {
  if (!response.ok) throw new Error(`${action} (${response.status}).`);
}

export interface ToolEventExtras {
  args?: string;
  duration_ms?: number;
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onTool: (name: string, phase: "start" | "end", extras?: ToolEventExtras) => void;
  onProgress?: (stage: "thinking" | "reviewing" | "saving") => void;
  onInputRequest?: (request: TripInputRequest) => void;
  onDone: (reply: string, tripId?: string) => void;
  onError: (message: string) => void;
}

// POST /chat/stream and parse the Server-Sent Events stream incrementally.
export async function streamChat(
  message: string,
  h: StreamHandlers,
  options: { proposalOnly?: boolean; requestId?: string; signal?: AbortSignal } = {},
): Promise<void> {
  const requestId = options.requestId ?? crypto.randomUUID();
  const res = await apiFetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      user_id: getUserId(),
      proposal_only: options.proposalOnly ?? false,
      request_id: requestId,
    }),
    signal: options.signal,
  });
  if (!res.ok) {
    let message = `Chat request failed (${res.status}).`;
    try {
      const data = (await res.json()) as { detail?: string; message?: string };
      message = data.message || data.detail || message;
    } catch {
      // Keep the status-based fallback for non-JSON responses.
    }
    throw new Error(message);
  }
  if (!res.body) {
    throw new Error("No response stream from server.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminalEvent = false;

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
      if (ev.event === "done" || ev.event === "error") terminalEvent = true;
      dispatch(ev.event, ev.data, h);
    }
  }
  const finalFrame = parseFrame(buffer);
  if (finalFrame) {
    if (finalFrame.event === "done" || finalFrame.event === "error") terminalEvent = true;
    dispatch(finalFrame.event, finalFrame.data, h);
  }
  if (!terminalEvent) {
    throw new Error("The response stream ended before the reply completed.");
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
    case "progress":
      if (["thinking", "reviewing", "saving"].includes(data.stage)) {
        h.onProgress?.(data.stage);
      }
      break;
    case "input_request":
      if (
        data.version === 1
        && typeof data.request_id === "string"
        && typeof data.question === "string"
        && Array.isArray(data.fields)
      ) {
        h.onInputRequest?.(data as TripInputRequest);
      }
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
  try {
    return await sharedClient.fetchChatHistory(tripId);
  } catch {
    return [];
  }
}

export async function fetchTripView(focus?: {
  kind: string;
  name: string;
  day?: number;
  stop?: number;
}, signal?: AbortSignal): Promise<TripView> {
  return sharedClient.fetchTripView(focus, signal);
}

export async function fetchPlaceGuide(
  opts: {
    city?: string;
    kind?: string;
    query?: string;
    cursor?: string | null;
    limit?: number;
    focus?: { kind: string; name: string } | null;
  } = {},
  signal?: AbortSignal,
): Promise<PlaceGuidePage> {
  return sharedClient.fetchPlaceGuide(opts, signal);
}

export type { DeselectItemOptions, SelectItemOptions, SelectionPlacement };

export async function selectItem(
  kind: string,
  name: string,
  options?: SelectItemOptions
): Promise<{ view: TripView; alerts: string[]; placement?: SelectionPlacement | null; placements?: SelectionPlacement[]; planner_review?: PlannerReview | null }> {
  return sharedClient.selectItem(kind, name, options);
}

export async function deselectItem(
  kind: string,
  name: string,
  options?: DeselectItemOptions,
): Promise<{ view: TripView; alerts: string[]; planner_review?: PlannerReview | null }> {
  return sharedClient.deselectItem(kind, name, options);
}

/** List the user's saved trips (the "My trips" switcher). */
export async function fetchSavedTrips(): Promise<SavedTrip[]> {
  return sharedClient.fetchSavedTrips();
}

/** Make a saved trip active (auto-saving whatever was active). Returns every
 * panel's view-model so the workspace swaps in one atomic update. */
export async function switchTrip(tripId: string): Promise<TripWorkspaceView | null> {
  return sharedClient.switchTrip(tripId);
}

/** Delete a saved trip; returns the refreshed saved-trips list. */
export async function deleteTrip(tripId: string): Promise<SavedTrip[]> {
  const res = await apiFetch(`${BASE}/trips/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trip_id: tripId, user_id: getUserId() }),
  });
  ensureOk(res, "Could not delete the trip");
  const json = await res.json();
  return (json.trips ?? []) as SavedTrip[];
}

/** Start a fresh planning chat: clear the active trip + general chat bucket. */
export async function startNewTrip(): Promise<void> {
  return sharedClient.startNewTrip();
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
    include_photos: options.include_photos ? "1" : "0",
    include_map_circuit: options.include_map_circuit ? "1" : "0",
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
  requestId: string,
): Promise<EmailExportResult> {
  const res = await apiFetch(`${BASE}/trip/export/email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: getUserId(),
      email,
      include_photos: options.include_photos,
      include_map_circuit: options.include_map_circuit,
      template: options.template,
      request_id: requestId,
    }),
  });
  const result = await res.json() as EmailExportResult;
  if (!res.ok && !result.error) throw new Error(`Could not email the itinerary (${res.status}).`);
  return result;
}

/**
 * Mint a read-only share token for the active trip. Returns the absolute URL
 * (origin + path) that anyone can open without logging in. Throws on failure.
 */
export async function shareActiveTrip(): Promise<string> {
  const res = await apiFetch(`${BASE}/trip/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId(), kind: "share", name: "share" }),
  });
  ensureOk(res, "Could not share the trip");
  const json = await res.json();
  if (json.error || !json.token) {
    throw new Error(json.error || "could not mint share link");
  }
  return String(json.url || "");
}

export async function importSharedTrip(token: string): Promise<TripView> {
  const res = await apiFetch(`${BASE}/trip/shared/${encodeURIComponent(token)}/import`, {
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
  const res = await apiFetch(`${BASE}/preferences?${params.toString()}`);
  ensureOk(res, "Could not load preferences");
  return res.json();
}

export interface SavePrefsResult {
  ok: boolean;
  about_me_extracted: string[];
  summary_conflict?: boolean;
}

export async function savePreferences(
  updates: Partial<Preferences>,
): Promise<SavePrefsResult> {
  const res = await apiFetch(`${BASE}/preferences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...updates, user_id: getUserId() }),
  });
  if (res.status === 409) {
    return { ok: false, about_me_extracted: [], summary_conflict: true };
  }
  ensureOk(res, "Could not save preferences");
  return res.json();
}

export async function regenerateProfileSummary(): Promise<{
  profile_summary: string;
  profile_summary_updated_at: string | null;
}> {
  const res = await apiFetch(`${BASE}/profile/summary/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "", name: "", user_id: getUserId() }),
  });
  ensureOk(res, "Could not regenerate the profile summary");
  const data = await res.json();
  return {
    profile_summary: (data && data.profile_summary) || "",
    profile_summary_updated_at: data?.profile_summary_updated_at ?? null,
  };
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
  const res = await apiFetch(`${BASE}/account/privacy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId(), action, confirm_text: confirmText }),
  });
  ensureOk(res, "Could not complete the privacy action");
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
  const req = apiFetch(`${BASE}/destination/overview?${params.toString()}`)
    .then((res) => {
      ensureOk(res, "Could not load destination details");
      return res.json() as Promise<DestinationOverview>;
    })
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

export async function fetchMapView(signal?: AbortSignal): Promise<MapView> {
  return sharedClient.fetchMapView(signal);
}

/** Structured day-by-day itinerary for the Itinerary tab. */
export async function fetchItinerary(signal?: AbortSignal): Promise<Itinerary> {
  return sharedClient.fetchItinerary(signal);
}

/** Toggle one itinerary stop's booked flag; returns the refreshed itinerary. */
export async function setStopBooked(
  day: number,
  name: string,
  booked: boolean
): Promise<Itinerary> {
  return sharedClient.setStopBooked(day, name, booked);
}

