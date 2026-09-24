# Experiment: Honest gaps — show what the plan has not decided

## Meta

- Lab: #32 (`honest-gaps`)
- Page: `frontend/labs/lab-32-honest-gaps.html`
- Branch: `claude/sleepy-pasteur-emvqf8`
- Owner: `munish`
- Date started: `2026-09-23`
- Date ended: `pending`
- Status: `testing`

## Hypothesis

The offline evaluation of 2026-09-23 (owner `/evals` console, report
`src/tripplanner/evals/owner_report.json`) judged twelve committed corpus trips
against rubric `itinerary-v1`. Every one of them still held something the planner had
not decided, and deterministic probes over all 178 corpus trips measured the same
thing at scale: 75 trips carry 544 placeholder stops ("Hotel (TBD)", "Lunch (TBD)",
"Local restaurant Jaipur"), 88 carry no priced item at all, and 9 of the 13 trips with
a selected flight hold a provider test-mode fare.

Production draws each of those exactly like a chosen place. A placeholder meal gets a
time, an icon and a confident map pin (the committed place cache resolves
"Beachside dining (TBD)" in Goa to Tereza Beach House). The traveller cannot tell a
guess from a decision, so the plan looks finished when it is not.

The Lab's claim is that the workspace should treat an undecided stop as an open
decision: visibly different, never pinned, counted, and closable in one tap. What is
uncertain is where those decisions gather.

## Options

Letters follow the fit score in `OptionContrast.tsx`.

| Option | Where the gaps live | Fit |
| --- | --- | --- |
| A · Decision inbox | A pinned bar above the days counts every open decision and expands into one list with three suggestions each and Choose myself. Placeholder rows are dashed. | 88 |
| B · Inline slots | Each placeholder becomes a dashed slot inside its own day with suggestion chips; day headers carry a count. | 81 |
| C · Readiness checklist | Details gains a Plan readiness checklist by Stay, Meals, Journeys and Prices; rows only gain a hollow marker. | 67 |
| D · Assistant follow-up | One Assistant message lists the gaps as chips; no pane changes. | 52 |

The recommended build pairs A's count and list with B's in-day slot once a traveller
opens a day.

## Scope

Changed files:

- `frontend/labs/lab-32-honest-gaps.html`
- `frontend/labs/src/honest-gaps/{fixture.ts,options.ts,main.tsx,styles.css,main.test.tsx}`
- `frontend/labs/src/shared/{labRecords.ts,LabScope.tsx,OptionContrast.tsx}`
- `frontend/labs/vite.config.ts`

Non-goals:

- No production UI, backend, planner or data-contract change.
- The Lab does not decide how the agent fills a gap, only how a gap is presented and
  how the traveller asks for it to be filled.
- Suggestions in the fixture are illustrative, not verified availability.

## Fixture

The committed corpus trip `corpus/trips/goa-relaxed.json`, placeholders unchanged: one
TBD hotel on all four days, five TBD meals, an untimed outbound flight and a
"Nuitée Air" sandbox return fare. *Compare with today* shows today's rendering,
including the wrong map pin.

## Further improvements from the same review

The Lab page ranks six follow-up candidates with their evidence; they are not
options in this Lab. In order: never pin a guessed place (11.3% of cached lookups
share no word with the stop name); show the day in the order it happens (95 trips
list a hotel after the day's departure); rebuild day summaries from stops (10 trips
contradict themselves); say when a trip is unpriced; echo each explicit request ask as
Met, Not yet or Dropped; and show nights used against nights booked (20 trips keep a
night after departure).

## Test Scenarios

1. Resolve three gaps in each option; the row, the count and the map note update.
2. Toggle *Compare with today*; placeholders read as ordinary stops and one is pinned.
3. Switch to Mobile; the inbox, slots, checklist and conversation remain reachable.

## Decision

Pending owner review.
