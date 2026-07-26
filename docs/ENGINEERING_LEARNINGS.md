# Engineering Learnings

Durable architectural and travel-domain lessons learned while building tripplanner.
This is a joint working log for decisions that should shape future features and
fixes. Keep entries concise, generalizable, and tied to observed behavior.

## 2026-07-26 - Cross-Surface Interaction Consistency

- One conceptual action must have one owner-level behavior across every surface.
  A day click in Itinerary and a day click in Map both mean aggregate day-circuit
  focus: clear exact-place selection, activate that day, and fit the full route.
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
