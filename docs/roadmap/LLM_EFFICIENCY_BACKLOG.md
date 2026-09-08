# LLM Efficiency Backlog

## Purpose

This is a deferred engineering backlog for reducing model latency and token cost
inside the existing single trip-planning agent. It does not authorize
implementation or change product behavior. A selected item must first receive a
bounded feature brief with an evaluation set, token and latency targets, and a
regression matrix for the existing planning behaviors.

## Guiding constraints

- Preserve one LangGraph trip agent and phase-selected tools.
- Preserve grounded provider evidence, complete-plan completion gates, and
  durable chat transcripts.
- Optimize only with measured production evidence; a lower token count is not a
  win if it regresses itinerary quality, completion, or trust.
- Keep full transcripts and provider provenance available for user display,
  replay, and audit even when they are omitted from model context.

## Priority Candidates

### 1. Bounded Model Context

**Outcome:** model cost remains stable as a conversation and planning turn grow.

- Build model input from a compact deterministic trip and profile snapshot, the
  current turn's bounded research evidence, and a small recent conversational
  window.
- Retain the full transcript in chat persistence for display and recovery, but
  do not resend all historical turns to every graph iteration.
- Replace older context with a versioned deterministic summary where possible;
  reserve model summarization for a measured quality need.
- Define explicit per-turn character or token budgets for historical messages,
  tool evidence, and total model input.
- Add tests covering retained preferences, active-trip identity, prior decisions,
  tool-call continuity, and long-session budget enforcement.

**Primary ownership:** `src/tripplanner/graph.py`,
`src/tripplanner/web/chat_store.py`.

### 2. Phase-Capability Tool Binding

**Outcome:** the model receives only the tool schemas it can legitimately need in
the current planning phase.

- Replace the broad active-trip tool set with an explicit phase/capability
  matrix: conversation and profile, kickoff, research, itinerary mutation, and
  review.
- Keep deterministic forced-tool and completion-gate precedence authoritative.
- Measure schemas bound, prompt tokens, tool calls, completion rate, and repair
  turns by phase before and after the change.

**Primary ownership:** `src/tripplanner/graph_policy.py`,
`src/tripplanner/agents/trip_agent.py`.

### 3. Compact Agent Evidence Contracts

**Outcome:** the model reasons over concise, comparable provider facts rather
than raw provider payloads.

- Define tool-specific agent evidence with a bounded top-$k$ candidate set,
  provenance, freshness, price, key constraints, and opaque provider references.
- Keep the raw provider result outside model context when it is needed for a UI
  surface or booking handoff.
- Apply the same evidence budget on cache hits and misses so cache behavior
  cannot silently change model context size.
- Validate that grounded claims and provider handoff material remain complete.

**Primary ownership:** `src/tripplanner/tools/`,
`src/tripplanner/tools_cache.py`, `src/tripplanner/graph.py`.

### 4. Selective Sidecar LLM Work

**Outcome:** passive learning and chat handoff preserve useful durable facts
without creating unbounded extra model calls.

- Add per-user debounce and content-digest deduplication for passive learning.
- Cap input length and require a high-confidence preference signal before an
  extractor call.
- Seed destination-switch carryover from persisted structured preferences first;
  use an LLM only for missing portable context and with a small bounded input.
- Record sidecar-call token cost and extracted-value outcomes separately from the
  primary planning turn.

**Primary ownership:** `src/tripplanner/api.py`,
`src/tripplanner/tools/passive_learning.py`,
`src/tripplanner/web/chat_carryover.py`.

### 5. Turn-Level Cost Attribution

**Outcome:** prioritization is based on the actual cost and latency of a planning
turn rather than isolated provider or model events.

- Emit one PII-safe turn summary with total prompt and completion tokens, model
  rounds, phase count, schemas bound, history and evidence budget use, cache-hit
  ratio, tool duration, sidecar cost, and end-to-end latency.
- Add dashboards or queries that compare these values by planning phase,
  destination complexity, model, and release version.
- Establish a representative evaluation set and reject changes that lower cost
  while degrading planning completion, grounding, or user-visible latency.

**Primary ownership:** `src/tripplanner/observability.py`,
`src/tripplanner/graph.py`, `docs/operations/performance-cost.md`.

### 6. Reusable Model Client Evaluation

**Outcome:** avoid unnecessary client setup overhead when production telemetry
shows model wrapper construction is material.

- Measure connection/setup time separately from Azure model latency.
- Only then evaluate a settings-keyed, process-wide client factory that keeps
  callback and request context behavior correct.
- Do not share mutable per-turn state or callbacks between requests.

**Primary ownership:** `src/tripplanner/graph.py`.

## Selection Gate

Before implementing a candidate, capture a baseline for prompt tokens,
completion tokens, model rounds, full-turn latency, provider calls, cache-hit
ratio, completion rate, and grounded-claim regressions. The feature brief must
name the maximum acceptable quality regression and the rollback condition.