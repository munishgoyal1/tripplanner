# Map Panel Controls UX Lab

**Status:** Active experiment  
**Lab:** `http://127.0.0.1:5175/map-controls.html`  
**Production impact:** None until an option is explicitly selected and approved

## Question

How should Map organize day scope, Add stop, and route context without stacking
several equal-weight command rows or mixing full-day schedule time with route-only
travel evidence?

## Preserved Behavior

- **All days** is aggregate trip focus: clear exact-place and one-day focus, fit
  every circuit, and target the itinerary trip summary.
- **Day N** is aggregate day focus: clear exact-place focus, fit that complete
  circuit, and target the matching itinerary day summary.
- Selecting a pin is exact occurrence focus and is visually distinct from either
  aggregate mode.
- The active day seeds Add stop placement, while All days defaults to Best day.
- Full schedule duration and estimated start/end remain separate from route-only
  travel duration, distance, and mode.

## Alternatives

### A - Unified Route Ribbon

Two stable rows combine day scope and Add stop with a structured route brief.
This is the recommended starting point because every frequent action remains
visible, but schedule and route facts gain labels instead of becoming one sentence.

### B - Contextual Command Deck

A compact floating command deck keeps the map dominant. Add stop and route
evidence open as focused overlays only when requested. This has the smallest idle
footprint, with a higher discovery and open-state management cost.

### C - Schedule-First Strip

A bottom timeline makes day order, dates, and operational timing the primary map
control. Search and Add stop remain a small floating utility group. This best
supports comparison across days, but occupies persistent lower map space.

## Evaluation Tasks

1. Switch from Day 2 to All days and confirm the mode reads immediately.
2. Select a numbered pin and distinguish exact focus from circuit focus.
3. Add a restaurant to the active day, then repeat from All days using Best day.
4. Find the full schedule span and route-only travel time without parsing prose.
5. Open each option at full size and test at desktop and narrow viewport widths.

Record the preferred option and modifications in the Lab handoff. A saved handoff
is evaluation evidence, not permission to change production Map behavior.