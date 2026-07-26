# Engineering Learnings

Durable architectural and travel-domain lessons learned while building tripplanner.
This is a joint working log for decisions that should shape future features and
fixes. Keep entries concise, generalizable, and tied to observed behavior.

## 2026-07-26 - Cross-Surface Interaction Consistency

- One conceptual action must have one owner-level behavior across every surface.
  A day click in Itinerary and a day click in Map both mean aggregate day-circuit
  focus: clear exact-place selection, activate that day, fit the full route, and
  place the itinerary at the start of the day-level summary.
- An all-days map action is aggregate trip focus: clear exact-place and
  single-day circuit state, fit every circuit, and place the itinerary at its
  trip-level summary. Model this as an explicit summary target, not a fake Day 0.
- Exact-place focus and aggregate day focus are mutually exclusive modes. Do not
  let a component invent a representative-place side effect for a day-level action.
- Selection styling must be exclusive and visually distinct from status styling.
  Warnings, booking state, and "In trip" state must not make multiple rows look
  selected; only the current exact occurrence receives the selected card/marker
  treatment.
- When adding an interaction available in multiple panes or form factors, verify
  the same acceptance matrix everywhere: owning state, map viewport, itinerary
  current row, Details context, desktop wiring, and mobile wiring.
- Prefer shared App/workspace handlers over parallel component-local semantics.
  Local state may render the action, but it must not redefine what the action means.

## 2026-07-26 - Itinerary Chronology Is One Contract

- Persisted stop-array order, displayed visit times, itinerary numbering, and map
  circuit order are four views of the same schedule. Validate them together.
- Route optimization or cross-day reflow invalidates old time slots. Reorder meals
  and visits coherently, then recompute times with duration and transfer buffers;
  never preserve stale times on moved stops.
- Reject model-authored duplicate or backwards visit times atomically. A warning
  after saving is too late because every downstream view will faithfully render
  contradictory source data.
- Provider-canonical place names may not match itinerary text. Route completion
  must use authoritative occurrence day/stop identity, not global pin insertion
  order, so name enrichment cannot reorder a circuit.

## 2026-07-26 - Persisted Services Need Runtime-State Recovery

- A persisted database volume can retain process locks after an abrupt container
  stop even when its data is healthy. Readiness must distinguish stale runtime
  state from corrupt data instead of waiting repeatedly or resetting the volume.
- PostgreSQL lock cleanup is safe only after proving no server process exists.
  Remove the complete runtime lock set, restart once, and preserve all database
  files; never turn automatic local startup into automatic data deletion.
