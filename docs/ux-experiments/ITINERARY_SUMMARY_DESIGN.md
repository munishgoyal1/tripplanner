# Experiment: Itinerary Summary Design

## Meta

- Surface: `frontend/summary-lab.html`
- Isolated build: `npm --prefix frontend run build:ux-lab`
- Paired row treatment: B - Compact agenda
- Owner: Munish Goyal
- Date started: 2026-07-29
- Status: testing

## Hypothesis

A day summary should answer four questions before the user reads the schedule:
what kind of day is this, how demanding is it, how will I get around, and what
still needs attention. Separating these concerns should make the itinerary more
useful than presenting route facts, reachability, and narrative as similar text.

## Variants

### A - Operational overview

A facts grid leads with stops, planned time, travel, and confirmation progress.
Getting around and Day overview remain distinct labeled sections. This is the
most balanced and scannable option.

### B - Narrative brief

The purpose and rhythm of the day lead in editorial prose, followed by a compact
facts line and travel note. This feels calmer and more inspiring, but booking
readiness is less prominent.

### C - Action strip

Open route, booking gaps, and cautions become the dominant interactive band.
This is the most operational option, but it can make a normal day feel like an
exception dashboard.

## Shared decisions under test

- Show weekday and full date as the day identity.
- Keep Open route visible without competing with the title.
- Distinguish itinerary narrative from transport guidance.
- Show booking readiness at day level without duplicating every row action.
- Pair every variant with Compact Agenda so the two choices can be evaluated as
  one hierarchy.

## Data boundary

The current contract provides date, title, summary, stops, booked count, route
metrics, reachability, and route URL. Variant C demonstrates a named timing
caution and the exact unbooked places; production can derive booking gaps from
stops, but named cautions require structured concern aggregation rather than
invented copy.

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
- Recommended starting candidate: A - Operational overview
- Next action: select a summary variant, then implement it together with Compact
  Agenda in the production itinerary.