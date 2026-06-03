import type { TripView } from "./types";

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

export interface StreamHandlers {
  onToken: (text: string) => void;
  onTool: (name: string, phase: "start" | "end") => void;
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
      h.onTool(data.name ?? "", data.phase ?? "start");
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
}

export async function fetchPreferences(): Promise<Preferences> {
  const params = new URLSearchParams({ user_id: getUserId() });
  const res = await fetch(`${BASE}/preferences?${params.toString()}`);
  return res.json();
}

export async function savePreferences(prefs: Preferences): Promise<void> {
  await fetch(`${BASE}/preferences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...prefs, user_id: getUserId() }),
  });
}
