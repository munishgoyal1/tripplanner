import { beforeEach, describe, expect, it, vi } from "vitest";
import { streamChat, type StreamHandlers } from "./api";

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
          'event: token\ndata: {"text":"Hello"}\n\n',
          'event: done\ndata: {"reply":"Hello","trip_id":"trip-1"}\n\n',
        ]),
      ),
    );
    const events = handlers();

    await streamChat("plan a trip", events);

    expect(events.onToken).toHaveBeenCalledWith("Hello");
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
