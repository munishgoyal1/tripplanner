# Planner Layout Directions

Lab #30 compares four complete workspace directions using the sbx4 planner as the factual baseline. It is available at `http://127.0.0.1:5175/lab-30-planner-layout-directions.html` while the UX Lab server is running.

## Decision

**C · Refined spatial workspace** was selected on 9 September 2026 and is implemented
in the sbx4 lane for owner review. Production promotion remains a separate decision.

## Shared fixture

Every direction presents the same four-day Kyoto trip, 14–18 April, for two travellers. The fixture stays at 60% readiness, keeps the same warning about missing food stops, and selects Kiyomizu-dera from the same day-one route. Export, new trip, reset, feedback, settings, sign-in, day navigation, map, itinerary, place details, and assistant editing remain available in every direction.

## Options

- **A · Journey canvas** is entirely new. A full-width map becomes the stage, a horizontal journey rail replaces the itinerary column, and a focused itinerary card plus floating place inspector reveal detail around the current selection.
- **B · Trip storyboard** is entirely new. A chapter rail, editorial day stream, and supporting map/evidence rail make the itinerary read as a coherent travel story.
- **C · Refined spatial workspace** keeps sbx4's three-pane model and substantially improves its hierarchy, grouping, density, colour, pane headers, and assistant dock.
- **D · Precision polish** preserves sbx4's geometry and information order. It focuses on professional hide/maximize controls, icon clarity, grouped actions, compact feedback, spacing, focus states, and finish.

## Evaluation notes

The previews run at full application scale and include working day selection, pane hide/restore, map maximize/restore, and assistant expand/minimize actions where those interactions belong. Responsive rules preserve the intended hierarchy at narrow widths. A saved selection authorizes only the Lab scope; implementing it in production requires a separate handoff.

## Implemented review

The sbx4 implementation gives the wide desktop a 27/48/25 itinerary-map-details
starting balance, preserves owner resizing after a one-time layout migration, adds
task-oriented pane identities, shortens focused-place imagery, reorders the direct
visibility controls to follow the canvas, collapses an empty notification row, and
makes the compact Assistant dock explicit and trip-aware. Pane visibility, resizing,
maximizing, focus synchronization, and mobile behavior retain their existing contracts.
