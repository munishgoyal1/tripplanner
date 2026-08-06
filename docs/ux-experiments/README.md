# UX Experiments

This folder tracks A/B-style UX layout experiments so we can compare quickly and discard safely.

## Lab Catalog

The regular `scripts/dev/dev-spa.ps1` startup serves UX Labs automatically. Open
`http://127.0.0.1:5175/catalog.html` to access every standalone experiment.
For Lab-only work, run `npm --prefix frontend run dev:ux-lab` instead. The
workspace has five durable catalog views:

- `catalog.html` is All Open Labs: in-progress, implemented-review, and parked
  experiments; only completed experiments are excluded.
- `catalog.html?view=active` contains choices still being evaluated or currently
  under implementation.
- `catalog.html?view=implemented-review` contains production implementations
  awaiting owner review and sign-off.
- `catalog.html?view=parked` contains saved evaluations waiting for a later
  decision.
- `completed-labs.html` preserves completed experiments, their original Lab
  links, and the selected outcome.

The implemented-review workflow starts with production implementations made on
2026-08-02. Earlier implemented Labs remain Completed; implementations from that
date onward stay in Implemented review until explicit owner sign-off.

Do not delete a Lab after a decision. Update its machine lifecycle record, retain
the page, and update its experiment document with the final choice and date.
Every standalone Lab has one explicit Back to All Labs link;
catalog filters appear only on catalog pages.
Historical experiments that predate Lab pages may remain read-only detail records
reconstructed from their preserved source material.

Each Lab has one permanent integer `labNumber` in the canonical registry. Allocate
a new Lab by incrementing `LAST_ASSIGNED_LAB_NUMBER` and assigning that value once.
Never renumber or reuse an identifier when a Lab changes state, is completed, or is
discarded. Catalog sections display the stored number rather than a row index so
`Lab #N` always identifies the same experiment.

Every individual Lab must declare its decision boundary before showing options or
the production-scale preview. The shared **Change scope** block names the exact
elements that vary and separately names the surrounding fixture elements that are
context only. Choosing an option authorizes only the declared changes; context UI
must remain unchanged unless the owner's handoff explicitly adds it.

Every option selector must also include an **Exact delta** statement. It names
the structure or behavior unique to that option and explicitly contrasts it with
the alternatives. Repeat the selected option's delta above its preview so the
comparison remains visible after selection. A benefit-oriented summary alone is
not sufficient to distinguish or approve an option.

Every Lab must also carry the shared **The difference, in one place** block
directly under Change scope. Per-option prose is written one option at a time and
cannot be compared; this block states the single axis the options genuinely
disagree about, then puts every option on the same four columns - the idea, what
it buys, what it costs, and when to choose it - and closes by naming what is
identical in all of them. Every option carries a 0-100 fit score and the rows
render best first, so the recommendation is an ordering rather than a sentence.
The score ranks only the options within one Lab. Option letters stay fixed
because decision records refer to them; ranking never renames an option. In a
Lab that is still open, list the option cards themselves in the same descending
order, so the page and the table agree; a decided Lab keeps its recorded order.
Close the block with one plain-prose paragraph reading the three options against
each other and saying why the ranking lands where it does.
Content lives in `frontend/labs/src/shared/OptionContrast.tsx`, keyed by Lab id,
so a new Lab adds one record and renders `<OptionContrast labId={LAB_ID} />`.

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
- Retired workspace-shell experiments: branches A, B, and C were deleted after
  the selected direction was integrated. Their history remains documented in
  [`WORKSPACE_SHELL_LAYOUT.md`](WORKSPACE_SHELL_LAYOUT.md).
- Retired pre-scroll baseline: branch `preserve/pre-vertical-scroll` was deleted;
  its original commit remains available as `3e7df9c`.

Use stable UI tags, not new long-lived branches or copied frontend folders, for
future accepted restoration points. A Lab does not become stable merely because it
exists or has a selected option; the owner must accept the implemented UI first.

