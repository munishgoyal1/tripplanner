# UX Experiments

This folder tracks A/B-style UX layout experiments so we can compare quickly and discard safely.

## Lab Catalog

The regular `scripts/dev/dev-spa.ps1` startup serves UX Labs automatically. Open
`http://127.0.0.1:5175/catalog.html` to access every standalone experiment.
For Lab-only work, run `npm --prefix frontend run dev:ux-lab` instead. The
workspace has three durable catalog views:

- `catalog.html` is All Labs: active, parked, and completed experiments.
- `catalog.html?view=active` contains choices still being evaluated or ready
  for implementation.
- `completed-labs.html` preserves completed experiments, their original Lab
  links, and the selected outcome.

Do not delete a Lab after a decision. Move its shared record from `activeLabs`
to `completedLabs`, retain the page, and update its experiment document with the
final choice and date. Every standalone Lab has one explicit Back to All Labs link;
catalog filters appear only on catalog pages.
Historical experiments that predate Lab pages may remain read-only detail records
reconstructed from their preserved source material.

Every individual Lab must declare its decision boundary before showing options or
the production-scale preview. The shared **Change scope** block names the exact
elements that vary and separately names the surrounding fixture elements that are
context only. Choosing an option authorizes only the declared changes; context UI
must remain unchanged unless the owner's handoff explicitly adds it.

The Change scope block also controls optional **change markers** on each preview.
Markers outline only elements carrying a Lab-owned `data-lab-change` target and
label the varied region without wrapping or restyling it. The marker layer is
rendered in a body portal, takes no layout space, and ignores pointer input, so
showing or hiding it cannot change the preview's dimensions or interactions.
Marker state is shared across Labs in the browser. These annotations exist only
under `frontend/labs/`; they must never be added to production components.

## Branch Strategy

- Stable baseline: `master`
- Immutable accepted UI baselines: `ui-stable/*` tags documented in
  [`STABLE_UI_VERSIONS.md`](STABLE_UI_VERSIONS.md)
- Preserved pre-scroll baseline: `preserve/pre-vertical-scroll` (from commit `3e7df9c`)
- Active experiment branches:
  - `exp/ux-shell-a-map-first`
  - `exp/ux-shell-b-story-first`
  - `exp/ux-shell-c-compact-mobile`

Use stable UI tags, not new long-lived branches or copied frontend folders, for
future accepted restoration points. A Lab does not become stable merely because it
exists or has a selected option; the owner must accept the implemented UI first.

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

## Decided Assistant Experiment (2026-07-30)

The Assistant-led trip kickoff lab is available at
`http://127.0.0.1:5175/chat-assistant.html`. It compares a collapsible edge
drawer, a corner conversation sheet, and a prompt popover around one realistic
structured-input journey. Each option can open in a full-viewport trip workspace.
The selected and implemented direction is B - Corner conversation sheet: a 480 px
lower-right surface over the usable workspace, with the conversation kept mounted
across close and reopen. No Azure deployment is
approved by this UI decision. See
[`CHAT_ASSISTANT_OVERLAY.md`](CHAT_ASSISTANT_OVERLAY.md).

## Implemented Workspace Refresh Experiment (2026-07-31)

The workspace visual-refresh lab is available at
`http://127.0.0.1:5175/shell-visual-refresh.html`. It compares semantic icon and
text controls, a compact icon control rail, and a text-led command bar inside a
realistic interactive planner. The selected and implemented direction is A -
Semantic icon + text, scoped only to the desktop top command bar. Wide desktops
show short pane labels; compact desktops retain the semantic icons without
overflow. Pane behavior and workspace UI below the command bar remain unchanged.
See [`SHELL_VISUAL_REFRESH.md`](SHELL_VISUAL_REFRESH.md).

## Implemented Command Bar Controls Experiment (2026-07-31)

The command-bar Lab remains available at
`http://127.0.0.1:5175/workspace-command-bar.html`. The selected and implemented
direction is A - Direct pane toggles. New trip is a labeled primary command;
Itinerary, Map, Details, and Assistant remain stable one-click controls in an
explicit visibility group. Existing Hide and Maximize actions stay in each pane
header. The pre-change semantic command bar is preserved at
`ui-stable/2026-07-31-semantic-command-bar`. See
[`WORKSPACE_COMMAND_BAR.md`](WORKSPACE_COMMAND_BAR.md).

