# Agentic planning: an itinerary that cannot be edited into nonsense

## Meta

- Branch: not retained; current implementation work uses a sandbox
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

A guard alone is not enough. It stops a plan that is impossible; it has nothing to say
about a plan that is merely bad. The second half of this Lab is an **effort model** — a
separate module with strictly weaker authority — that ranks the options the invariants
already permitted and, very occasionally, says what a change cost. Its design is below, and
its central constraint is that it may never block and may never show the owner a number it
invented.

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

## The effort model

The invariants answer whether a plan is *possible*. They cannot answer whether it is any
good. A day can satisfy all eight and still be eleven kilometres on foot in November sun
after a 05:00 alarm. That is the second layer, and its authority is deliberately different.

> The invariant may block but never speaks in numbers.
> The score may speak but never blocks.

Merging them fails in one of two ways. Fold taste into the guard and it starts refusing
legal plans the owner actually wanted. Fold the guard into a total score and one genuinely
broken day is averaged away by four good ones. So the effort model lives in its own module,
`effortModel.ts`, beside `planEngine.ts` and importing only its arithmetic.

### Three response modes

| Mode | When | Behaviour |
| --- | --- | --- |
| Refuse | An invariant is broken | Names the invariant in words and offers the nearest legal slot. The only outcome that stops anything. |
| Apply, and say what it cost | Legal, but notably worse | Applies. The receipt states the regression as a measured quantity. Never asks, because it was always allowed. |
| Apply silently | Legal, neutral or better | The common case, and the reason this layer is not friction. |

### Fatigue is a vector, not a number

Five currencies, because they recover at completely different rates overnight and
collapsing them early destroys the information that makes the model actionable.

| Currency | What it counts | Overnight recovery |
| --- | --- | --- |
| Physical | Active minutes weighted by demand: distance on foot, ascent, steps, standing, crowds | 55% |
| Transit | Time in motion weighted by mode and surface | 80% |
| Logistical | Transitions rather than time: check-ins, bag moves, mode switches, navigation | 95% |
| Circadian | Starts before 07:00, ends after 22:00, red-eyes, timezone shift | 35% |
| Exposure | Heat, rain, altitude and sun during hours actually spent outdoors | 70% |

Everything is denominated in effort-minutes, where one minute of unhurried sightseeing
costs 1. That makes five unlike things comparable and keeps the debugging read intuitive.

The owner's jeep case falls straight out of the mode table: 5 km of rough track at 14 km/h
costs more than 30 km of highway at 60 km/h, because the surface multiplier is 2.1 against
1.0. No model was consulted — the `surface` tag is already on the road in OpenStreetMap and
the rest is multiplication.

### Fatigue is a stock, not a flow

Per-day scoring rates three consecutive heavy days better than one brutal day with a light
one either side, which is exactly backwards. Each traveller has a daily capacity; each day
spends against it; each night repays part of the debt, unevenly, per currency. The
carry-forward is the same five-part vector and collapses to one figure only at comparison
time.

Three things this buys that per-day scoring structurally cannot:

1. It fires on the **right day** — usually the ordinary day after two heavy ones, not the
   heaviest day itself.
2. It puts the fix in the **right place** — the remedy for a bad day 4 is a slow morning on
   day 3.
3. It gives the trip a **shape** — rest-day placement, the hard hike early while fresh, the
   long transfer on the low-energy day.

**The risk, stated plainly.** The recovery coefficients are invented. There is no ground
truth for them, and a compounding model gets progressively wronger: ten per cent a day is a
wrong verdict by day five. The failure mode is confident nagging, which is worse than
silence.

**The mitigation.** Separate *having* the model from *giving it a voice*. Ranking uses the
carry-forward always — invisible, safe, immediately useful, and harmless when slightly
wrong. Speaking is rationed hard: **at most one statement per trip, at the single worst
point, and only when the debt is large and sustained across two or more consecutive days
over capacity.** Never marginal. All coefficients live in one named block so retuning is a
single edit.

**Why now rather than later.** Adding the carry-forward afterwards is a rewrite —
`score(day)` and `score(sequence)` are different shapes. Making it quieter afterwards is one
coefficient. So it ships in the first cut, nearly mute.

### Capacity comes from the party, not from taste

A five-year-old or a seventy-year-old shifts the physical weighting further than any
preference ever will, and `family` already carries this and is currently unused for it.
Capacity is the **minimum** across the party, never the average, because a party moves at
the pace of its most limited member. On this fixture that single choice is the difference
between the model saying nothing at all and the model saying one useful thing.

### Preferences without a learner

| Level | Source | Use |
| --- | --- | --- |
| Stated | About Me — "train over road", "no early starts" | Tilts a comfort factor. Never invents a constraint. |
| Party composition | `family` — ages, seniors, pace | Sets capacity, as above. |
| Revealed precedents | Each accepted alternative or undo, stored as a labelled pair | Cited, not fitted. ~50 a year is enough to say "last time you chose the train over a 06:00 flight"; it is nowhere near enough to fit weights, and silently drifting coefficients would be unexplainable. |

### Provenance decides how loudly a fact may speak

The engine owns the arithmetic; sourced facts fill typed slots; provenance governs the
volume. Much of what looks like "model intelligence" is actually structured data.

