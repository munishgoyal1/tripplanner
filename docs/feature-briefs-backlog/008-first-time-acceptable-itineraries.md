# Brief 008 — First-time-acceptable itineraries: close the completion gate

## Document control

| Field | Value |
|---|---|
| Brief ID | `008` |
| Status | Draft — tier 1 in progress |
| Owner | Munish Goyal |
| Created | 2026-08-18 |
| Updated | 2026-08-18 |
| Baseline | `docs/REQUIREMENTS.md` |
| Target milestone | Accepted-as-delivered itineraries |
| Related capability IDs | PLAN-03, PLAN-04, ITIN-01, BOOK-01, PLACE-01 |
| Evidence | 68-trip corpus in `corpus/trips/`, audit inspector (brief `007`) |

## One-sentence requirement

As the traveller, I need the first itinerary the planner gives me to be one I can
accept and execute without editing it, so that the product earns its claim of
planning for me rather than drafting something I finish myself.

## Why now

The paid corpus reached 68 trips across 360 days, which is the first sample large
enough to measure what the planner actually ships rather than what it can ship.
Every trip has a real day-by-day itinerary with named stops, so the structural
work is done. What remains is the gap between *a plan* and *a plan someone would
book*, and it is measurable.

## Evidence

Measured over all 68 corpus trips by direct field reads. Percentages are of trips
unless stated otherwise.

| Defect | Trips | % |
|---|---|---|
| Days with fewer than two meals | 68 | 100% |
| No weather | 60 | 88% |
| No cost total or breakdown | 55 | 81% |
| Missing stop durations (167 stops) | 32 | 47% |
| International trip with no visa information | 28 | 41% |
| Itinerary names hotels, `selected_hotels` empty | 27 | 40% |
| Lodging that names no bookable property | 18 | 26% |
| `TBD` placeholders (128 stops) | 18 | 26% |

Per-day density across 360 days:

```
meals/day        0: 148 days (41%)   1: 171   2: 41
attractions/day  0:  59 days (16%)   1: 121   2: 109   3+: 71
hotels/day       0:   9 days          1: 163   2: 183   3: 5
```

## Root cause

The completion gate already exists and already asks for most of this.
`planning_completion_gaps` reports the gaps and `graph_policy` re-prompts the
agent to close them — but `MAX_INITIAL_ITINERARY_UPDATES = 2`, and when that
budget is exhausted `graph.trip_agent` instructs the model to *"give a concise
best-effort summary"* and *"state these unresolved details honestly"*.

So the gate does not fail closed. It gives up after two attempts and ships the
trip with its gaps narrated in prose. That single decision explains most of the
table above: the checks fire, nobody has to satisfy them.

Two consequences follow, and they need different fixes:

1. **Gaps the gate never detected.** Unbookable lodging was invisible because
   `_HOTEL_PLACEHOLDER_RE` only matched `tbd`, `hotel option` and
   `accommodation recommendation`. `Hotel in Kochi`, `Colombo Hotel` and
   `Accessible Hotel Kuala Lumpur` passed it and shipped.
2. **Gaps the gate detected and then abandoned.** `No concrete hotel is
   selected` has always been reported, and 40% of trips ship anyway.

## Scope

### Tier 1 — the plan cannot be executed as delivered

- **T1.1 Unbookable lodging is detected.** A stay that names only a lodging word,
  a describing adjective and a city is not a choice. *(implemented)*
- **T1.2 Lodging gaps fail closed.** A trip may not be presented as planned while
  any night resolves to no bookable property. Either bind a real property, or
  offer two or three named candidates and say so explicitly — never silence.
- **T1.3 `selected_hotels` agrees with the itinerary.** The structured selection
  and the day stops describe the same stays, since the selection is the booking
  handoff material.
- **T1.4 Every overnight day has somewhere to sleep.** Nine days currently have
  no lodging stop at all.

### Tier 2 — the plan forces the traveller to edit it

- **T2.1 Meal anchoring.** Every full day resolves lunch and dinner to a named
  place near that day's geographic cluster. Food-led trips get one signature meal
  per day.
- **T2.2 No empty days.** A day with no attraction is either filled or explicitly
  labelled as intentional rest.
- **T2.3 Cost is always answered.** Estimated total, per-person, and a
  stay/travel/food/activities split, each marked estimated or quoted. A traveller
  cannot accept a plan they cannot price.
- **T2.4 Durations on every visit**, so the day can be checked for overpacking.

### Tier 3 — trust

- **T3.1 Visa and entry requirements on international trips.**
- **T3.2 Seasonal and weather guidance**, especially for monsoon-sensitive trips.
- **T3.3 Remove duplicate lodging stops** — 183 days carry two.

## Non-goals

- Provider-side purchase, payment, or order management. Booking here continues to
  mean grounded choices and verified handoff material.
- Raising `MAX_INITIAL_ITINERARY_UPDATES` as the primary remedy. More model turns
  cost money per trip and do not make the gate deterministic. Prefer arithmetic
  repair, then a bounded ask, then an honest explicit gap.
- Reworking the corpus harness or the audit inspector, which brief `007` owns.

## Acceptance criteria

| ID | Criterion |
|---|---|
| AC-1 | A stay naming no bookable property is reported as a completion gap, with the affected days named. |
| AC-2 | Real property names are never reported. Pinned by corpus examples, both directions. |
| AC-3 | A trip with an unresolved lodging gap is not presented as planned. |
| AC-4 | `selected_hotels` and the itinerary's hotel stops cannot disagree on a saved trip. |
| AC-5 | The audit page shows, per rule, how many trips are affected and how that has moved since the previous audit. |
| AC-6 | A corpus-wide regression assertion fails if the placeholder or unbookable-lodging rate rises above its recorded baseline. |

## Validation

- Unit: `tests/test_unnamed_lodging.py` pins twelve unbookable and ten real
  property names taken verbatim from shipped corpus trips.
- Corpus: re-run `trip_audit` and compare rule counts against the recorded
  baseline in `corpus/audit-report.json`.
- Regression: the corpus-wide assertion in AC-6.

## Open owner decisions

1. When no real property can be grounded, should the planner offer named
   candidates and continue, or hold the trip as incomplete?
2. Is a day with no attraction acceptable when the traveller asked for relaxed
   pacing, or should it always be labelled explicitly as rest?
3. Should cost estimates appear when only rough price levels are known, marked as
   estimated, or be withheld until quotable?

## Status log

- 2026-08-18 — Brief created from the 68-trip corpus measurement. T1.1 implemented
  (`unnamed_lodging` in `trip_common`, wired into `_hotel_selection_warnings`);
  it flags 18 of 68 corpus trips with no false positives.
