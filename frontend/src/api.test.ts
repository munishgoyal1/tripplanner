import { beforeEach, describe, expect, it, vi } from "vitest";
import { deselectItem, fetchSavedTrips, streamChat, tripExportPdfUrl, type StreamHandlers } from "./api";

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

describe("streamChat", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("dispatches a complete reply", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamResponse([
          'event: progress\ndata: {"stage":"thinking"}\n\n',
          'event: token\ndata: {"text":"Hello"}\n\n',
          'event: done\ndata: {"reply":"Hello","trip_id":"trip-1"}\n\n',
        ]),
      ),
    );
    const events = handlers();

    await streamChat("plan a trip", events);

    expect(events.onToken).toHaveBeenCalledWith("Hello");
    expect(events.onProgress).toHaveBeenCalledWith("thinking");
    expect(events.onDone).toHaveBeenCalledWith("Hello", "trip-1");
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
  beforeEach(() => {
    localStorage.clear();
  });

  it("rejects non-success list responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })));

    await expect(fetchSavedTrips()).rejects.toThrow("Could not load saved trips (503)");
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
