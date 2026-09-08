# Feature 03 — Map-as-Editor

- **Pillars:** B (easy editing), A (breezy)
- **Status:** Proposed (extends `MAP-01` POI inspect/add into editing)
- **Size:** L · **Risk:** med · **Suggested lane:** Agent 1 (map) + Agent 2 (shared contract with Feature 02)

## The pain

The map is the dominant surface but is mostly read + add-stop. Users want to edit
spatially: "put this on Day 2," "reorder this loop," "this stop is out of the way."
Reasoning about geography on a list is harder than moving a pin.

## Outcome

The map becomes a first-class editor: click empty map or a labeled POI to inspect + add
(exists today), drag a pin to reorder its day circuit, and drag a pin onto a day selector
to move it across days — all with the same deterministic reflow and locks as the itinerary.

## Bounded v1

- **Drag a non-booked pin to reorder** within the selected day's circuit → retime.
- **Drag a pin onto a compact day rail** (D1..Dn shown during drag) → move to that day
  (move-day mutation).
- Keep existing click-to-inspect and Add stop; surface an inline "move to day" on the
  temporary place tile (partially present via the `Best day` selector).
- Booked pins, hotel endpoints (`H`), and airport (`A`) pins are locked.
- **Edits require selected-day mode**; all-days mode stays read-only for edits (too dense).

## UX

- Selected-day mode shows draggable numbered pins; a small day rail appears during drag as
  drop targets; drop → optimistic overlay update + authoritative reflow.
- Marker geometry (34×44), day color, and white border stay unchanged; only drag affordance
  is added.

## Implementation notes

- **Frontend:** `frontend/src/components/MapPanel.tsx` + `frontend/src/components/map/`
  (`overlaySync`); add marker drag handlers; reuse the same optimistic reducer path as
  Feature 02; share one mutation client. Requires overlay memoization (Feature 08) so drag
  stays smooth.
- **Backend:** same move-day + "set day order" contract as Feature 02; **no new endpoints.**
- **Coherence:** pin drag and itinerary drag call the identical mutation, so both panes converge.

## Perf / privacy / cost

Relies on Feature 08 overlay memoization to avoid full rebuilds during drag. No provider calls.

## Risks & mitigations

- **Dense/overlapping circuits and pin hit-testing** → restrict edits to selected-day mode;
  keep all-days read-only. Validate marker geometry and focus behavior unchanged. Med risk.

## Acceptance

- Pin reorder + cross-day move persist and match the itinerary exactly.
- Locked pins (booked/hotel/airport) are immovable.
- Edits only in selected-day mode; overlays stay smooth during drag.
