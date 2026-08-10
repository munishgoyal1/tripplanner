import type { TripView, DecisionApplyResult, DestinationOverview, MapView, MapsConfig, PlannerReview, Receipt, SavedTrip, Itinerary, PlaceGuidePage, TripWorkspaceView } from "./types";
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

export interface OpsMetricRow {
  calls: number;
  errors: number;
  p50_ms: number;
  p95_ms: number;
  p90_ms?: number;
}

export interface OpsOverview {
  generated_at: string;
  uptime_seconds: number;
  business: {
    new_trips: Record<"today" | "7d" | "30d", number>;
    active_trips: Record<"today" | "7d" | "30d", number>;
    chat_requests: number;
    iterations: number;
    inventory: {
      trips: number;
      flights: number;
      hotels: number;
      activities: number;
    };
  };
  product: {
    events: number;
    sessions: number;
    users: number;
    engagement_seconds: number;
    activities: Record<string, number>;
    funnel: Record<"page_view" | "planning_started" | "trip_created" | "planning_completed", number>;
    drop_offs: Record<string, number>;
    countries: Record<string, number>;
    sources: Record<string, number>;
  };
  chat_turns: {
    calls: number;
    completed: number;
    errors: number;
    distinct_users: number;
    p50_ms: number;
    p95_ms: number;
    tool_calls: number;
    avg_tools_per_turn: number;
    outcomes: Record<string, number>;
  };
  requests: OpsMetricRow & {
    by_route: Record<string, OpsMetricRow>;
    error_statuses: Record<string, number>;
  };
  models: OpsMetricRow & {
    recent: Array<{ model: string; status: string; duration_ms: number; at: number }>;
  };
  usage: {
    month: string;
    model_calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost_usd: number;
  };
  tools: Record<string, OpsMetricRow & {
    cache_hits: number;
    hit_rate: number;
    avg_ms: number;
    error_types: Record<string, number>;
  }>;
  providers: Record<string, {
    calls: number;
    successes: number;
    failures: number;
    failure_rate: number;
    avg_ms: number;
  }>;
  cache: {
    configured: boolean;
    backend: "redis" | "memory";
    redis_connected: boolean;
    fallback_active: boolean;
    memory_entries: number;
    redis_entries: number;
    redis_bytes: number;
    redis_stats_truncated: boolean;
  };
}

