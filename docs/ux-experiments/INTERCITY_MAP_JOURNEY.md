# Experiment: Complete inter-city travel on the Map

## Meta

- Owner: Munish Goyal
- Date started: 2026-08-01
- Status: implemented
- Lab: `http://127.0.0.1:5175/intercity-map.html`

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

## Selected direction

**A - Connected day journey**. It makes completeness visible without requiring
another control and gives the Map the same authoritative day sequence as the
itinerary.

The production handoff is intentionally limited to the selected option:

- Preserve every mappable transfer-day endpoint in itinerary order and fit the
  complete open journey when that day is selected.
- Keep local legs in the day color and distinguish solid road, dashed rail, and
  dotted flight connectors. Flight and rail terminal pins remain informational.
- Continue using endpoint-based geodesic estimates; do not add a billed route
  provider, a journey strip, or route-layer controls.
- Preserve ordinary sightseeing days as closed hotel circuits.

## Decision

- Decision: Option A approved by the owner on 2026-08-02
- Owner modifications: none
- Production implementation status: implemented
- Validation: focused road, rail, and flight view-model tests plus the MapPanel unit suite
