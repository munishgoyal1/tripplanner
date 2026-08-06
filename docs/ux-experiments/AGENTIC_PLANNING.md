# Agentic planning: an itinerary that cannot be edited into nonsense

## Meta

- Branch: `agents/worker-2`
- Owner: Munish Goyal
- Date started: 5-Aug-2026
- Date ended: pending
- Status: In evaluation
- Lab: `http://127.0.0.1:5175/lab-19-agentic-planning.html`
- Full-size preview: append `?preview=proposal`, `?preview=guarded`, or `?preview=console`

## Observed defects this Lab answers

Both were reported by the owner against the live Bengaluru → Indore trip.

1. **Add a place on the best day, and it lands after the flight home.** The agent placed a
   new attraction on day 5, after the departure flight, in a city the traveller had already
   left. The cause is reproducible in `src/tripplanner/tools/trip_planner.py`:
   `_place_selected_stop` scores each day with `route_km * 2.5 + count * 18 + duration * 0.35`
   and subtracts 30 for a day holding no named stops, so the departure day — check out plus
   a flight — always scores lowest and always wins "best day". `_closest_insert_index`
   returns `len(stops)` when the new place has no resolved coordinates, appending it after
   the flight; `_infer_stop_time` then assigns `min(previous + 120, 22:00)`, which reads
   17:40 against a 15:40 departure. No layer in the pipeline knows the trip has an end, or
   that the traveller's city changes when a flight completes.
2. **Change the Indore hotel to a 3-star, and the return flight disappears silently.** The
   swap itself was correct, but the operation also deleted the Bengaluru return leg, and
   nothing in the reply mentioned it. `_remove_candidate` protects only stops flagged
   `booked` and kinds outside `{attraction, other}`, and neither the tool result nor the
   narration enumerates what was removed. A change that touched one hotel was allowed an
   unbounded blast radius, and the explanation was written from the request rather than
   from the diff.

The shared root cause is that the model is the only thing standing between an intent and
the persisted trip. The prompt is asked to be simultaneously the parser, the planner, the
constraint solver and the narrator, and it is graded on none of them.

## Hypothesis

**Yes, a separate intelligence layer is required.** Not instead of the model — beside it.

A deterministic *plan engine* should own placement, validation and persistence. The model
should own only what it is genuinely better at: reading a loose request, ranking options
against stated preferences, and explaining a result in the owner's language. If the engine
holds the write authority, then no phrasing, no temperature and no tool-call ordering can
produce a stop scheduled after the flight home, because that state is unrepresentable.

The engine is small and knowable. It is roughly 300 lines of arithmetic over a trip that
already carries dates, times, durations, cities and coordinates. The Lab implements it in
`planEngine.ts` and runs it live in the browser; every verdict, score and rejection shown
in the Lab is computed, not authored.

## Pipeline

Every change, from every channel, takes the same six steps:

| Step | Owner | Responsibility |
| --- | --- | --- |
| 1 · Intent | Model | Turn free text or a gesture into a typed operation |
| 2 · Resolve | Engine | Bind names to real places, coordinates, opening hours, prices |
| 3 · Plan | Engine | Enumerate candidate slots and score them |
| 4 · Validate | Engine | Test every invariant; reject rather than repair silently |
| 5 · Blast radius | Engine | Declare exactly what this operation may touch, and refuse the rest |
| 6 · Explain | Model | Narrate the engine's diff — never the request |

The model never writes trip state. It emits an operation and receives a verdict.

## Invariants

Hard invariants are checked on every write and cannot be overridden by the model.

| Code | Rule | Meaning |
| --- | --- | --- |
| I1 | Trip envelope | Nothing may be scheduled before arrival or after departure |
| I2 | Presence | A stop's city must match where the traveller actually is at that moment |
| I3 | Opening hours | A visit must fit inside the place's open window |
| I4 | Temporal feasibility | Consecutive stops must be reachable, travel time included |
| I5 | Departure buffer | Two hours must remain clear before any flight |
| I6 | Stay coverage | Every night in a city must be covered by a stay |
| I7 | Return coverage | Every outbound leg needs a matching return home |
| I8 | Blast radius | An operation may only alter the stops it declared |

I1, I2, I7 and I8 are precisely the four the production pipeline does not have, and they
are exactly the four that would have prevented both reported defects.

## Variants

- **A · Proposal first.** Nothing is written until the owner accepts. Each request returns
  a chosen slot with its reasons, a scored alternative, and the slots that were ruled out
  with the invariant that ruled them out. *Exact delta:* the highest trust and the most
  clicks; every change, however trivial, costs one confirmation.
