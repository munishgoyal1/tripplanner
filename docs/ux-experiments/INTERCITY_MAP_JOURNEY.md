# Experiment: Complete inter-city travel on the Map

## Meta

- Owner: Munish Goyal
- Date started: 2026-08-01
- Status: implemented
- Lab: `http://127.0.0.1:5175/lab-14-intercity-map.html`

## Problem

The persisted itinerary retains the full checkout-transfer-check-in sequence,
but the production Map deliberately limits a transfer day to local geometry on
one side and filters airports, rail stations, and bus terminals out of its path.
The selected day can therefore look incomplete or imply that distant stay
endpoints are unrelated.

Ordinary sightseeing days must remain closed hotel circuits. A genuine transfer
day is instead an open endpoint-to-endpoint journey: origin local travel,
inter-city movement, then destination local travel. Road can use a continuous
path, rail should expose stations and rail treatment, and a flight needs airport
transfers around a visually distinct airport-to-airport arc.

## Scope

- Compare complete dual-scale framing, a journey strip above a local map, and
  independently controllable local and inter-city layers.
- Switch among realistic road, rail, and flight geometry in every option.
- Preserve itinerary facts, place order, route providers, geocoding, mutations,
  and ordinary closed hotel circuits as context only.

## Variants

- **A - Connected day journey:** fit both city contexts, local circuits, and the
  inter-city movement in one complete selected-day map, without B's separate
  summary strip or C's visibility controls.
- **B - Journey strip and local map:** keep the destination map at a useful local
  scale while a pinned strip preserves the complete stay-to-stay journey. The
  origin circuit leaves the canvas and no route-layer controls are added.
- **C - Optional inter-city layer:** show local and inter-city geometry together
  by default, with separate visibility controls for each scale. Unlike B, the
  inter-city leg remains geometry on the dual-scale map.

## How to review the Lab

The Lab renders each option inside a production-scale workspace shell (command
bar, itinerary rail, map canvas, route rail) so an option is judged in the
context it would ship into, not as an isolated map card.

- **Measured improvement band.** Stops reaching the map, route legs drawn,
  terminal pins, and city contexts are counted from the same fixture that both
  previews render, so the gain is verifiable rather than asserted.
- **Baseline comparison.** `Compare with today` renders today's production
  behavior beside the option. The itinerary rail flags every stop the current Map
  drops with `Not on the map`, which is the concrete thing this Lab removes.
- **Five scenarios.** Road with on-route stops, rail with stations, flight with
  airports, a departure day with no destination stop, and an ordinary
  sightseeing day.
- **Regression guard.** The ordinary sightseeing day must render identically
  before and after in every option: no journey strip, no layer controls, no
  reframing, no restyling. An option that changes it fails.
- **Full size.** `?preview=<full-journey|journey-strip|layer-toggle>&scenario=<road|rail|flight|departure|ordinary>`
  opens one option full window.

## Evaluation criteria

1. Can the complete transfer day be read without leaving the Map?
2. Is road, rail, or flight identifiable without reading the itinerary?
3. Does the destination stay work remain usable at a normal working scale?
4. Does an ordinary sightseeing day stay exactly as it is today?

## Non-goals

- No billed routing provider; travel facts stay endpoint-based estimates.
- Terminal pins are informational only and are not selectable place stops.
- No change to itinerary order, timing, persistence, or mutation behavior.
- No change to ordinary closed hotel circuits.

## Lab source

- `frontend/labs/src/intercity-map/scenarios.ts` - fixtures and derived counts
- `frontend/labs/src/intercity-map/JourneyMap.tsx` - data-driven mock canvas
- `frontend/labs/src/intercity-map/IntercityWorkspace.tsx` - workspace shell
- `frontend/labs/src/intercity-map/main.tsx` - Lab page

## Selected direction

**A - Connected day journey, with local selected-day framing**. It makes
completeness visible without another control and gives the Map the same
authoritative day sequence as the itinerary, while avoiding an unusably broad
viewport for normal destination work.

The production handoff is intentionally limited to the selected option:

- Preserve every mappable transfer-day endpoint in itinerary order and render the
  complete open journey when that day is selected.
- Frame the useful destination airport-to-stay circuit on arrival days. When no
  substantive destination stop remains, frame the origin stay-to-airport circuit.
- Keep local legs in the day color and distinguish solid road, dashed rail, and
  dotted flight connectors. Flight and rail terminal pins remain informational.
- Continue using endpoint-based geodesic estimates; do not add a billed route
  provider, a journey strip, or route-layer controls.
- Preserve ordinary sightseeing days as closed hotel circuits.

## Decision

- Decision: Option A approved by the owner on 2026-08-02
- Owner modification: retain complete connected geometry, but use local
  destination- or origin-side framing for selected transfer days
- Production implementation status: implemented
- Validation: focused road, rail, and flight view-model tests plus the MapPanel unit suite
- Lab lifecycle note: the machine handoff record still reads `ready`, so the Lab
  page shows `In progress`. It needs the owner's `Implemented - To be reviewed`
  disposition to match this document.