| Tier | Source | Cost | Rule |
| --- | --- | --- | --- |
| 0 · measured | Minutes, distances, opening hours, party, elevation, weather | Free, offline | Must produce a verdict on its own. |
| 1 · structured | OSM `surface`, `smoothness`, `highway=track`, steps, place details | Cached hard | Authoritative; changes once a decade. |
| 2 · inferred | Review text read by a model | Only for ambiguous places already in the plan, cached with `checked_on` | May lower a ranking or add a caveat. Never blocks, never phrased as certain. |

The guard degrades to *less insightful*, never to wrong and never to blocked.

**Reviews, kept in their place.** As a numeric input, review text is weak — reviewer
fitness and recency bias it badly, and an LLM labels almost everything "moderate walking".
Exactly one review signal is genuinely checkable and genuinely valuable: **how long people
say the visit takes**, compared with what we planned. That one becomes a flag. Everything
else read from reviews stays annotation text, never a term in the arithmetic.

### Weird is broader than tiring

Coherence checks that cost almost nothing and catch most of what reads as wrong. All of
them annotate; none of them refuse.

| Code | Check | Why it earns its place |
| --- | --- | --- |
| C1 | Wrong time of day | A sunset viewpoint at 11:00. Highest signal per line of code in the model. |
| C2 | Meal rhythm | A day that runs through lunch with no meal and no gap. |
| C3 | Backtracking | Crossing the city and coming back reads worse than the kilometres suggest. |
| C4 | Late night into early start | Two legal days that are illegal as a pair. |
| C5 | Anticlimax and whiplash | The headline sight on the departure day, or two headliners competing for one day. |
| C6 | Under-timed visit | Reviewers consistently say two hours; the plan allows forty-five minutes. |

### Comparative, never absolute

The public interface is `rank(options) -> ordered, with per-dimension deltas`, not
`score(day) -> number`. A lone absolute figure means nothing and invites the argument this
layer exists to avoid; a difference between two real choices is defensible and is what the
owner wanted to know. Property test: effort is **monotonic** — adding a stop or lengthening
a visit can never reduce it. Beyond that, a golden set of roughly fifteen hand-labelled
days ("brutal" / "fine") is worth more than any amount of weight tuning.

### No composite ever reaches the owner

Not "Day 3: 78", not "fatigue 62%", and **not gauges, progress bars or colour-coded
ratings** — those are numbers wearing a costume. But a measured quantity is not a score.
"Eleven kilometres on foot" is checkable, and it is exactly what a human planner says. Same
rule the document-readiness checks already follow: surface the measured quantity and the
comparison, never the composite.

- Good: *"Day 3 is your longest on foot — about 11 km, roughly double any other day."*
- Good: *"The train costs four hours more but saves an 04:30 start and a hotel night."*
- Bad: anything with a score, a bar, or a rating out of anything.

The composite stays inspectable for debugging in option C's plan console, behind a toggle
and labelled as engineering detail. It never appears in the normal flow.

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
8. Effort ranks and warns; it never blocks. Only an invariant may refuse a change.
9. No composite score, bar, gauge or rating reaches the owner — only measured quantities
   and comparisons.
10. The cumulative reserve informs every ranking but speaks at most once per trip, at the
    worst point.
11. A model-inferred fact may lower a ranking or add a caveat; it may never block and is
    never phrased as certain.

## Scope

- Changed experiment files:
  - `frontend/labs/lab-19-agentic-planning.html`
  - `frontend/labs/src/agentic-planning/main.tsx`
  - `frontend/labs/src/agentic-planning/AgenticWorkspace.tsx`
  - `frontend/labs/src/agentic-planning/planEngine.ts`
  - `frontend/labs/src/agentic-planning/effortModel.ts`
  - `frontend/labs/src/agentic-planning/effortModel.test.ts`
  - `frontend/labs/src/agentic-planning/effortFacts.ts`
  - `frontend/labs/src/agentic-planning/EffortPanels.tsx`
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
7. Read the effort table and confirm every owner-facing sentence names a quantity that can
   be checked against the itinerary, and that no composite, bar or rating appears outside
   the console's engineering toggle.
8. Compare the reserve for a solo traveller and for the same itinerary with a seven-year-old
   and confirm the model is silent in the first case and says exactly one thing in the
   second.
9. Confirm the one pacing statement lands on the day the debt catches up, and that its
   remedy points at an earlier day.
10. Confirm the ranked travel options state the longer wall-clock time before the advantage.

## Scorecard (1-5)

| Criterion | A · Proposal | B · Guarded | C · Console |
| --- | --- | --- | --- |
| Trust in a careless request | | | |
| Speed for a safe change | | | |
| Legibility of a refusal | | | |
| Collateral visibility | | | |
| Channel parity | | | |
| Cost in screen area | | | |
| Judgement without nagging | | | |
| Legibility without numbers | | | |

## Decision

- Decision: pending owner selection. Recommended starting point: **B · Guarded autonomy**,
  with C available as a toggle rather than a permanent panel.
- Implementation: not started; no production code changed by this Lab.
- Rationale: pending.
- Next action: owner selects an option in the Lab. Promotion should carry the plan engine
  and its invariants, not only the receipt and proposal UI — the defects live below the
  interface. The effort model may be promoted in the same change or deferred, but if it is
  promoted at all it must be promoted with the cumulative reserve: the carry-forward is a
  different shape from per-day scoring and retrofitting it is a rewrite.