## Implemented Trip Snapshot Experiment (2026-07-31)

The whole-trip snapshot Lab remains available at
`http://127.0.0.1:5175/trip-snapshot.html`. The selected and implemented direction
is B - Decision brief. The production snapshot now keeps traveler context with trip
identity, presents explicit booking readiness, and compresses Days, Stay, Places,
and Flights into one-line facts. Family and constraint evidence remains visible,
but the prototype's repeated Trip fit line below Budget was intentionally omitted.
Day briefs and itinerary rows are unchanged. See
[`TRIP_SNAPSHOT_HIERARCHY.md`](TRIP_SNAPSHOT_HIERARCHY.md).

## Implemented Map Controls Experiment (2026-07-31)

The Map commands and day context Lab is available at
`http://127.0.0.1:5175/map-controls.html`. It compares a Unified route ribbon,
Contextual command deck, and Schedule-first strip in the same production-scale
Paris workspace. The selected and implemented direction is A - Unified route
ribbon, refined after production review. Day scope now uses the Map title row,
Add stop remains directly visible below, and one compact line separates schedule
span from route-only travel. Day/all-days aggregate focus, exact-pin focus,
placement, pins, routes, mutations, and surrounding workspace behavior are
unchanged. See
[`MAP_PANEL_CONTROLS.md`](MAP_PANEL_CONTROLS.md).

## Active Pane Control Polish Experiment (2026-08-01)

The separate enhancements and polishing Lab is available at
`http://127.0.0.1:5175/pane-controls.html`. It compares compact semantic actions,
a restrained icon pair, and a pane-local action menu. Every option preserves each
pane's independent Hide and Maximize/Restore behavior, recovery, layout, and
content. This experiment is not part of the Map command refinement and makes no
production UI change until the owner selects and separately approves a direction.
See [`PANE_CONTROL_POLISH.md`](PANE_CONTROL_POLISH.md).

Each active experiment page also includes a **Your handoff** section. Choose one
option, record modifications, additional inputs, details to preserve, and
implementation or validation instructions, then choose its next step. The local
Vite server writes all handoffs to the machine-level store
`%LOCALAPPDATA%/Tripplanner/ux-labs/selections.json`, which is shared by the
primary checkout and every worker worktree. Writes use atomic replacement and
retain `selections.previous.json` for recovery. Existing records in the former
ignored `docs/ux-experiments/LAB_SELECTIONS.local.json` location migrate once
when the shared store is absent. A coding agent can read the shared store
when the owner later says to pick and execute the saved preferences. Saving a
handoff does not change production UI and is not implementation approval by
itself; the owner's later execution instruction remains the approval boundary.
**Save for implementation** keeps the Lab in progress and marks the complete
handoff ready. **Park for later** preserves the option and notes, removes the Lab
from In progress, and lists it under Parked on All Labs. **Mark completed**
preserves the selected option and notes, removes the Lab from In progress, and
lists it in both Completed views; completion records the evaluation decision but
does not assert that production implementation is shipped or approved. **Discard Lab** removes
the Lab from catalogs and deletes its option, notes, and browser draft; only a
minimal discarded marker remains so it stays hidden.
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
4. End each implemented experiment with a recorded decision and move its shared record from
  the active catalog to the completed page; preserve its Lab page as design history.
5. Read `%LOCALAPPDATA%/Tripplanner/ux-labs/selections.json` when the owner asks to execute a `ready`
  handoff; implement the selected option together with all handoff notes.
  Provisional language such as "try" or "see first" means extend or run the Lab
  preview, not production implementation approval. Do not add production code or
  production tests merely to evaluate an option.
6. Every standalone Lab page links directly back to All Labs.
7. Every option can be experienced at realistic production scale before selection;
  keep that preview inside the Lab until the owner explicitly approves production.
8. State exact in-scope changes and context-only elements before the alternatives.
  A realistic preview is not permission to redesign every element it happens to show.
9. Mark each varied preview region with `data-lab-change`; keep annotations out of
  production UI and ensure marker overlays take no layout space or pointer input.

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
