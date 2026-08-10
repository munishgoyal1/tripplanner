# Experiment: Assistant overlap after planning

## Meta

- Branch: not retained; current implementation work uses a sandbox
- Owner: Munish Goyal
- Date started: 2026-07-30
- Date ended: 2026-07-30
- Status: implemented
- Lab: `http://127.0.0.1:5175/lab-4-chat-assistant.html`
- Full-size preview: choose an option, then use **Open full-size preview**

## Hypothesis

A temporary Assistant surface can provide enough room for complete planning prompts,
then recede so Itinerary, Map, and Details regain visual priority. A clear launcher
should make re-entry easy without keeping a large conversation pane permanently open.

## Variants

- **A - Collapsible edge drawer (recommended):** a 420 px full-height drawer
  overlays Details while leaving Itinerary and most of Map usable. It collapses
  into a 48 px edge rail with a quiet ready indicator.
- **B - Corner conversation sheet:** a 480 px lower-right sheet uses about two-thirds
  of the workspace height. It leaves more of the map visible and collapses into a
  familiar floating Assistant button.
- **C - Prompt popover + rail:** a 400 px prompt surface opens beside a persistent
  48 px edge rail. It gives the three workspace panels the most visual priority,
  but provides the least room for a long transcript.

All variants use the same live interaction fixture: saved-default disclosure,
single choice, multiple choice, traveler stepper, direct-flight toggle, functional
skip path, one-click build handoff, Return to trip action, collapsed launcher, and
reopen behavior. Each runs at full viewport scale over the same realistic itinerary,
map, and details workspace.

## Scope

Changed experiment files:

- `frontend/labs/lab-4-chat-assistant.html`
- `frontend/labs/src/chat-assistant/main.tsx`
- `frontend/labs/src/catalog/main.tsx`
- `frontend/labs/vite.config.ts`

Related backend foundation:

- `src/tripplanner/chat_interactions.py`
- additive `input_request` SSE event
- shared web/native TypeScript contract

Non-goals for this experiment:

- No additional production Assistant layout change beyond the selected conversation sheet.
- No production renderer tests merely to evaluate a Lab option.
- No change to direct-mode complete-by-default planning.
- No generic form builder or arbitrary model-authored HTML.
- No persistence of unanswered input requests in this milestone.

## Interaction Intent

- Primary workflow: user states destination/origin/rough timing; Assistant applies
  durable preferences and asks at most one compact trip-specific question when needed.
- Secondary workflow: user skips the question and receives a complete first plan
  built from disclosed defaults.
- Refinement: after the first plan, Assistant remains available; Details and Map
  provide direct visual refinement.
- Mobile behavior: use the same structured request contract in a native sheet after
  the desktop direction is selected; do not squeeze the desktop overlay onto mobile.

## Test Scenarios

1. Start with a bare Paris request and build using all preselected values.
2. Change pace, priorities, party size, and flight preference before building.
3. Skip the prompt and verify the UI makes its default assumptions explicit.
4. Collapse and reopen each option; judge whether its resting affordance is obvious
  without competing with the three trip panels.
5. Compare how much Itinerary, Map, and Details remain visible while each is open.
6. Use keyboard-only controls and verify every field has a visible label and state.

## Scorecard (1-5)

- Completion speed:
- Clarity:
- Cognitive load (higher is easier):
- Mobile adaptability:
- Delight:
- Confidence while editing:

## Decision

- Decision: B - Corner conversation sheet
- Implementation: 480 px lower-right desktop sheet using about 68% of workspace
  height, with sharp edges, explicit close, and one continuously mounted conversation.
- Rationale: it gives follow-up turns enough room while leaving most of the map and
  itinerary visible and usable.
- Next action: evaluate broader shell and control styling separately in the
  workspace visual-refresh Lab. No Azure deployment is approved.
