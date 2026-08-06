# Itinerary canvas, reimagined

## Meta

- Branch: `agents/worker-2`
- Owner: Munish Goyal
- Date started: 5-Aug-2026
- Date ended: pending
- Status: In evaluation
- Lab: `http://127.0.0.1:5175/lab-17-itinerary-canvas.html`
- Full-size preview: append `?preview=spine`, `?preview=cards`, or `?preview=editorial`

## Hypothesis

The itinerary pane knows a great deal about each stop and prints all of it at the same
volume. A single stop can carry a timing label, a start time, an estimate marker, a visit
duration, a leave time, a travel mode with distance, duration, detail, estimated arrival
and a buffer or conflict, a booking state, a cost, opening hours, a rating with review
count, a must-visit score, a concern, a note and an insight. Stacked as uniform rows, a
five-day plan becomes a wall of true statements that is slow to scan and does not feel
like a product a hundred million people would enjoy using.

If the same facts are re-ranked — a small number always loud, the rest quiet or opened in
place — then the plan reads at a glance while remaining complete, and the pane starts to
feel considered rather than merely thorough.

## Variants

- **A · Journey spine.** One continuous time rail runs the length of the day. The time
  column sits outside the rail, markers sit on it, and travel legs sit on the line between
  stops. *Exact delta:* the day reads as a single movement; the rail permanently costs
  about 5 rem of horizontal space.
- **B · Layered stop cards.** Each stop is a calm card on a `surface` background. Time,
  name and booking state are the only always-loud facts, secondary facts collapse into one
  chip row, and notes and insights open in place under *Notes & tips*. Concerns never
  collapse. *Exact delta:* fastest to scan; long-form guidance is one click away.
- **C · Editorial agenda.** Fraunces day titles with Morning, Afternoon and Evening
  chapters. Every secondary fact for a stop is compressed into a single interpunct meta
  line. *Exact delta:* most elegant to read end to end; densest single line of facts.

Each option is comparable against a *Compare with today* toggle that renders the current
production presentation from the same fixture.

## Required in every option

1. Every stop fact listed in the hypothesis is present, including estimated-time markers,
   travel detail, estimated arrival, and the buffer or conflict after a leg.
2. Every day keeps its date, title, weather with rain probability, summary, planned stop
   count, schedule duration and span, day travel total, confirmed and to-book counts,
   travel rhythm, and the *Open route* link.
3. The trip header keeps destination, origin, dates, travelers, status, total cost against
   target, readiness, counts, weather, packing, family pills, constraints and budget.
4. Booking status, remove, and show-on-map stay reachable from the row itself.
5. Concerns are never hidden behind a disclosure.

## Scope

- Changed experiment files:
  - `frontend/labs/lab-17-itinerary-canvas.html`
  - `frontend/labs/src/itinerary-canvas/main.tsx`
  - `frontend/labs/src/itinerary-canvas/ItineraryCanvas.tsx`
  - `frontend/labs/src/itinerary-canvas/TripHeader.tsx`
  - `frontend/labs/src/shared/tripFixture.ts`, `WorkspaceFrame.tsx`, `StylizedMap.tsx`
  - `frontend/labs/src/shared/labRecords.ts`, `LabScope.tsx`, `vite.config.ts` (registration)
- Related production code, read but not modified:
  - `frontend/src/components/ItineraryStopRow.tsx` — the full fact inventory per stop.
  - `frontend/src/components/ItineraryPanel.tsx` — the day card and its meta block.
  - `frontend/src/components/TripSnapshot.tsx` — the always-expanded trip header sections.
- Non-goals: persisted stop order, booking semantics, itinerary mutation logic, the trip
  agent, Map and Details content design.

## Interaction intent

The owner should be able to open the pane and answer three questions without scrolling
twice: what is happening today, what is at risk, and what still needs booking. Everything
else is reference material that should be available in one gesture and silent until then.

## Test scenarios

1. Find Belém Tower on Day 3 and confirm it is not booked. Count the interactions.
2. Confirm the 16-minute ferry conflict on Day 3 is visible without any click.
3. Scroll from Day 1 to Day 4 and compare the distance travelled against today's baseline.
4. Narrow the browser until the itinerary pane is about 20 rem and re-check both above.
5. Read the pane beside the toolbar and Map and judge whether it belongs to the same app.

## Scorecard (1-5)

| Criterion | A · Spine | B · Cards | C · Editorial |
| --- | --- | --- | --- |
| Time to find one stop | | | |
| Risk visibility | | | |
| Vertical cost | | | |
| Calm at density | | | |
| Theme fit | | | |

## Decision

- Decision: Option B · Layered stop cards, built in a sandbox for hands-on judgement. The
  Lab still records the owner selection as pending; B was the recommended starting point
  and scored 87/100 against A (74) and C (68) in the cross-lab contrast.
- Implementation: in sandbox `sbx-1-lab17-canvas` (branch `sandbox/1-lab17-canvas`),
  awaiting owner inspection. Production code touched:
  `frontend/src/components/ItineraryStopRow.tsx` (each stop is now a card; time, name and
  booking state are the only always-loud facts; timing label, kind, visit or transfer
  duration and the leave time moved into one quiet meta line; cost, opening hours, rating
  and must-visit score stay in the chip row; notes and insights open in place behind
  *Notes & tips*; map and remove reveal on hover from `sm` upward and stay visible on
  touch widths) and `frontend/src/components/ItineraryPanel.tsx` (the day's stop list is a
  spaced list on `surface` instead of divided rows, and the transition-day rail is gone
  because the cards no longer share a time gutter).
- Facts preserved: every stop, day and trip fact listed above still renders. Concerns are
  never collapsed, the estimated-time marker, travel detail, estimated arrival and the
  buffer or conflict still print above the card, and no new colour was introduced.
- Not carried over: the Lab's flat sticky day header. The production day card keeps its
  labelled meta block (`Schedule duration:`, `Day's travel:`, `Travel rhythm:`) because
  that is shared by all three options rather than what distinguishes B, and it is covered
  by existing tests. It can follow in the same sandbox if the owner wants it.
- Rationale: the pane reads at a glance — what is happening, what is at risk, what still
  needs booking — while long-form guidance stays one click away instead of always printed.
- Next action: owner runs `.\scripts\sandbox\Run-Sandbox.cmd 1`, inspects the itinerary
  pane (including at about 20 rem wide), then promotes or discards the sandbox.
