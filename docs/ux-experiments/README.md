# UX Experiments

This folder tracks A/B-style UX layout experiments so we can compare quickly and discard safely.

## Lab Catalog

The regular `scripts/dev/dev-spa.ps1` startup serves UX Labs automatically. Open
`http://127.0.0.1:5175/catalog.html` to access every standalone experiment.
For Lab-only work, run `npm --prefix frontend run dev:ux-lab` instead. The
workspace has two durable linked pages:

- `catalog.html` contains active choices still being evaluated or paired.
- `completed-labs.html` preserves completed experiments, their original Lab
  links, and the selected outcome.

Do not delete a Lab after a decision. Move its shared record from `activeLabs`
to `completedLabs`, retain the page, and update its experiment document with the
final choice and date. Every standalone Lab links directly to both indexes.
Historical experiments that predate Lab pages may remain read-only detail records
reconstructed from their preserved source material.

## Branch Strategy

- Stable baseline: `master`
- Preserved pre-scroll baseline: `preserve/pre-vertical-scroll` (from commit `3e7df9c`)
- Active experiment branches:
  - `exp/ux-shell-a-map-first`
  - `exp/ux-shell-b-story-first`
  - `exp/ux-shell-c-compact-mobile`

## Current Decision (2026-07-23)

Layout C is the selected working direction: map-first canvas on the left,
details-first rail on the right, and chat in the compact lower-right pane.
The experiment badge and dashboard-style move/hide controls were removed;
resizing and maximize remain. Keep the other branches until C is accepted on
canary, then merge C and delete discarded experiment branches.

## Decided Component Experiments (2026-07-29)

The itinerary information-design lab is available at
`http://127.0.0.1:5175/itinerary-information.html` while the UX Lab server is running.
The implemented decision is B - Compact Agenda. See
[`ITINERARY_INFORMATION_DESIGN.md`](ITINERARY_INFORMATION_DESIGN.md).

The separate day-summary lab is available at
`http://127.0.0.1:5175/itinerary-summary.html`. The implemented decision is C -
Compact Brief, with explicit Travel rhythm and day-plan wording, confirmed and
remaining booking counts, and hotel anchors excluded from the planned-stop
count. See
[`ITINERARY_SUMMARY_DESIGN.md`](ITINERARY_SUMMARY_DESIGN.md).

These standalone labs are the preferred mechanism for future focused UX choices:
use realistic fixtures, compare coherent alternatives, record local scores, and
keep production behavior unchanged until the owner selects a direction. Every
experiment must include a production-scale preview that shows the option inside
a realistic full application viewport; a miniature specimen alone is not enough
to judge or approve a direction.

## Active Assistant Experiment (2026-07-31)

The Assistant overlap lab is available at
`http://127.0.0.1:5175/chat-assistant.html`. It compares a Collapsible edge
drawer, Corner conversation sheet, and Prompt popover + rail around the same
realistic structured-input journey. Each option supports the full open, build,
return, collapsed, and reopen lifecycle over a production-scale trip workspace.
A - Collapsible edge drawer is the recommended starting point; no option is a
final selection. No production layout change is approved until the owner
explicitly chooses a direction after evaluation. See
[`CHAT_ASSISTANT_OVERLAY.md`](CHAT_ASSISTANT_OVERLAY.md).

## Active Map Controls Experiment (2026-07-31)

The Map commands and day context Lab is available at
`http://127.0.0.1:5175/map-controls.html`. It compares a Unified route ribbon,
Contextual command deck, and Schedule-first strip in the same production-scale
Paris workspace. Every option preserves day/all-days aggregate focus, exact-pin
focus, explicit Add stop placement, and the distinction between full schedule
duration and route-only travel evidence. A - Unified route ribbon is the
recommended starting point; no production Map change is approved. See
[`MAP_PANEL_CONTROLS.md`](MAP_PANEL_CONTROLS.md).

Each active experiment page also includes a **Your handoff** section. Choose one
option, add modifications or implementation instructions, and save it. The local
Vite server writes all handoffs to the ignored worktree file
`docs/ux-experiments/LAB_SELECTIONS.local.json`, which a coding agent can read
when the owner later says to pick and execute the saved preferences. Saving a
handoff does not change production UI and is not implementation approval by
itself; the owner's later execution instruction remains the approval boundary.
The page also keeps each in-progress choice and comment as a browser draft. If
the local endpoint is temporarily unavailable, the draft survives a reload and
can be retried once the Labs server is running again.

## Active Trip Book Experiment (2026-07-30)

The Execution-ready Trip Book lab is available at
`http://127.0.0.1:5175/itinerary-trip-book.html`. It compares a compact
Operations binder, the recommended Layered Trip Book, and a Visual journey
book using the same family-trip facts. The experiment tests packet structure,
navigation, document readiness, and evidence-labeled personalization only;
secure document ingestion and merged-PDF production behavior remain out of
scope until a direction is selected and separately approved. See
[`ITINERARY_TRIP_BOOK.md`](ITINERARY_TRIP_BOOK.md).

## Rules

1. Keep each experiment isolated to UI layout/interaction files only.
2. Timebox each experiment to 1-2 sessions.
3. Use the scorecard template for decision-making.
4. End each experiment with a recorded decision and move its shared record from
  the active catalog to the completed page; preserve its Lab page as design history.
5. Read `LAB_SELECTIONS.local.json` when the owner asks to execute saved lab
  preferences; implement the selected option together with its comments.
  Provisional language such as "try" or "see first" means extend or run the Lab
  preview, not production implementation approval. Do not add production code or
  production tests merely to evaluate an option.
6. Every standalone Lab page links directly to the active and completed indexes.
7. Every option can be experienced at realistic production scale before selection;
  keep that preview inside the Lab until the owner explicitly approves production.

## Fast Commands

```powershell
git switch exp/ux-shell-a-map-first
git switch exp/ux-shell-b-story-first
git switch exp/ux-shell-c-compact-mobile
git switch preserve/pre-vertical-scroll
git switch master
```

## Compare Checklist

- Task completion speed
- Layout clarity
- Cognitive load
- Mobile usability
- Delight / visual appeal
- Editing confidence