## Current Decision (2026-07-23)

Layout C is the selected working direction: map-first canvas on the left,
details-first rail on the right, and chat in the compact lower-right pane.
The experiment badge and dashboard-style move/hide controls were removed;
resizing and maximize remain. The direction was integrated and the discarded
experiment branches were retired.

## Decided Component Experiments (2026-07-29)

The itinerary information-design lab is available at
`http://127.0.0.1:5175/lab-2-itinerary-information.html` while the UX Lab server is running.
The implemented decision is B - Compact Agenda. See
[`ITINERARY_INFORMATION_DESIGN.md`](ITINERARY_INFORMATION_DESIGN.md).

The separate day-summary lab is available at
`http://127.0.0.1:5175/lab-3-itinerary-summary.html`. The implemented decision is C -
Compact Brief, with explicit Travel rhythm and day-plan wording, confirmed and
remaining booking counts, and hotel anchors excluded from the planned-stop
count. See
[`ITINERARY_SUMMARY_DESIGN.md`](ITINERARY_SUMMARY_DESIGN.md).

The compact itinerary density Lab selected Option B with an explicit preservation
constraint. Production retains the detailed Compact Agenda and tightens spacing;
identical hotel endpoints render once with Depart and Return timing, while different
hotels remain explicit Check out and Check in rows. See
[`ITINERARY_DENSITY.md`](ITINERARY_DENSITY.md).

These standalone labs are the preferred mechanism for future focused UX choices:
use realistic fixtures, compare coherent alternatives, record local scores, and
keep production behavior unchanged until the owner selects a direction. Every
experiment must include a production-scale preview that shows the option inside
a realistic full application viewport; a miniature specimen alone is not enough
to judge or approve a direction.

## Open Agentic Planning Experiment (2026-08-05)

The agentic planning lab is available at
`http://127.0.0.1:5175/lab-19-agentic-planning.html`. It is the first lab about agent
*behaviour* rather than presentation, and it answers two defects the owner reported: a new
attraction placed on day 5 after the flight home, and a hotel-class change that silently
deleted the return leg to Bengaluru. Both are reproduced live from a deterministic model of
the production heuristics in `src/tripplanner/tools/trip_planner.py`.

Its answer is that a separate intelligence layer is required beside the model: a
deterministic plan engine that owns placement, validation and persistence under eight
invariants, leaving the model to parse intent and explain the resulting diff. It compares
proposal-first review, guarded autonomy with reversible receipts, and a persistent plan
console, and it applies the same operation and verdict from all four channels — chat, map,
itinerary and details. See [`AGENTIC_PLANNING.md`](AGENTIC_PLANNING.md).

## Open Travel Documents Experiment (2026-08-06)

The travel documents lab is available at
`http://127.0.0.1:5175/lab-20-travel-documents.html`. The owner approved the capability on
6-Aug-2026, which supersedes the earlier non-goal below that kept travel-document upload out
of scope pending approval.

Its retention rule was decided before the lab opened and is context, not a variable: the
original photo or PDF is **never stored**. A document is read once, the fields that answer a
planning question are kept, the document number is kept masked, and the file is discarded.
Those kept fields are what get reused on the next trip, so the same passport is never
requested twice. The lab compares a trip readiness rail, an account vault that the trip only
reports gaps against, and a drop-anything inbox that routes items after the fact. Its Lisbon
fixture is built so every check has a real answer, including a passport that fails Portugal's
three-month validity rule. See [`TRAVEL_DOCUMENTS.md`](TRAVEL_DOCUMENTS.md).

## Open Itinerary and Map Canvas Experiments (2026-08-05)

Two paired labs reimagine the two panes the owner reads most, using one shared four-day
Lisbon fixture so both argue over the presentation of identical facts.

