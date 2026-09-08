# Experiment: Trip snapshot hierarchy

## Meta

- Owner: Munish Goyal
- Date started: 2026-07-31
- Status: implemented
- Lab: `http://127.0.0.1:5175/lab-6-trip-snapshot.html`

## Variants

- **A - Scan ledger:** dense facts remain visible in a stable horizontal hierarchy.
- **B - Decision brief:** identity, readiness, weather, and budget form one compact planning brief.
- **C - Progressive summary:** secondary planning context expands on demand.

## Decision

- Decision: **B - Decision brief**
- Production status: implemented on 2026-07-31.
- Traveler context is part of trip identity, followed by an authored trip-level
  narrative when available and a factual generated summary for older trips.
- Booking readiness remains explicit.
- Days, Stay, Places, and Flights use one compact one-line facts row.
- Persisted weather renders its source, day conditions, temperatures, and packing
  guidance. Older trips without weather retain a visible, truthful unavailable state
  rather than silently dropping the Weather section.
- Family/preference context, constraints, and Budget retain their existing data and behavior.
- The prototype's generic Trip fit line below Budget is intentionally omitted. Its
  useful evidence already appears as specific family/preference and constraint data;
  repeating a vague summary added no distinct decision support.
- Day briefs, itinerary stop rows, Map, Details, Assistant, and mobile behavior are unchanged.

## Validation

- Focused ItineraryPanel suite: 13 tests pass.
