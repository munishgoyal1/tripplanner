# Map canvas, reimagined

## Meta

- Branch: `agents/worker-2`
- Owner: Munish Goyal
- Date started: 5-Aug-2026
- Date ended: pending
- Status: In evaluation
- Lab: `http://127.0.0.1:5175/lab-18-map-canvas.html`
- Full-size preview: append `?preview=deck`, `?preview=dock`, or `?preview=ribbon`

## Hypothesis

The Map pane spends roughly a fifth of its height on chrome before a single pin is drawn:
a day-scope row, an add-stop row carrying a search field, a type select, a day select and
an Add button, and a third line of day context. All of it is useful, none of it is
geography, and the result reads as a form with a map underneath rather than a map.

If the same controls are re-placed — floated, docked, or compressed into one command row —
the pane can give far more of itself to the route while keeping every control, fact and
state the production map already provides. A dock can go further and let the map itself
carry the day's sequence, which is the one thing a map is uniquely good at showing.

## Variants

- **A · Floating deck.** The map runs edge to edge. Day scope, search and the day's facts
  float as glass cards over it. *Exact delta:* the most map per pixel; floating chrome can
  cover pins when the pane is narrow.
- **B · Route dock.** The map stays clean while a dock at the bottom carries day tabs, the
  day's schedule and travel facts, and a horizontal timeline of every stop with its time,
  marker, booking dot and travel leg. Search collapses to one *Add a place* button that
  opens in place. *Exact delta:* turns the map into a route-planning surface at a cost of
  about 7 rem at the bottom.
- **C · Command ribbon.** Today's three stacked rows collapse into one command row plus a
  single day-coloured fact ribbon, and the map takes everything below. *Exact delta:* the
  smallest change from today and the safest to ship; adds no new capability.

Each option is comparable against a *Compare with today* toggle, and a *Failure state*
toggle renders the load-failure message with its Retry affordance in any option.

## Required in every option

1. Day scope keeps *All days* plus every day, each in its own route colour.
2. Adding a place keeps all three inputs — free-text search, optional type, and target day
   including *Best day* — plus the Add action.
3. The day context line keeps the day label, schedule duration, start and end with the
   `est.` marker, and route-only travel duration, distance and mode.
4. A selected pin keeps its photo, name, rating, address and *Open details*, plus move-day
   and remove for planned stops or day select and *Add to trip* for new ones.
5. Route colour and numbered markers keep matching the itinerary pane exactly.
6. The load-failure state keeps its message and Retry affordance.

## Scope

- Changed experiment files:
  - `frontend/labs/lab-18-map-canvas.html`
  - `frontend/labs/src/map-canvas/main.tsx`
  - `frontend/labs/src/map-canvas/MapCanvas.tsx`
  - `frontend/labs/src/shared/StylizedMap.tsx`, `tripFixture.ts`, `WorkspaceFrame.tsx`
  - `frontend/labs/src/shared/labRecords.ts`, `LabScope.tsx`, `vite.config.ts` (registration)
- Related production code, read but not modified:
  - `frontend/src/components/MapPanel.tsx` — the day-scope row, add-stop row, context line,
    floating context card, pin card and failure toast.
- Non-goals: Google Maps implementation, provider search, geocoding, place data, route
  computation, and any trip mutation behavior.

## Interaction intent

The map is where a day stops being a list and becomes a shape. Chrome should be present
when reached for and quiet otherwise, and the pane should answer "does this day make
geographic sense" before it answers anything else.

## Test scenarios

1. Scope to Day 3 and judge how much of the pane is geography in each option.
2. Add a place to Day 2 and count the interactions from intent to Add.
3. Select the Belém Tower pin and confirm every pin-card fact and action is present.
4. Toggle the failure state in each option and confirm the message and Retry stay usable.
5. Narrow the window until Map is the secondary pane and repeat steps 1 and 2.
6. Compare a pin's colour and number against the same stop in the itinerary pane.

## Scorecard (1-5)

| Criterion | A · Deck | B · Dock | C · Ribbon |
| --- | --- | --- | --- |
| Map surface | | | |
| Time to add a stop | | | |
| Day comprehension | | | |
| Itinerary agreement | | | |
| Narrow-pane survival | | | |

## Decision

- Decision: pending owner selection.
- Implementation: not started; no production code changed by this Lab.
- Rationale: pending.
- Next action: owner selects an option in the Lab; the selection is then promoted with its
  defining interaction behavior intact, not only its visual shell.
