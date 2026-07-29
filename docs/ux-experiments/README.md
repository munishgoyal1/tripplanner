# UX Experiments

This folder tracks A/B-style UX layout experiments so we can compare quickly and discard safely.

## Lab Catalog

Open `http://localhost:5173/labs.html` while the frontend dev server is running
to access every standalone UX experiment from one place. The catalog has two
durable sections:

- **Active experiments** contains choices still being evaluated or paired.
- **Already decided** preserves completed experiments, their original lab links,
  and the selected outcome.

Do not delete a lab after a decision. Move its catalog record from Active to
Already decided, retain the page, and update its experiment document with the
final choice and date. Historical experiments that predate lab pages may remain
read-only detail records reconstructed from their preserved source material.

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
`http://localhost:5173/ux-lab.html` while the frontend dev server is running.
The implemented decision is B - Compact Agenda. See
[`ITINERARY_INFORMATION_DESIGN.md`](ITINERARY_INFORMATION_DESIGN.md).

The separate day-summary lab is available at
`http://localhost:5173/summary-lab.html`. The implemented decision is C -
Compact Brief, with explicit Travel rhythm and day-plan wording, confirmed and
remaining booking counts, and hotel anchors excluded from the planned-stop
count. See
[`ITINERARY_SUMMARY_DESIGN.md`](ITINERARY_SUMMARY_DESIGN.md).

These standalone labs are the preferred mechanism for future focused UX choices:
use realistic fixtures, compare coherent alternatives, record local scores, and
keep production behavior unchanged until the owner selects a direction.

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

## Rules

1. Keep each experiment isolated to UI layout/interaction files only.
2. Timebox each experiment to 1-2 sessions.
3. Use the scorecard template for decision-making.
4. End each experiment with a recorded decision and move its catalog entry to
  Already decided; preserve its lab page as design history.
5. Read `LAB_SELECTIONS.local.json` when the owner asks to execute saved lab
  preferences; implement the selected option together with its comments.

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
