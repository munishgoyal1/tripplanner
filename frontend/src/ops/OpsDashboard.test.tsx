import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchOpsOverview, type OpsOverview } from "../api";
import OpsDashboard from "./OpsDashboard";

vi.mock("../api", () => ({ fetchOpsOverview: vi.fn() }));

const overview: OpsOverview = {
  generated_at: "2026-08-10T12:00:00Z",
  uptime_seconds: 120,
  business: {
    new_trips: { today: 1, "7d": 3, "30d": 8 },
    active_trips: { today: 2, "7d": 5, "30d": 9 },
    chat_requests: 4,
    iterations: 9,
    inventory: { trips: 9, flights: 2, hotels: 3, activities: 12 },
  },
  product: {
    events: 12,
    sessions: 4,
    users: 3,
    engagement_seconds: 600,
    activities: { page_view: 4, planning_started: 3, planning_completed: 2 },
    funnel: { page_view: 4, planning_started: 3, trip_created: 2, planning_completed: 2 },
    drop_offs: { planning_abandoned: 1 },
    countries: { unknown: 12 },
    sources: { direct: 8, search: 4 },
  },
  chat_turns: {
    calls: 4,
    completed: 3,
    errors: 1,
    distinct_users: 2,
    p50_ms: 1200,
    p95_ms: 4000,
    tool_calls: 8,
    avg_tools_per_turn: 2,
    outcomes: { completed: 3, error: 1 },
  },
  requests: {
    calls: 10,
    errors: 1,
    p50_ms: 50,
    p90_ms: 120,
    p95_ms: 200,
    by_route: { "POST /chat/stream": { calls: 4, errors: 1, p50_ms: 1200, p95_ms: 4000 } },
    error_statuses: { "500": 1 },
  },
  models: { calls: 4, errors: 0, p50_ms: 800, p95_ms: 2200, recent: [] },
  usage: { month: "2026-08", model_calls: 20, prompt_tokens: 1000, completion_tokens: 500, cost_usd: 1.25 },
  tools: {
    search_hotels: { calls: 4, errors: 1, p50_ms: 100, p95_ms: 400, cache_hits: 2, hit_rate: 0.5, avg_ms: 180, error_types: { TimeoutError: 1 } },
  },
  providers: { liteapi: { calls: 4, successes: 3, failures: 1, failure_rate: 0.25, avg_ms: 300 } },
  cache: { configured: true, backend: "redis", redis_connected: true, fallback_active: false, memory_entries: 2, redis_entries: 7, redis_bytes: 2048, redis_stats_truncated: false },
};

describe("OpsDashboard", () => {
  beforeEach(() => vi.mocked(fetchOpsOverview).mockResolvedValue(overview));

  it("switches between business and system health insights", async () => {
    render(<OpsDashboard />);
    expect(await screen.findByText("Activation funnel")).toBeInTheDocument();
    expect(screen.getByText("Observed drop-off")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /system health/i }));

    await waitFor(() => expect(screen.getByText("Tool performance")).toBeInTheDocument());
    expect(screen.getByText("Provider reliability")).toBeInTheDocument();
    expect(screen.getByText("Top cache hits")).toBeInTheDocument();
    expect(screen.getByText("Persisted inventory")).toBeInTheDocument();
  });
});
