import type {
  BudgetWhatIf,
  DecisionBatchApplyResult,
  DecisionBatchChange,
  DecisionApplyResult,
  DeselectItemOptions,
  Itinerary,
  MapView,
  PlaceGuidePage,
  PlannerReview,
  SavedTrip,
  SelectItemOptions,
  SelectionPlacement,
  StreamHandlers,
  StreamOptions,
  TripInputRequest,
  TripFreshnessResult,
  TripPriceRecheckResult,
  TripView,
  TripRepairResult,
  TripVerification,
  TripWorkspaceView,
} from "./types";

export type IdentityProvider = () => string | Promise<string>;
export type SessionTokenProvider = () => string | null | Promise<string | null>;

export function requireApiBaseUrl(value: string | undefined, settingName: string): string {
  const normalized = value?.trim().replace(/\/+$/, "");
  if (!normalized) throw new Error(`${settingName} must be configured.`);
  return normalized;
}

/** Carries the HTTP status so callers can react to retryable failures (409). */
export class ApiError extends Error {
  readonly status: number;
  readonly retryAfterMs: number | null;

  constructor(message: string, status: number, retryAfterMs: number | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfterMs = retryAfterMs;
  }
}

function retryAfterMs(response: Response): number | null {
  const header = response.headers?.get?.("Retry-After");
  const seconds = header ? Number(header) : NaN;
  return Number.isFinite(seconds) ? Math.max(0, seconds) * 1000 : null;
}

function ensureOk(response: Response, action: string): void {
  if (!response.ok) {
    throw new ApiError(`${action} (${response.status}).`, response.status, retryAfterMs(response));
  }
}

function parseFrame(frame: string): { event: string; data: Record<string, unknown> } | null {
  let event = "message";
  let rawData = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) rawData += line.slice(5).trim();
  }
  if (!rawData) return null;
  try {
    return { event, data: JSON.parse(rawData) as Record<string, unknown> };
  } catch {
    return null;
  }
}

function splitFrames(buffer: string): string[] {
  return buffer.replace(/\r\n/g, "\n").split("\n\n");
}

function dispatchFrame(event: string, data: Record<string, unknown>, handlers: StreamHandlers): void {
  if (event === "token") handlers.onToken(typeof data.text === "string" ? data.text : "");
  if (event === "tool") {
    handlers.onTool(
      typeof data.name === "string" ? data.name : "",
      data.phase === "end" ? "end" : "start",
      {
        args: typeof data.args === "string" ? data.args : undefined,
        duration_ms: typeof data.duration_ms === "number" ? data.duration_ms : undefined,
      },
    );
  }
  if (event === "receipt" && handlers.onReceipt && typeof data.text === "string") {
    handlers.onReceipt({
      seq: typeof data.seq === "number" ? data.seq : 0,
      at: typeof data.at === "string" ? data.at : "",
      kind: typeof data.kind === "string" ? data.kind : "",
      text: data.text,
      detail: typeof data.detail === "string" ? data.detail : undefined,
      decision_id: typeof data.decision_id === "string" ? data.decision_id : undefined,
      source: typeof data.source === "string" ? data.source : undefined,
    });
  }
  if (event === "progress" && handlers.onProgress) {
    const stage = data.stage;
    if (stage === "thinking" || stage === "reviewing" || stage === "saving") {
      handlers.onProgress(stage);
    }
  }
  if (
    event === "input_request"
    && handlers.onInputRequest
    && data.version === 1
    && typeof data.request_id === "string"
    && typeof data.question === "string"
    && Array.isArray(data.fields)
  ) {
    handlers.onInputRequest(data as unknown as TripInputRequest);
  }
  if (event === "done") {
    handlers.onDone(
      typeof data.reply === "string" ? data.reply : "",
      typeof data.trip_id === "string" ? data.trip_id : undefined,
    );
  }
  if (event === "error") {
    handlers.onError(typeof data.message === "string" ? data.message : "Unknown error.");
  }
}