- **B · Guarded autonomy.** The engine applies a change immediately when it is legal,
  reversible and inside the declared blast radius, and leaves a receipt carrying *why here*,
  what changed, and Undo. It stops and asks only when an invariant is violated, money or a
  booking is involved, or the change reaches outside its declared radius. *Exact delta:*
  keeps the speed of today with a hard floor under it; the owner must trust the floor.
- **C · Plan console.** The workspace gains a persistent panel showing live invariant
  status, the day-by-day feasibility of the current plan, and the full rejection log for
  the last operation. *Exact delta:* the most legible and the most inspectable; costs
  permanent screen area and reads as an engineering tool.

A *Compare with today* toggle renders the current production behaviour: the naive answer
is applied with no validation, no receipt and no mention of collateral damage.

## Channel parity

The Lab's channel selector — chat, map, itinerary, details — changes only *where* the
agency surface appears. The operation, the verdict, the receipt and the invariants are
identical in all four. This is the point: dragging a pin on the map, retiming a stop in the
itinerary, changing a hotel class in details and asking in chat are four spellings of one
typed operation, and none of them may bypass the engine.

## Required in every option

1. A refused change must name the invariant it broke, in the owner's language.
2. An accepted change must be able to answer "why here" without a second request.
3. Every write is reversible from its receipt.
4. Collateral removals are never silent, and a booked or paid item is never removed
   without explicit consent.
5. Money, bookings and cancellations always stop for confirmation.
6. The same operation issued from any channel produces the same verdict.
7. The engine's decisions are computed and inspectable, not narrated by the model.

## Scope

- Changed experiment files:
  - `frontend/labs/lab-19-agentic-planning.html`
  - `frontend/labs/src/agentic-planning/main.tsx`
  - `frontend/labs/src/agentic-planning/AgenticWorkspace.tsx`
  - `frontend/labs/src/agentic-planning/planEngine.ts`
  - `frontend/labs/src/agentic-planning/fixture.ts`
  - `frontend/labs/src/shared/labRecords.ts`, `LabScope.tsx`, `vite.config.ts` (registration)
- Related production code, read but not modified:
  - `src/tripplanner/tools/trip_planner.py` — `_place_selected_stop`, `_closest_insert_index`,
    `_infer_stop_time`, `_remove_candidate`, `_rebalance_day`; the source of both defects.
  - `src/tripplanner/graph.py` — the agent and tool loop that would host the engine.
  - `src/tripplanner/web/trip_view.py` — where a verdict and receipt would enter the view model.
- Non-goals: provider search, geocoding, booking handoff, server-side persistence, and the
  visual design of the itinerary, map and details panes, which appear here only as
  production-scale context.

## Interaction intent

The owner should be able to make a careless request and receive a careful plan. Speed is
worth keeping, but only above a floor the owner never has to check. When the agent cannot
be careful, it should say so precisely rather than guess, and when it does act, the reason
should already be on screen before anyone asks for it.

## Test scenarios

1. Run *Add Patalpani Waterfall on the best day* with *Compare with today* on, and confirm
   the naive answer lands on day 5 at 17:40, after the 15:40 departure.
2. Run the same request in each option and confirm the chosen slot, its reasons, its
   alternative and the rejection log are all reachable.
3. Run *Change the Indore hotel to a 3-star* with *Compare with today* on, and confirm the
   return flight vanishes with no mention.
4. Run the same request in each option and confirm the return flight is protected, the
   consent items are itemised, and the cost delta is stated before acceptance.
5. Repeat both scenarios from the map, itinerary and details channels and confirm the
   verdict is identical.
6. Undo an applied change from its receipt and confirm the plan returns to a sound state.

## Scorecard (1-5)

| Criterion | A · Proposal | B · Guarded | C · Console |
| --- | --- | --- | --- |
| Trust in a careless request | | | |
| Speed for a safe change | | | |
| Legibility of a refusal | | | |
| Collateral visibility | | | |
| Channel parity | | | |
| Cost in screen area | | | |

## Decision

- Decision: pending owner selection. Recommended starting point: **B · Guarded autonomy**,
  with C available as a toggle rather than a permanent panel.
- Implementation: not started; no production code changed by this Lab.
- Rationale: pending.
- Next action: owner selects an option in the Lab. Promotion should carry the plan engine
  and its invariants, not only the receipt and proposal UI — the defects live below the
  interface.
