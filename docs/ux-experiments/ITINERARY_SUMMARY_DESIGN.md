# Experiment: Itinerary Summary Design

## Meta

- Surface: `frontend/summary-lab.html`
- Isolated build: `npm --prefix frontend run build:ux-lab`
- Paired row treatment: B - Compact agenda
- Owner: Munish Goyal
- Date started: 2026-07-29
- Status: testing

## Hypothesis

A Narrative Brief should explain the purpose and rhythm of the day before the
user reads the schedule while keeping route, travel, and booking readiness easy
to scan. The remaining choice is how editorial or compact that brief should be.

## Variants

### A - Editorial brief

A spacious narrative opening gives the day's character the most authority.
Route, metrics, readiness, and travel rhythm follow as quiet supporting lines.
This is the calmest and most travel-editorial option.

### B - Balanced brief

Narrative still leads, followed by one framed journey line that pairs transport
guidance with compact route and booking signals. This keeps the original brief's
tone while making logistics easiest to distinguish.

### C - Compact brief

The narrative becomes a short sentence inside a denser day header. Metrics,
transport, booking gaps, and guidance share one compact supporting line. This
preserves more vertical space for the agenda, especially on mobile.

## Shared decisions under test

- Show weekday and full date as the day identity.
- Keep Open route visible without competing with the title.
- Distinguish itinerary narrative from transport guidance.
- Show booking readiness at day level without duplicating every row action.
- Pair every variant with Compact Agenda so the two choices can be evaluated as
  one hierarchy.

## Data boundary

The current contract provides date, title, summary, stops, booked count, route
metrics, reachability, and route URL. All three revised variants stay within
that boundary and require no new structured caution or transport data.

## Test scenarios

1. Explain the day's purpose and intensity in under five seconds.
2. Find Open route without scanning the stop list.
3. Identify whether bookings remain incomplete.
4. Distinguish transport guidance from the narrative plan.
5. Verify the summary leads naturally into Compact Agenda on mobile and desktop.

## Scorecard

Rate each variant from 1-5 for day comprehension, action visibility, travel
clarity, visual calm, and mobile fit. Scores stay in browser local storage.

## Decision

- Decision: pending owner selection
- Current comparison focus: three modifications of Narrative Brief B
- Next action: select a summary variant, then implement it together with Compact
  Agenda in the production itinerary.