# Experiment: Trip snapshot hierarchy

## Meta

- Owner: Munish Goyal
- Date started: 2026-07-31
- Status: implemented
- Lab: `http://127.0.0.1:5175/trip-snapshot.html`

## Variants

- **A - Scan ledger:** dense facts remain visible in a stable horizontal hierarchy.
- **B - Decision brief:** identity, readiness, weather, and budget form one compact planning brief.
- **C - Progressive summary:** secondary planning context expands on demand.

## Decision

- Decision: **B - Decision brief**
- Production status: implemented on 2026-07-31.
- Traveler context is part of trip identity, followed by explicit booking readiness.
- Days, Stay, Places, and Flights use one compact one-line facts row.
- Weather, packing guidance, family/preference context, constraints, and Budget retain
  their existing data and behavior.
- The prototype's generic Trip fit line below Budget is intentionally omitted. Its
  useful evidence already appears as specific family/preference and constraint data;
  repeating a vague summary added no distinct decision support.
- Day briefs, itinerary stop rows, Map, Details, Assistant, and mobile behavior are unchanged.

## Validation

- Focused ItineraryPanel suite: 12 tests pass.
