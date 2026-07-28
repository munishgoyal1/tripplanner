import type {
  DeselectItemOptions,
  Itinerary,
  MapView,
  PlannerReview,
  SavedTrip,
  SelectItemOptions,
  SelectionPlacement,
  StreamHandlers,
  StreamOptions,
  TripView,
} from "./types";

export type IdentityProvider = () => string | Promise<string>;
export type SessionTokenProvider = () => string | null | Promise<string | null>;

function ensureOk(response: Response, action: string): void {
  if (!response.ok) throw new Error(`${action} (${response.status}).`);
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
  if (event === "progress" && handlers.onProgress) {
    const stage = data.stage;
    if (stage === "thinking" || stage === "reviewing" || stage === "saving") {
      handlers.onProgress(stage);
    }
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
    return fetch(url, { ...init, credentials: "include", headers });
  }

  async fetchTripView(
    focus?: { kind: string; name: string },
    signal?: AbortSignal,
  ): Promise<TripView> {
    const params: Record<string, string> = { user_id: await this.userId() };
    if (focus?.name) {
      params.focus_kind = focus.kind;
      params.focus_name = focus.name;
    }
    const response = await this.request(this.url("/trip/view", params), { signal });
    ensureOk(response, "Could not load the trip");
    return response.json() as Promise<TripView>;
  }

  async fetchItinerary(signal?: AbortSignal): Promise<Itinerary> {
    const response = await this.request(
      this.url("/trip/itinerary", { user_id: await this.userId() }),
      { signal },
    );
    ensureOk(response, "Could not load the itinerary");
    return response.json() as Promise<Itinerary>;
  }

  async fetchMapView(signal?: AbortSignal): Promise<MapView> {
    const response = await this.request(
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
  ): Promise<{ role: "user" | "assistant"; text: string }[]> {
    const params: Record<string, string> = { user_id: await this.userId() };
    if (tripId) params.trip_id = tripId;
    const response = await this.request(this.url("/chat/history", params), { signal });
    ensureOk(response, "Could not load chat history");
    const data = (await response.json()) as {
      messages?: { role: "user" | "assistant"; text: string }[];
    };
    return data.messages ?? [];
  }

  async switchTrip(tripId: string): Promise<TripView | null> {
    const response = await this.post("/trips/switch", { trip_id: tripId });
    ensureOk(response, "Could not switch trips");
    const data = (await response.json()) as { ok?: boolean; view?: TripView };
    return data.ok && data.view ? data.view : null;
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

  async streamChat(
    message: string,
    handlers: StreamHandlers,
    options: StreamOptions = {},
  ): Promise<void> {
    const requestId = options.requestId ?? crypto.randomUUID();
    const response = await this.post("/chat/stream", {
      message,
      proposal_only: options.proposalOnly ?? false,
      request_id: requestId,
    });
    ensureOk(response, "Chat request failed");
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

  private async post(path: string, body: Record<string, unknown>): Promise<Response> {
    return this.request(this.url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, user_id: await this.userId() }),
    });
  }
}