The itinerary canvas lab is available at
`http://127.0.0.1:5175/lab-17-itinerary-canvas.html`. It compares a continuous journey
spine, layered stop cards that open notes in place, and an editorial agenda grouped by
Morning, Afternoon and Evening. Every production stop, day and trip fact is required in
every option; only its ranking changes. See
[`ITINERARY_CANVAS.md`](ITINERARY_CANVAS.md).

The map canvas lab is available at
`http://127.0.0.1:5175/lab-18-map-canvas.html`. It compares a floating control deck, a
bottom route dock that carries the day's stop timeline, a single command ribbon, and a
search-first dock that keeps the bottom placement but drops the resident stop list, puts a
real search field in the dock, and lets a tap on an unplanned pin fill that same field. Day
scope, all three add-stop inputs, the day fact line, the pin card and the failure state are
required in every option. See [`MAP_CANVAS.md`](MAP_CANVAS.md).

Both labs include a *Compare with today* toggle and a full-viewport production-scale
preview. No production code is changed by either Lab.

## Open Chat Agent Workspace Experiment (2026-08-05)

The chat-agent rethink lab is available at
`http://127.0.0.1:5175/lab-16-chat-agent-workspace.html`. It revisits the decision
recorded below by asking where the Assistant should live in the workspace, and how a
single turn, the time it took, and the stops it changed should be presented. It compares
a resident conversation column, a full-width focus composer with an expanding reading
sheet, and a right-rail turn thread that displaces Details into a map overlay. Complete
session history, reader-owned scroll position, and a retained per-reply duration are
required in every option rather than selectable, because they are current defects. No
production code is changed by this Lab. See
[`CHAT_AGENT_WORKSPACE.md`](CHAT_AGENT_WORKSPACE.md).

## Decided Assistant Experiment (2026-07-30)

The Assistant-led trip kickoff lab is available at
`http://127.0.0.1:5175/lab-4-chat-assistant.html`. It compares a collapsible edge
drawer, a corner conversation sheet, and a prompt popover around one realistic
structured-input journey. Each option can open in a full-viewport trip workspace.
The selected and implemented direction is B - Corner conversation sheet: a 480 px
lower-right surface over the usable workspace, with the conversation kept mounted
across close and reopen. No Azure deployment is
approved by this UI decision. See
[`CHAT_ASSISTANT_OVERLAY.md`](CHAT_ASSISTANT_OVERLAY.md).

## Implemented Workspace Refresh Experiment (2026-07-31)

The workspace visual-refresh lab is available at
`http://127.0.0.1:5175/lab-9-shell-visual-refresh.html`. It compares semantic icon and
text controls, a compact icon control rail, and a text-led command bar inside a
realistic interactive planner. The selected and implemented direction is A -
Semantic icon + text, scoped only to the desktop top command bar. Wide desktops
show short pane labels; compact desktops retain the semantic icons without
overflow. Pane behavior and workspace UI below the command bar remain unchanged.
See [`SHELL_VISUAL_REFRESH.md`](SHELL_VISUAL_REFRESH.md).

## Implemented Command Bar Controls Experiment (2026-07-31)

The command-bar Lab remains available at
`http://127.0.0.1:5175/lab-7-workspace-command-bar.html`. The selected and implemented
direction is A - Direct pane toggles. New trip is a labeled primary command;
Itinerary, Map, Details, and Assistant remain stable one-click controls in an
explicit visibility group. Existing Hide and Maximize actions stay in each pane
header. The pre-change semantic command bar is preserved at
`ui-stable/2026-07-31-semantic-command-bar`. See
[`WORKSPACE_COMMAND_BAR.md`](WORKSPACE_COMMAND_BAR.md).

## Implemented Trip Snapshot Experiment (2026-07-31)

The whole-trip snapshot Lab remains available at
`http://127.0.0.1:5175/lab-6-trip-snapshot.html`. The selected and implemented direction
is B - Decision brief. The production snapshot now keeps traveler context with trip
identity, presents explicit booking readiness, and compresses Days, Stay, Places,
and Flights into one-line facts. Family and constraint evidence remains visible,
but the prototype's repeated Trip fit line below Budget was intentionally omitted.
Day briefs and itinerary rows are unchanged. See
[`TRIP_SNAPSHOT_HIERARCHY.md`](TRIP_SNAPSHOT_HIERARCHY.md).

