# Feature 02 — Direct-Manipulation Itinerary Editing

- **Pillars:** B (easy editing), A (breezy)
- **Status:** Proposed (new; builds on `MUT-01` mutations + `PLAN-04` reflow)
- **Size:** L · **Risk:** med · **Suggested lane:** Agent 1 (dnd UI) + Agent 2 (order/reflow contract)

## The pain

Today, moving a stop to another day or changing its order means chatting or using
discrete controls. The number-one editing expectation in itinerary tools is "just let
me drag it." Users think spatially about days and sequence.

## Outcome

Drag any unbooked stop to another day or to a new position; the itinerary retimes
deterministically via the existing reflow; booked stops, hotels, flights, and transport
stay locked. The change persists like any authoritative mutation and refreshes Map and
Details coherently.

## Bounded v1

- **Reorder within a day** (vertical drag) → backend retimes in the chosen order.
  Explicit user order wins over auto-optimization, consistent with the existing
  "explicit day choice takes precedence over automatic rebalancing" rule.
- **Move across days** (drag onto a day header) → maps to the existing move-day
  mutation + reflow.
- Booked / hotel / flight / transport rows are non-draggable with a clear locked affordance.
- Keyboard-accessible equivalents (move up/down, move to day N) for a11y.

## UX

- Grab handle on `ItineraryStopRow`; drag shows a live insertion line; day headers
  highlight as drop targets.
- On drop: optimistic reorder + quiet "updating…", then authoritative reflow reconciles.
- Conflict (day already contains that place, or a booked-occurrence conflict) → the
  existing available-days / unbook-and-retry path; itinerary unchanged on reject.

## Implementation notes

- **Frontend:** drag-and-drop in `frontend/src/components/ItineraryPanel.tsx` /
  `ItineraryStopRow.tsx` (use `@dnd-kit` for pointer + keyboard a11y). Optimistic apply in
  `frontend/src/workspaceState.ts`; reconcile on server response. Respect exact occurrence
  identity (day/stop).
- **Backend:** reuse move-day plus a "set day order" honored by reflow in
  `src/tripplanner/tools/trip_planner.py` (`_place_selected_stop`, `_rebalance_day` already
  exist); keep booked stops fixed. No persisted-stop schema change beyond order.
- **Coherence:** reuse `MUT-01` whole-itinerary refresh; successful mutation supersedes
  in-flight reads.

## Perf / privacy / cost

Optimistic UI hides latency; one authoritative mutation per drop; no provider calls.
Depends on the perceived-performance layer (Feature 08) for smoothness.

## Risks & mitigations

- **Within-day manual order vs. route optimization tension** → v1 treats a manual reorder
  as an explicit user sequence the schedule contract retimes, plus a small "re-optimize
  order" action to snap back. Validate with focused tests (times strictly increase; booked
  fixed; markers/map order stay consistent). Med risk.

## Acceptance

- Move-day and reorder persist and reflow correctly.
- Booked / hotel / flight / transport rows never move.
- Keyboard path works; Map and Details stay in sync; invalid drops leave the trip unchanged.
