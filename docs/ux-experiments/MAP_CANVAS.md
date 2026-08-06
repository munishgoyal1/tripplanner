# Map canvas, reimagined

## Meta

- Branch: `agents/worker-2`
- Owner: Munish Goyal
- Date started: 5-Aug-2026
- Date ended: pending
- Status: In evaluation
- Lab: `http://127.0.0.1:5175/lab-18-map-canvas.html`
- Full-size preview: append `?preview=deck`, `?preview=dock`, `?preview=ribbon`, or `?preview=compose`

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
- **D · Search-first dock.** B's bottom dock without the resident stop list. A real search
  field lives in the dock at all times; type and target day appear only once a place is
  resolved; tapping a dashed pin — a place not yet in the trip — writes its name into that
  same field. The route timeline moves behind a *Sequence* toggle. *Exact delta:* keeps B's
  bottom placement without duplicating the itinerary, and makes the add affordance state its
  own behaviour.

### Open questions D answers

Raised by the owner after reviewing B, and unresolved by A, B or C:

1. **B's route timeline repeats the itinerary and eats the dock.** D drops it from the
   resting state and puts it behind a *Sequence* toggle in the same dock. The strip is
   identical when opened, so a sandbox round can settle whether it earns its space —
   especially when the map is maximised and the itinerary is not on screen.
2. **A button labelled *Add a place* does not say you can type into it.** The owner is
   right. That pill reads as *open a form* or *add something now*. D replaces it with a
   control that already looks like a search box — magnifier, placeholder, live results — so
   the affordance states its behaviour instead of promising it.
3. **A place picked on the map must feed the same composer, not a parallel one.** In D the
   dashed pins are places not yet in the trip; tapping one fills the search field and
   reveals type, day and Add. Typing and tapping become two ways to fill one control, so
   there is only ever one add flow to learn.

None of this is settled by the Lab. D exists so the bottom-bar placement can be kept while
the duplication and the add affordance are argued separately, and so the sandbox round has
something concrete to iterate on.

Each option is comparable against a *Compare with today* toggle, and a *Failure state*
toggle renders the load-failure message with its Retry affordance in any option.

## Required in every option

1. Day scope keeps *All days* plus every day, each in its own route colour.
2. Adding a place keeps all three inputs — free-text search, optional type, and target day
   including *Best day* — plus the Add action. An option may reveal them progressively, but
   none may be dropped.
3. The day context line keeps the day label, schedule duration, start and end with the
   `est.` marker, and route-only travel duration, distance and mode.
4. A selected pin keeps its photo, name, rating, address and *Open details*, plus move-day
   and remove for planned stops or day select and *Add to trip* for new ones.
5. Route colour and numbered markers keep matching the itinerary pane exactly.
6. The load-failure state keeps its message and Retry affordance.
7. An affordance must describe what it does: a control that accepts typing must look like it
   accepts typing.

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
7. In D, add a place by typing *market*, then clear it and add the same place by tapping its
   dashed pin; both should land in the same composer in the same state.
8. In D, toggle *Sequence* on and off with the itinerary visible, then again with the map
   maximised, and judge whether the strip is worth its space in either case.

## Scorecard (1-5)

| Criterion | A · Deck | B · Dock | C · Ribbon | D · Composer |
| --- | --- | --- | --- | --- |
| Map surface | | | | |
| Time to add a stop | | | | |
| Add affordance clarity | | | | |
| Day comprehension | | | | |
| Itinerary agreement | | | | |
| Duplication with the itinerary | | | | |
| Narrow-pane survival | | | | |

## Decision

- Decision: Option D · Search-first dock, built in a sandbox so the deferred questions can
  be judged on the real map instead of a fixture. The Lab still records the owner selection
  as pending; B's bottom placement is kept, and whether the sequence strip earns its space
  is exactly what the sandbox is for.
- Implementation: in sandbox `sbx-4-lab18-map` (branch `sandbox/4-lab18-map`), awaiting
  owner inspection. Production code touched: `frontend/src/components/MapPanel.tsx` (the
  whole command block moved below the map, so the map now starts at the top of the pane;
  the composer rests as a single search field and only reveals type, target day and Add
  once a place is named or resolved; a clear affordance resets the field and drops the
  candidate pin; a *Sequence* toggle opens the active day's stop order — marker, time, name
  and the travel duration between stops — as a horizontal strip, and tapping a card selects
  the pin and focuses the itinerary exactly like tapping the pin does).
- Facts preserved: day scope with *All days* and every day in its route colour, all three
  add-stop inputs including *Best day*, the auto-filled type marker, the day context line
  with schedule, `est.` marker and route-only travel, the day and pin context cards with
  with their actions, and the failure toast with Retry. Day scope now lives in the
  dock beside the sequence toggle rather than in the pane header, so every map
  command sits in one place under the map.
- Not carried over: the Lab's dashed discovery pins. Production already resolves a place
  by typing into the field or tapping a Google POI on the map — both fill the same
  composer — so a separate discovery layer would be new place data, which the Lab lists as
  a non-goal. The booking dot on the sequence strip is also absent because the map view
  model does not carry booking state.
- Rationale: the pane reads as a map with commands under it rather than a form with a map
  underneath, and the add affordance now looks like what it is.
- Next action: owner runs `.\scripts\sandbox\Run-Sandbox.cmd 4`, judges the map surface,
  the add flow and whether *Sequence* is worth its space, then promotes or discards.