## Implemented Map Controls Experiment (2026-07-31)

The Map commands and day context Lab is available at
`http://127.0.0.1:5175/lab-8-map-controls.html`. It compares a Unified route ribbon,
Contextual command deck, and Schedule-first strip in the same production-scale
Paris workspace. The selected and implemented direction is A - Unified route
ribbon, refined after production review. Day scope now uses the Map title row,
Add stop remains directly visible below, and one compact line separates schedule
span from route-only travel. Day/all-days aggregate focus, exact-pin focus,
placement, pins, routes, mutations, and surrounding workspace behavior are
unchanged. See
[`MAP_PANEL_CONTROLS.md`](MAP_PANEL_CONTROLS.md).

## Implemented Pane Control Polish Experiment (2026-08-01)

The separate enhancements and polishing Lab is available at
`http://127.0.0.1:5175/lab-10-pane-controls.html`. It compares compact semantic actions,
a restrained icon pair, and a pane-local action menu. The selected and implemented
direction is B - Restrained icon pair for Itinerary, Map, and Details. It groups
each pane's existing icons without changing independent Hide and Maximize/Restore
behavior, disabled states, recovery, layout, or content. This experiment remains
separate from the Map command refinement.
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
Cards show both the Lab creation date and the date it entered its current
lifecycle state. The machine record wins over committed historical fallback
metadata when the two disagree.
**Save for implementation** keeps the Lab in progress and marks the complete
handoff ready. **Mark implemented - to be reviewed** is required after production
implementation and keeps the Lab visible in progress for owner validation.
**Sign off and complete** is enabled only from that review state; it records the
owner's approval, removes the Lab from In progress, and lists it in both Completed
views. **Park for later** preserves the option and notes, removes the Lab from In
progress, and lists it under Parked on All Labs. **Discard Lab** removes
the Lab from catalogs and deletes its option, notes, and browser draft; only a
minimal discarded marker remains so it stays hidden.
The page also keeps each in-progress choice and comment as a browser draft. If
the local endpoint is temporarily unavailable, the draft survives a reload and
can be retried once the Labs server is running again.

## Active Trip Book Experiment (2026-07-30)

The Execution-ready Trip Book lab is available at
`http://127.0.0.1:5175/lab-5-itinerary-trip-book.html`. It compares a compact
Operations binder, the recommended Layered Trip Book, and a Visual journey
book using the same family-trip facts. The experiment tests packet structure,
navigation, document readiness, and evidence-labeled personalization only;
secure document ingestion and merged-PDF production behavior remain out of
scope until a direction is selected and separately approved. See
[`ITINERARY_TRIP_BOOK.md`](ITINERARY_TRIP_BOOK.md). Document ingestion itself was
approved on 6-Aug-2026 and is now decided in
[`TRAVEL_DOCUMENTS.md`](TRAVEL_DOCUMENTS.md), which also rules out merged-PDF storage
permanently: originals are never kept.

## Rules

1. Keep each experiment isolated to UI layout/interaction files only.
2. Timebox each experiment to 1-2 sessions.
3. Use the scorecard template for decision-making.
4. After implementing an experiment, move its shared record to `implemented-review`.
  Keep it active until the owner signs off, then move it to `completed`; preserve
  its Lab page as design history.
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
9. Give every Lab an option-contrast table naming the one axis the options disagree
  about, compared on identical columns, scored 0-100 and ordered best first, plus
  what stays identical across them.
10. Mark each varied preview region with `data-lab-change`; keep annotations out of
  production UI and ensure marker overlays take no layout space or pointer input.

## Compare Checklist

- Task completion speed
- Layout clarity
- Cognitive load
- Mobile usability
- Delight / visual appeal
- Editing confidence
