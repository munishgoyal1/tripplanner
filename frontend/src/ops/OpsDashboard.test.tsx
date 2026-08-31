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
  conversation_limits: {
    daily: { key: "2026-08-28", resets_at: "2026-08-29T00:00:00Z", categories: { new_trip: { used: 4, limit: 10, remaining: 6 }, existing_trip_turn: { used: 7, limit: 20, remaining: 13 } } },
    weekly: { key: "2026-W35", resets_at: "2026-08-31T00:00:00Z", categories: { new_trip: { used: 9, limit: 25, remaining: 16 }, existing_trip_turn: { used: 18, limit: 50, remaining: 32 } } },
    lifetime: { key: "lifetime", resets_at: null, categories: { new_trip: { used: 19, limit: 50, remaining: 31 }, existing_trip_turn: { used: 38, limit: 100, remaining: 62 } } },
  },
  tools: {
    search_hotels: { calls: 4, errors: 1, p50_ms: 100, p95_ms: 400, cache_hits: 2, hit_rate: 0.5, avg_ms: 180, error_types: { TimeoutError: 1 } },
  },
  providers: { liteapi: { calls: 4, successes: 3, failures: 1, failure_rate: 0.25, avg_ms: 300 } },
  provider_usage: {
    period_days: 30,
    since: "2026-07-11T12:00:00Z",
    pricing: { catalog_version: "2026-03-01", basis: "Planning estimates; provider billing exports remain authoritative.", currency: "USD" },
    totals: { calls: 8, avoided_calls: 0, failures: 1, estimated_cost_usd: 0.052, unknown_cost_calls: 2, prompt_tokens: 1000, completion_tokens: 500 },
    trip_costs: {
      new_trip: { interactions: 1, trips: 1, calls: 4, estimated_cost_usd: 0.03, average_estimated_cost_usd: 0.03, unknown_cost_interactions: 0 },
      trip_update: { interactions: 1, trips: 1, calls: 2, estimated_cost_usd: 0.015, average_estimated_cost_usd: 0.015, unknown_cost_interactions: 1 },
      infrastructure: { allocation_status: "not_allocated", basis: "Shared Azure infrastructure cost is not allocated per trip." },
    },
    by_initiator: [
      { environment: "canary", initiator: "user_trip", calls: 6, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.045, unknown_cost_calls: 1, prompt_tokens: 1000, completion_tokens: 500 },
      { environment: "canary", initiator: "audit", calls: 2, avoided_calls: 0, failures: 1, estimated_cost_usd: 0.007, unknown_cost_calls: 1, prompt_tokens: 0, completion_tokens: 0 },
    ],
    by_interaction_kind: [],
    by_provider_total: [{ environment: "canary", provider: "google", calls: 6, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.045, unknown_cost_calls: 1, prompt_tokens: 0, completion_tokens: 0 }],
    by_trip: [
      { environment: "canary", initiator: "user_trip", interaction_kind: "new_trip", trip_id: "trip-kashmir", trip_name: "Kashmir", calls: 4, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.03, unknown_cost_calls: 0, prompt_tokens: 700, completion_tokens: 300 },
      { environment: "canary", initiator: "user_trip", interaction_kind: "trip_update", trip_id: "trip-kashmir", trip_name: "Kashmir", calls: 2, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.015, unknown_cost_calls: 1, prompt_tokens: 300, completion_tokens: 200 },
    ],
    by_provider: [
      { environment: "canary", initiator: "user_trip", interaction_kind: "new_trip", trip_id: "trip-kashmir", interaction_id: "request-create", provider: "google", calls: 4, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.03, unknown_cost_calls: 0, prompt_tokens: 0, completion_tokens: 0 },
      { environment: "canary", initiator: "user_trip", interaction_kind: "trip_update", trip_id: "trip-kashmir", interaction_id: "request-update", provider: "google", calls: 2, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.015, unknown_cost_calls: 1, prompt_tokens: 0, completion_tokens: 0 },
    ],
    by_operation: [{ environment: "canary", initiator: "user_trip", interaction_kind: "trip_update", trip_id: "trip-kashmir", interaction_id: "request-update", provider: "google", operation: "text_search", sku_class: "essentials", calls: 2, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.015, unknown_cost_calls: 1, prompt_tokens: 0, completion_tokens: 0 }],
    by_interaction: [
      { environment: "canary", initiator: "user_trip", interaction_kind: "new_trip", trip_id: "trip-kashmir", trip_name: "Kashmir", interaction_id: "request-create", calls: 4, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.03, unknown_cost_calls: 0, prompt_tokens: 700, completion_tokens: 300 },
      { environment: "canary", initiator: "user_trip", interaction_kind: "trip_update", trip_id: "trip-kashmir", trip_name: "Kashmir", interaction_id: "request-update", calls: 2, avoided_calls: 0, failures: 0, estimated_cost_usd: 0.015, unknown_cost_calls: 1, prompt_tokens: 300, completion_tokens: 200 },
    ],
  },
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
    expect(screen.getByText("Conversation capacity")).toBeInTheDocument();
    expect(screen.getByText("4 / 10")).toBeInTheDocument();
    expect(screen.getByText("38 / 100")).toBeInTheDocument();
  });

  it("shows new-trip and update cost averages with expandable trip details", async () => {
    render(<OpsDashboard />);
    await screen.findByText("Activation funnel");

    fireEvent.click(screen.getByRole("tab", { name: /api & cost/i }));

    expect(screen.getByText("Measured calls")).toBeInTheDocument();
    expect(screen.getByText("Cost is an estimate, not a billing statement.")).toBeInTheDocument();
    expect(screen.getByText("Average new trip")).toBeInTheDocument();
    expect(screen.getByText("Average trip update")).toBeInTheDocument();
    expect(screen.getByText("New trip creation")).toBeInTheDocument();
    expect(screen.getByText("Existing trip updates")).toBeInTheDocument();
    expect(screen.getAllByText("Kashmir")).toHaveLength(2);
    expect(screen.getByText("Unknown price")).toBeInTheDocument();
    expect(screen.getAllByText(/\+ 1 unknown/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Cumulative provider cost").length).toBeGreaterThan(0);
  });
});
