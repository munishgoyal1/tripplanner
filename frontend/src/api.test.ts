import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  deselectItem,
  fetchSavedTrips,
  savePreferences,
  streamChat,
  tripExportPdfUrl,
  type Preferences,
  type StreamHandlers,
} from "./api";

function streamResponse(frames: string[], status = 200): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        frames.forEach((frame) => controller.enqueue(encoder.encode(frame)));
        controller.close();
      },
    }),
    { status, headers: { "Content-Type": "text/event-stream" } },
  );
}

function handlers(): StreamHandlers {
  return {
    onToken: vi.fn(),
    onTool: vi.fn(),
    onProgress: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
  };
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("tripplanner_user_id", "local");
});

describe("streamChat", () => {
  it("dispatches a complete reply", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamResponse([
          'event: progress\ndata: {"stage":"thinking"}\n\n',
          'event: input_request\ndata: {"version":1,"request_id":"request-1","question":"Pick a pace","known_context":["Boutique stays"],"fields":[{"id":"pace","label":"Pace","kind":"single","value":"balanced","options":[{"value":"easy","label":"Easy"},{"value":"balanced","label":"Balanced"}]}],"submit_label":"Continue","allow_skip":true}\n\n',
          'event: token\ndata: {"text":"Hello"}\n\n',
          'event: done\ndata: {"reply":"Hello","trip_id":"trip-1"}\n\n',
        ]),
      ),
    );
    const events = handlers();
    events.onInputRequest = vi.fn();

    await streamChat("plan a trip", events);

    expect(events.onToken).toHaveBeenCalledWith("Hello");
    expect(events.onProgress).toHaveBeenCalledWith("thinking");
    expect(events.onInputRequest).toHaveBeenCalledWith(expect.objectContaining({
      request_id: "request-1",
      question: "Pick a pace",
    }));
    expect(events.onDone).toHaveBeenCalledWith("Hello", "trip-1");
  });

  it("marks planner review turns as proposal-only", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse(['event: done\ndata: {"reply":"Three options"}\n\n']),
    );
    vi.stubGlobal("fetch", fetchMock);

    await streamChat("Review Day 3", handlers(), { proposalOnly: true });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toMatchObject({
      message: "Review Day 3",
      proposal_only: true,
      request_id: expect.any(String),
    });
  });

  it("rejects when the stream ends without a terminal event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamResponse(['event: token\ndata: {"text":"Partial"}\n\n']),
      ),
    );

    await expect(streamChat("plan a trip", handlers())).rejects.toThrow(
      "ended before the reply completed",
    );
  });

  it("rejects non-success responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Service unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(streamChat("plan a trip", handlers())).rejects.toThrow("Service unavailable");
  });
});

describe("saved-trip API", () => {
  it("rejects non-success list responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })));

    await expect(fetchSavedTrips()).rejects.toThrow("Could not load saved trips (503)");
  });
});

describe("preferences API", () => {
  it("omits an unchanged generated summary while preserving planning mode", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, about_me_extracted: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const prefs: Preferences = {
      display_name: "Munish",
      home_city: "Bengaluru",
      home_country: "India",
      trip_style: "balanced",
      budget_level: "moderate",
      flight_class: "economy",
      prefer_direct_flights: true,
      hotel_star_rating_min: 3,
      dietary: [],
      interests: [],
      dislikes: [],
      about_me: "",
      profile_summary: "Generated summary",
      profile_summary_updated_at: "2026-07-28T12:00:00",
      planning_mode: "interactive",
    };

    await savePreferences({ planning_mode: prefs.planning_mode });

    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(String(init.body));
    expect(body.planning_mode).toBe("interactive");
    expect(body).not.toHaveProperty("display_name");
    expect(body).not.toHaveProperty("profile_summary");
    expect(body).not.toHaveProperty("profile_summary_updated_at");
  });

  it("includes the summary compare timestamp for a real edit", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, about_me_extracted: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const prefs = {
      display_name: "",
      home_city: "",
      home_country: "",
      trip_style: "balanced",
      budget_level: "moderate",
      flight_class: "economy",
      prefer_direct_flights: true,
      hotel_star_rating_min: 3,
      dietary: [],
      interests: [],
      dislikes: [],
      about_me: "",
      profile_summary: "My correction",
      profile_summary_updated_at: "2026-07-28T12:00:00",
      planning_mode: "direct" as const,
    };

    await savePreferences({
      profile_summary: prefs.profile_summary,
      profile_summary_updated_at: prefs.profile_summary_updated_at,
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toMatchObject({
      profile_summary: "My correction",
      profile_summary_updated_at: "2026-07-28T12:00:00",
    });
  });

  it("surfaces a stale summary response as a reloadable conflict", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: "profile summary changed" }), { status: 409 }),
      ),
    );
    const prefs = {
      display_name: "",
      home_city: "",
      home_country: "",
      trip_style: "balanced",
      budget_level: "moderate",
      flight_class: "economy",
      prefer_direct_flights: true,
      hotel_star_rating_min: 3,
      dietary: [],
      interests: [],
      dislikes: [],
      about_me: "",
      profile_summary: "Stale correction",
      profile_summary_updated_at: "2026-07-28T12:00:00",
      planning_mode: "direct" as const,
    };

    await expect(
      savePreferences({
        profile_summary: prefs.profile_summary,
        profile_summary_updated_at: prefs.profile_summary_updated_at,
      }),
    ).resolves.toMatchObject({ ok: false, summary_conflict: true });
  });
});

describe("PDF export URL", () => {
  it("forwards photo and map choices", () => {
    const url = new URL(
      tripExportPdfUrl({
        include_photos: false,
        include_map_circuit: true,
        template: "family",
      }),
      "https://trip.example",
    );

    expect(url.searchParams.get("include_photos")).toBe("0");
    expect(url.searchParams.get("include_map_circuit")).toBe("1");
    expect(url.searchParams.get("template")).toBe("family");
  });
});

describe("place removal", () => {
  it("sends exact occurrence context", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      view: { items: [] },
      alerts: ["Removed Eiffel Tower from Day 2."],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await deselectItem("attraction", "Eiffel Tower", {
      day: 2,
      stop: 3,
      all_occurrences: false,
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toMatchObject({
      kind: "attraction",
      name: "Eiffel Tower",
      day: 2,
      stop: 3,
      all_occurrences: false,
    });
  });
});
