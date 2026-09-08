# Compact Itinerary Density UX Lab

**Status:** Completed and implemented
**Selected direction:** B - Circuit header, adapted to preserve production detail

## Decision boundary

This Lab changes only itinerary day density and repeated hotel endpoint presentation.

The following remain fixed:

- Stop order, route endpoints, occurrence identity, names, and times.
- Travel estimates, visit duration, booking state, ratings, notes, concerns, and actions.
- Trip snapshot, day brief categories, Map, Details, and Assistant behavior.

## Options

- **A - One-line ledger:** maximum simultaneous detail with both hotel endpoints as rows.
- **B - Circuit header:** one day-level hotel presentation for an identical departure and return stay.
- **C - Progressive focus:** quiet default rows with selected-stop disclosure.

The Lab is available at `http://127.0.0.1:5175/lab-11-itinerary-density.html`.

## Implementation

Production keeps the current detailed Compact Agenda and tightens its vertical spacing.
When a day starts and ends at the same normalized hotel, one combined hotel row shows
both Depart and Return timing while the two underlying route endpoints remain intact.
The row retains the return leg's travel and arrival evidence and remains focusable from
either occurrence. When endpoint hotels differ, both remain visible as explicit Check
out and Check in rows.
