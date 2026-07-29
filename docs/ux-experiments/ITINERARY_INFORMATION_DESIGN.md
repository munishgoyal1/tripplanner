# Experiment: Itinerary Information Design

## Meta

- Surface: `frontend/ux-lab.html`
- Isolated build: `npm --prefix frontend run build:ux-lab`
- Owner: Munish Goyal
- Date started: 2026-07-29
- Status: preferred candidate selected; pairing decision pending

## Hypothesis

Itinerary rows will be easier to understand when booking state is an explicit
action rather than a checkbox, transport appears between the places it connects,
the weekday is visible beside the date, and travel guidance is separated from
the day narrative with clear labels.

## Variants

### A - Journey timeline

Transport is a visual connector between place cards. This best communicates the
sequence `place -> travel -> place` and is the recommended starting direction.
It uses more vertical space than the other variants.

### B - Compact agenda

Time is the dominant left column and transport is embedded above the destination.
This supports fast scanning and higher information density, but explanatory
content has less room.

### C - Guided place cards

Each place has explicitly labeled Travel, Time here, and Plan sections. This is
the most self-explanatory treatment for first-time use, but it is the tallest
and can feel repetitive during long trips.

## Shared decisions under test

- Replace checkbox semantics with a `Confirmed` / `Needs booking` status action.
- Label each visit's absolute clock time as `Arrive` and its planned dwell
  duration as `Stay` or `Planned stay`. Label hotel endpoints as `Depart` and
  `Return` instead of implying time spent there.
- Show weekday and full date together.
- Surface estimated mode, duration, distance, and short guidance for every leg.
- Label day-level prose as `Getting around` and `Day overview`.
- Keep map marker identity, time, place name, duration, and booking state easy to
  scan without opening Details.

## Data boundary

The current itinerary contract exposes estimated `walk`, `local transit`, and
`car transfer` modes derived from straight-line distance. The experiment uses
more concrete Metro, bus, and taxi examples to test information design only.
Shipping those exact labels requires either agent-authored structured guidance
or a verified Google Routes transit-mode enhancement. Until then, production
copy must say `estimated` and must not invent line numbers, bus numbers, fares,
or live schedules.

## Test scenarios

1. Find the next destination and how to reach it in under five seconds.
2. Identify which stops still need a reservation without interpreting a form
   checkbox.
3. Distinguish day transport advice from the day narrative without reading both.
4. Scan the full day on a narrow mobile viewport.
5. Distinguish suggested arrival time from planned time at a stop without
  inferring their meaning from position.
6. Compare a hotel endpoint, attraction, meal, and return leg.

## Scorecard

Rate each variant from 1-5 for scan speed, transport clarity, booking clarity,
information hierarchy, and mobile fit. The lab stores scores only in browser
local storage.

## Decision

- Preferred candidate: B - Compact agenda
- Final decision: pending pairing with an itinerary-summary treatment
- Next action: choose a summary variant in the separate summary lab, then
  normalize real-data wording and update the production ItineraryPanel plus its
  backend/frontend contract tests as one coherent change.