export class TripplannerClient {
  constructor(
    private readonly baseUrl: string,
    private readonly getIdentity: IdentityProvider,
    private readonly getSessionToken?: SessionTokenProvider,
    //: Extra headers for every request. Optional so native callers are unaffected.
    private readonly getExtraHeaders?: () => Record<string, string>,
  ) {}

  private async userId(): Promise<string> {
    return this.getIdentity();
  }

  private url(path: string, params: Record<string, string> = {}): string {
    const query = new URLSearchParams(params).toString();
    return `${this.baseUrl.replace(/\/$/, "")}${path}${query ? `?${query}` : ""}`;
  }

  private async request(url: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    const token = await this.getSessionToken?.();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    for (const [name, value] of Object.entries(this.getExtraHeaders?.() ?? {})) {
      headers.set(name, value);
    }
    return fetch(url, { ...init, credentials: "include", headers });
  }

  async fetchTripView(
    focus?: { kind: string; name: string; day?: number; stop?: number },
    signal?: AbortSignal,
  ): Promise<TripView> {
    const params: Record<string, string> = { user_id: await this.userId() };
    if (focus?.name) {
      params.focus_kind = focus.kind;
      params.focus_name = focus.name;
      if (focus.day != null) params.focus_day = String(focus.day);
      if (focus.stop != null) params.focus_stop = String(focus.stop);
    }
    const response = await this.request(this.url("/trip/view", params), { signal });
    ensureOk(response, "Could not load the trip");
    return response.json() as Promise<TripView>;
  }

  async buildBudgetWhatIf(): Promise<BudgetWhatIf> {
    const response = await this.post("/trip/budget/what-if", {});
    ensureOk(response, "Could not build budget suggestions");
    return response.json() as Promise<BudgetWhatIf>;
  }

  async fetchPlaceGuide(
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
    const params: Record<string, string> = { user_id: await this.userId() };
    if (opts.city) params.city = opts.city;
    if (opts.kind) params.kind = opts.kind;
    if (opts.query) params.query = opts.query;
    if (opts.cursor) params.cursor = opts.cursor;
    if (opts.limit != null) params.limit = String(opts.limit);
    if (opts.focus?.name) {
      params.focus_kind = opts.focus.kind;
      params.focus_name = opts.focus.name;
    }
    const response = await this.request(this.url("/trip/places", params), { signal });
    ensureOk(response, "Could not load places");
    return response.json() as Promise<PlaceGuidePage>;
  }

  async fetchItinerary(signal?: AbortSignal): Promise<Itinerary> {
    const response = await this.request(
      this.url("/trip/itinerary", { user_id: await this.userId() }),
      { signal },
    );
    ensureOk(response, "Could not load the itinerary");
    return response.json() as Promise<Itinerary>;
  }

  async fetchVerification(signal?: AbortSignal): Promise<TripVerification> {
    const response = await this.request(
      this.url("/trip/verification", { user_id: await this.userId() }),
      { signal },
    );
    ensureOk(response, "Could not load the verification report");
    return response.json() as Promise<TripVerification>;
  }

  async refreshVerification(updatedAt = ""): Promise<TripFreshnessResult> {
    const response = await this.request(this.url("/trip/verification/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: await this.userId(), updated_at: updatedAt }),
    });
    ensureOk(response, "Could not recheck the itinerary");
    return response.json() as Promise<TripFreshnessResult>;
  }

