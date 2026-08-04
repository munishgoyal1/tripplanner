# Feature 07 — Live Itinerary Health Meter & One-Tap Fixes

- **Pillars:** E (insightful outcome), B (easy editing)
- **Status:** Proposed (sharpens backlog #4 into a live inline gauge tied to the existing impact gate)
- **Size:** M · **Risk:** low · **Suggested lane:** Agent 2 (expose gate) + Agent 1 (meter UI)

## The pain

Users can't tell if a plan is genuinely good or ready. Is Day 3 overpacked? Any day
without a meal? Any unbooked essentials? Today this only surfaces as post-mutation flags,
so the overall quality of the plan is invisible at a glance.

## Outcome

An always-visible, compact health meter in the trip snapshot scores pace balance, meal
coverage, travel load, empty/thin days, booking gaps, and budget fit — and each weak
dimension links to a one-tap fix that triggers the right structured intent or planner review.

## Bounded v1

- Reuse the deterministic impact gate + completion gaps already computed
  (`planning_completion_gaps`, `assess_itinerary_change` in `tools/trip_planner.py`).
  Aggregate into 4–6 dimensions with green/amber states and short reasons.
- Each amber links to an action: "Add a meal to Day 2" (structured add), "Balance Day 3"
  (reflow), "Book flight" (handoff), "Review with planner" (proposal-only, `PLAN-04`).
- Non-alarmist and honest; **quiet when all green**; valid transfer/leisure days are not
  flagged.

## UX

- Compact meter under the Decision brief; expand for per-dimension reasons + fix buttons.
- Updates after each mutation (the gate is already recomputed).

## Implementation notes

- **Backend:** expose the existing gate results in the `TripOverview` contract
  (`src/tripplanner/web/trip_view.py`) instead of only on mutation responses; small
  aggregation in `src/tripplanner/web/insight.py` (shared with Feature 06).
- **Frontend:** render in `frontend/src/components/TripSnapshot.tsx`; fix buttons reuse the
  Feature 04 intents and planner review.

## Perf / privacy / cost

Reuses existing computation; negligible added cost; no provider calls.

## Risks & mitigations

- **Nagging / noise** → strictly quiet-when-green, cap to material issues only. Low risk.

## Acceptance

- Meter reflects real gate output; each amber has a working one-tap fix.
- Silent when healthy; no false alarms on valid transfer or intentional leisure days.