export async function fetchOpsOverview(signal?: AbortSignal): Promise<OpsOverview> {
  const response = await apiFetch(`${BASE}/ops/overview`, { signal });
  ensureOk(response, "Operations overview unavailable");
  return response.json() as Promise<OpsOverview>;
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onTool: (name: string, phase: "start" | "end", extras?: ToolEventExtras) => void;
  onProgress?: (stage: "thinking" | "reviewing" | "saving") => void;
  onReceipt?: (receipt: Receipt) => void;
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
    case "receipt":
      if (typeof data.text === "string" && data.text) {
        h.onReceipt?.({
          seq: typeof data.seq === "number" ? data.seq : 0,
          at: typeof data.at === "string" ? data.at : "",
          kind: typeof data.kind === "string" ? data.kind : "",
          text: data.text,
          detail: typeof data.detail === "string" ? data.detail : undefined,
          decision_id: typeof data.decision_id === "string" ? data.decision_id : undefined,
          source: typeof data.source === "string" ? data.source : undefined,
        });
      }
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

/** Take a different option on a recorded comparison. */
export async function overrideDecision(
  decisionId: string,
  optionId: string,
  updatedAt?: string | null,
): Promise<DecisionApplyResult> {
  return sharedClient.overrideDecision(decisionId, optionId, updatedAt);
}

/** Put the agent's own choice back. */
export async function restoreDecision(
  decisionId: string,
  updatedAt?: string | null,
): Promise<DecisionApplyResult> {
  return sharedClient.restoreDecision(decisionId, updatedAt);
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

/** Empty the active trip's plan but keep its destination, dates and people.
 * Returns every panel's view-model so the workspace swaps in one update. */
export async function resetTrip(): Promise<TripWorkspaceView | null> {
  const res = await apiFetch(`${BASE}/trip/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId() }),
  });
  ensureOk(res, "Could not reset the trip");
  const json = await res.json();
  if (!json.ok || !json.view) return null;
  return { view: json.view, map: json.map ?? null, itinerary: json.itinerary ?? null };
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
  display_region?: string;
  display_language?: string;
  display_currency?: string;
  display_currency_configured?: boolean;
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

// ---------------------------------------------------------------------------
// Travel documents. The server keeps the fields a document contained, never
// the document. Nothing here uploads a file for storage: the bytes are read
// once by /documents/extract and discarded with the request.
// ---------------------------------------------------------------------------

export type DocumentKind =
  | "passport"
  | "visa"
  | "insurance"
  | "vaccination"
  | "licence"
  | "idp"
  | "loyalty";

export interface TravelDocument {
  id: string;
  scope: "traveler" | "trip";
  type: DocumentKind;
  status: string;
  traveller_key: string;
  traveller_name: string;
  trip_id: string | null;
  fields: Record<string, string | number>;
  provenance: {
    source_kind: "manual" | "image" | "text";
    confidence: number;
    confirmed_by_user: boolean;
    captured_at: string;
  };
  created_at: string;
  updated_at: string;
}

export interface DocumentsResponse {
  documents: TravelDocument[];
  type_labels: Record<string, string>;
}

export interface ProposedField {
  key: string;
  label: string;
  value: string | number;
  masked: boolean;
  confidence: number;
}

export interface ExtractionResult {
  type: DocumentKind;
  source_kind: "image" | "text";
  fields: ProposedField[];
}

export interface ReadinessCheck {
  id: string;
  severity: "blocker" | "warning" | "ok";
  traveller_key: string;
  traveller_name: string;
  title: string;
  detail: string;
  rule: string;
  origin: "computed";
  action: string;
}

export interface DocumentReadiness {
  destination?: string;
  travellers?: { key: string; name: string; relationship: string }[];
  checks: ReadinessCheck[];
  blockers: number;
  warnings: number;
  badge: string;
  badge_tone?: "blocker" | "warning" | "";
  origin_country?: string;
  destination_country?: string;
  crosses_border?: boolean;
  reason?: string;
}

export async function fetchTravelDocuments(): Promise<DocumentsResponse> {
  const params = new URLSearchParams({ user_id: getUserId() });
  const res = await apiFetch(`${BASE}/documents?${params.toString()}`);
  ensureOk(res, "Could not load your document details");
  return res.json();
}

/** Read one document and get field proposals back. Stores nothing. */
export async function extractTravelDocument(
  type: DocumentKind,
  input: { contentBase64?: string; text?: string },
): Promise<ExtractionResult> {
  const res = await apiFetch(`${BASE}/documents/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: getUserId(),
      type,
      content_base64: input.contentBase64 ?? "",
      text: input.text ?? "",
    }),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || !json.ok) {
    throw new Error(json.message || "The document could not be read.");
  }
  return json as ExtractionResult;
}

export async function saveTravelDocument(record: {
  id?: string;
  type: DocumentKind;
  traveller_key: string;
  traveller_name: string;
  fields: Record<string, string | number>;
  provenance?: Partial<TravelDocument["provenance"]>;
}): Promise<TravelDocument> {
  const res = await apiFetch(`${BASE}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...record, id: record.id ?? "", user_id: getUserId() }),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || !json.ok) {
    throw new Error(json.message || "Could not save these details.");
  }
  return json.document as TravelDocument;
}

export async function deleteTravelDocument(id: string): Promise<boolean> {
  const res = await apiFetch(`${BASE}/documents/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, user_id: getUserId() }),
  });
  ensureOk(res, "Could not delete that detail");
  const json = await res.json();
  return Boolean(json.ok);
}

export async function clearTravelDocuments(): Promise<number> {
  const res = await apiFetch(`${BASE}/documents/clear`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getUserId() }),
  });
  ensureOk(res, "Could not delete your document details");
  const json = await res.json();
  return Number(json.deleted || 0);
}

export async function fetchDocumentReadiness(
  signal?: AbortSignal,
): Promise<DocumentReadiness> {
  const params = new URLSearchParams({ user_id: getUserId() });
  const res = await apiFetch(`${BASE}/trip/documents/readiness?${params.toString()}`, { signal });
  ensureOk(res, "Could not check this trip's documents");
  return res.json();
}