  async recheckPrices(updatedAt = ""): Promise<TripPriceRecheckResult> {
    const response = await this.request(this.url("/trip/prices/recheck"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: await this.userId(), updated_at: updatedAt }),
    });
    ensureOk(response, "Could not recheck trip prices");
    return response.json() as Promise<TripPriceRecheckResult>;
  }

  async repairTrip(updatedAt = ""): Promise<TripRepairResult> {
    const response = await this.request(this.url("/trip/repair"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: await this.userId(), updated_at: updatedAt }),
    });
    ensureOk(response, "Could not rearrange the trip");
    return response.json() as Promise<TripRepairResult>;
  }

  async fetchMapView(signal?: AbortSignal): Promise<MapView> {    const response = await this.request(
      this.url("/trip/map", { user_id: await this.userId() }),
      { signal },
    );
    ensureOk(response, "Could not load the map");
    return response.json() as Promise<MapView>;
  }

  async fetchSavedTrips(signal?: AbortSignal): Promise<SavedTrip[]> {
    const response = await this.request(
      this.url("/trips", { user_id: await this.userId() }),
      { signal },
    );
    ensureOk(response, "Could not load saved trips");
    const data = (await response.json()) as { trips?: SavedTrip[] };
    return data.trips ?? [];
  }

  async fetchChatHistory(
    tripId?: string,
    signal?: AbortSignal,
  ): Promise<{ role: "user" | "assistant"; text: string; ts?: number; seconds?: number }[]> {
    const params: Record<string, string> = { user_id: await this.userId() };
    if (tripId) params.trip_id = tripId;
    const response = await this.request(this.url("/chat/history", params), { signal });
    ensureOk(response, "Could not load chat history");
    const data = (await response.json()) as {
      messages?: { role: "user" | "assistant"; text: string; ts?: number; seconds?: number }[];
    };
    return data.messages ?? [];
  }

  async switchTrip(tripId: string): Promise<TripWorkspaceView | null> {
    const response = await this.post("/trips/switch", { trip_id: tripId });
    ensureOk(response, "Could not switch trips");
    const data = (await response.json()) as {
      ok?: boolean;
      view?: TripView;
      map?: MapView;
      itinerary?: Itinerary;
    };
    if (!data.ok || !data.view) return null;
    return { view: data.view, map: data.map ?? null, itinerary: data.itinerary ?? null };
  }

  async startNewTrip(): Promise<void> {
    const response = await this.post("/trip/new", {});
    ensureOk(response, "Could not start a new trip");
  }

  async selectItem(kind: string, name: string, options: SelectItemOptions = {}): Promise<{
    view: TripView;
    alerts: string[];
    placement?: SelectionPlacement | null;
    placements?: SelectionPlacement[];
    planner_review?: PlannerReview | null;
  }> {
    const response = await this.post("/trip/select", { kind, name, ...options });
    ensureOk(response, "Could not add the place");
    const data = (await response.json()) as {
      ok?: boolean;
      view: TripView;
      alerts?: string[];
      placement?: SelectionPlacement | null;
      placements?: SelectionPlacement[];
      planner_review?: PlannerReview | null;
    };
    if (data.ok === false) throw new Error(data.alerts?.[0] || "Could not add the place.");
    return {
      view: data.view,
      alerts: data.alerts ?? [],
      placement: data.placement,
      placements: data.placements ?? [],
      planner_review: data.planner_review,
    };
  }

  async deselectItem(
    kind: string,
    name: string,
    options: DeselectItemOptions = {},
  ): Promise<{ view: TripView; alerts: string[]; planner_review?: PlannerReview | null }> {
    const response = await this.post("/trip/deselect", { kind, name, ...options });
    ensureOk(response, "Could not remove the place");
    const data = (await response.json()) as {
      view: TripView;
      alerts?: string[];
      planner_review?: PlannerReview | null;
    };
    return {
      view: data.view,
      alerts: data.alerts ?? [],
      planner_review: data.planner_review,
    };
  }

  async setStopBooked(day: number, name: string, booked: boolean): Promise<Itinerary> {
    const response = await this.post("/trip/stop/booked", { day, name, booked });
    ensureOk(response, "Could not update the stop");
    const data = (await response.json()) as { itinerary: Itinerary };
    return data.itinerary;
  }

  async confirmStopPlace(name: string): Promise<MapView> {
    const response = await this.post("/trip/stop/place", { name });
    ensureOk(response, "Could not confirm the place");
    const data = (await response.json()) as { map: MapView };
    return data.map;
  }

  async streamChat(
    message: string,
    handlers: StreamHandlers,
    options: StreamOptions = {},
  ): Promise<void> {
    const requestId = options.requestId ?? crypto.randomUUID();
    const response = await this.post(
      "/chat/stream",
      {
        message,
        proposal_only: options.proposalOnly ?? false,
        request_id: requestId,
      },
      options.signal,
    );
    if (!response.ok) {
      let detail = "";
      try {
        const payload = (await response.json()) as { detail?: unknown };
        if (typeof payload.detail === "string") detail = payload.detail;
      } catch {
        // Keep the status-based message when the server did not return JSON.
      }
      throw new ApiError(
        detail || `Chat request failed (${response.status}).`,
        response.status,
        retryAfterMs(response),
      );
    }
    const stream = response.body as ReadableStream<Uint8Array> | null;
    if (!stream?.getReader) {
      let terminalEvent = false;
      for (const rawFrame of splitFrames(await response.text())) {
        const frame = parseFrame(rawFrame);
        if (!frame) continue;
        if (frame.event === "done" || frame.event === "error") terminalEvent = true;
        dispatchFrame(frame.event, frame.data, handlers);
      }
      if (!terminalEvent) throw new Error("The response ended before completion.");
      return;
    }

    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let terminalEvent = false;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = splitFrames(buffer);
      buffer = frames.pop() ?? "";
      for (const rawFrame of frames) {
        const frame = parseFrame(rawFrame);
        if (!frame) continue;
        if (frame.event === "done" || frame.event === "error") terminalEvent = true;
        dispatchFrame(frame.event, frame.data, handlers);
      }
    }
    const finalFrame = parseFrame(buffer);
    if (finalFrame) {
      if (finalFrame.event === "done" || finalFrame.event === "error") terminalEvent = true;
      dispatchFrame(finalFrame.event, finalFrame.data, handlers);
    }
    if (!terminalEvent) throw new Error("The response stream ended before completion.");
  }

  async overrideDecision(
    decisionId: string,
    optionId: string,
    updatedAt?: string | null,
  ): Promise<DecisionApplyResult> {
    const response = await this.post(
      `/trip/decisions/${encodeURIComponent(decisionId)}/override`,
      { option_id: optionId, updated_at: updatedAt ?? "" },
    );
    return this.decisionResult(response, "Could not change this leg");
  }

  async restoreDecision(
    decisionId: string,
    updatedAt?: string | null,
  ): Promise<DecisionApplyResult> {
    const params: Record<string, string> = { user_id: await this.userId() };
    if (updatedAt) params.updated_at = updatedAt;
    const response = await this.request(
      this.url(`/trip/decisions/${encodeURIComponent(decisionId)}/override`, params),
      { method: "DELETE" },
    );
    return this.decisionResult(response, "Could not undo this change");
  }

  async applyDecisionOverrides(
    changes: DecisionBatchChange[],
    updatedAt?: string | null,
  ): Promise<DecisionBatchApplyResult> {
    const response = await this.post("/trip/decisions/overrides", {
      changes,
      updated_at: updatedAt ?? "",
    });
    if (!response.ok && response.status !== 409) {
      ensureOk(response, "Could not apply budget changes");
    }
    return (await response.json()) as DecisionBatchApplyResult;
  }

  /** A 409 is not a failure to hide: it carries the trip as it actually is now. */
  private async decisionResult(response: Response, action: string): Promise<DecisionApplyResult> {
    if (!response.ok && response.status !== 409) ensureOk(response, action);
    return (await response.json()) as DecisionApplyResult;
  }

  private async post(
    path: string,
    body: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<Response> {
    return this.request(this.url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, user_id: await this.userId() }),
      signal,
    });
  }
}