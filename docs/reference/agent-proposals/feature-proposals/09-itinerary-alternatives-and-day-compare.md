# Feature 09 — Itinerary Alternatives & Day A/B Compare

- **Pillars:** E (insightful outcome), B (easy editing)
- **Status:** Proposed (sharpens backlog #6 into an in-context, day-level compare with selective adoption)
- **Size:** L · **Risk:** med · **Suggested lane:** Agent 2 (variant generator) + Agent 1 (compare UI)

## The pain

Users want to explore genuinely different shapes — "more relaxed," "foodie," "cheaper" —
without losing their current plan or regenerating everything from scratch. Today the only
path is a chat request that overwrites the plan, which discourages exploration.

## Outcome

For a single day (or later the whole trip), generate a few intentional variants
(relaxed / balanced / packed / foodie / budget), compare them side by side on price, travel
load, free time, and fit, and adopt one — or adopt just one day — while the base plan stays
intact until accepted.

## Bounded v1 (day-level first)

- "Reshape Day" produces 2–3 variants using existing research + deterministic reflow;
  compare compact metrics; "Use this day" applies via authoritative mutation; booked stops
  preserved.
- Whole-trip alternatives are a later phase (cost/latency).
- **No cosmetically-different duplicates** — each variant must differ on a named axis.

## UX

- From a day header action → variants render as compact compare cards (metrics + key
  differences) → adopt one day. Base plan unchanged until adopt.

## Implementation notes

- **Backend:** a **proposal-only** variant generator in `src/tripplanner/tools/trip_planner.py`
  that reuses research + reflow to produce N day variants **without persisting**, returning
  metrics. Respects proposal-only / no-passive-learning semantics (`PLAN-04`).
- **Frontend:** compare UI in `frontend/src/components/ItineraryPanel.tsx` /
  `RightRail.tsx`; adopt calls the normal mutation path.

## Perf / privacy / cost

Bounded to a single day and a small N; explicit user action gates provider calls; reuse the
existing 60-second live-search cache.

## Risks & mitigations

- **Cost/latency of variants** → day scope + small N + explicit trigger; show progress and
  cache. Med risk on latency.

## Acceptance

- Variants are genuinely different on a stated axis (no duplicates).
- Adopt-one-day persists and reflows; the base plan is untouched until adopt.
- Booked stops preserved; provider cost bounded.
