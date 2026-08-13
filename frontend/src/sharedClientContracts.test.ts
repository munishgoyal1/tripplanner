import { afterEach, describe, expect, it, vi } from "vitest";

import {
  exactItineraryOccurrence,
  LatestRequestGate,
  requireApiBaseUrl,
  SerializedMutationQueue,
  TripplannerClient,
  type StreamHandlers,
} from "../../packages/tripplanner-client/src";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("shared API configuration contract", () => {
  it("normalizes an explicitly configured API URL", () => {
    expect(requireApiBaseUrl(" https://canary.example/api/// ", "TRIP_API")).toBe(
      "https://canary.example/api",
    );
  });

  it("rejects a missing API URL instead of selecting an environment implicitly", () => {
    expect(() => requireApiBaseUrl("  ", "TRIP_API")).toThrow(
      "TRIP_API must be configured.",
    );
  });
});

describe("shared itinerary occurrence contract", () => {
  it("converts repeated itinerary rows to distinct one-based occurrences", () => {
    expect(exactItineraryOccurrence(2, 0)).toEqual({
      day: 2,
      stop: 1,
    });
    expect(exactItineraryOccurrence(2, 2)).toEqual({
      day: 2,
      stop: 3,
    });
  });
});

describe("shared refresh request gate", () => {
  it("aborts and invalidates superseded refreshes", () => {
    const gate = new LatestRequestGate();
    const first = gate.start();
    const second = gate.start();

    expect(first.signal.aborted).toBe(true);
    expect(first.isCurrent()).toBe(false);
    expect(second.signal.aborted).toBe(false);
    expect(second.isCurrent()).toBe(true);

    gate.abort();
    expect(second.signal.aborted).toBe(true);
    expect(second.isCurrent()).toBe(false);
  });
});

describe("shared chat stream contract", () => {
  function handlers(): StreamHandlers {
    return {
      onToken: vi.fn(),
      onTool: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    };
  }

  function streamResponse(chunks: string[], init?: ResponseInit): Response {
    const encoder = new TextEncoder();
    return new Response(new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    }), init);
  }

  it("retains split SSE frames until a terminal event arrives", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse([
      'event: token\r\ndata: {"text":"Hel',
      'lo"}\r\n\r\nevent: done\r\ndata: {"reply":"Hello","trip_id":"trip-1"}\r\n\r\n',
    ])));
    const events = handlers();
    const client = new TripplannerClient("/api", () => "local-user");

    await client.streamChat("Plan a trip", events, { requestId: "request-1" });

    expect(events.onToken).toHaveBeenCalledWith("Hello");
    expect(events.onDone).toHaveBeenCalledWith("Hello", "trip-1");
  });

  it("rejects a stream that closes without done or error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamResponse([
      'event: token\ndata: {"text":"Partial"}\n\n',
    ])));
    const client = new TripplannerClient("/api", () => "local-user");

    await expect(client.streamChat("Plan a trip", handlers(), { requestId: "request-1" }))
      .rejects.toThrow("response stream ended before completion");
  });

  it("preserves the server reason when a stream is rejected by the workspace lock", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "A workspace update is in progress. Please retry shortly." }), {
        status: 409,
        headers: { "Content-Type": "application/json", "Retry-After": "2" },
      }),
    ));
    const client = new TripplannerClient("/api", () => "local-user");

    await expect(client.streamChat("Replan Paris", handlers(), { requestId: "request-1" }))
      .rejects.toThrow("A workspace update is in progress. Please retry shortly.");
  });
});

describe("shared mutation queue", () => {
  it("serializes mutations through their authoritative refresh boundary", async () => {
    const queue = new SerializedMutationQueue();
    const events: string[] = [];
    let releaseFirst: () => void = () => undefined;
    const firstBlocked = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });

    const first = queue.run(async () => {
      events.push("first:mutation");
      await firstBlocked;
      events.push("first:refresh");
    });
    const second = queue.run(async () => {
      events.push("second:mutation");
    });

    await Promise.resolve();
    expect(events).toEqual(["first:mutation"]);

    releaseFirst();
    await Promise.all([first, second]);
    expect(events).toEqual(["first:mutation", "first:refresh", "second:mutation"]);
  });

  it("continues after a failed mutation without hiding its rejection", async () => {
    const queue = new SerializedMutationQueue();

    await expect(queue.run(async () => {
      throw new Error("conflict");
    })).rejects.toThrow("conflict");
    await expect(queue.run(async () => 42)).resolves.toBe(42);
  });
});