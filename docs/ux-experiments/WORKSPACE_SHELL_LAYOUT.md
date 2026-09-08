# Experiment: Workspace Shell Layout

## Meta

- Surface: `frontend/labs/lab-1-workspace-shell.html`
- Original branches: `exp/ux-shell-a-map-first`,
  `exp/ux-shell-b-story-first`, `exp/ux-shell-c-compact-mobile`
- Date started: 2026-06-20
- Decision date: 2026-07-23
- Status: decided

## Options

### A - Map-first

- Hypothesis: location-flow-first planning improves place-level edit speed.
- Primary: persistent dominant Map and Details.
- Supporting: Itinerary and Chat in a secondary column.
- Preserved source: commit `3ece004`.

### B - Story-first

- Hypothesis: itinerary prominence improves continuity for users who think in a
  day-by-day narrative before map fine-tuning.
- Primary: Itinerary as the planning spine, with Details nearby.
- Supporting: Chat and Map in the secondary right lane.
- Preserved source: commit `65769d8`.

### C - Spatial workspace

- Hypothesis: independent persistent panes preserve context across map,
  itinerary, detail, and conversation workflows.
- Primary: Itinerary left, dominant Map center, Details right.
- Supporting: compact Assistant dock in the lower-right; panes can hide, resize,
  and maximize.
- Preserved source: `f8d02a1` and later work on
  `exp/ux-shell-c-compact-mobile`.

## Decision

- Selected: C - Spatial workspace.
- Outcome: map-first canvas, details-first rail, compact lower-right Assistant,
  no page scroll on desktop, and responsive inspector/mobile adaptations.
- Archive note: the experiment predates standalone lab pages. Its current page
  reconstructs verified option intent and pane arrangements from preserved
  branch documents; it does not claim to be an executable snapshot of each old
  branch.