# Experiment: Assistant-led trip kickoff

## Meta

- Branch: `agents/worker-1`
- Owner: Munish Goyal
- Date started: 2026-07-30
- Date ended: pending
- Status: testing
- Lab: `http://127.0.0.1:5175/chat-assistant.html`

## Hypothesis

A focused Assistant surface can make conversation the primary itinerary-building
surface without hiding the workspace context users need for trust. Showing the
saved defaults already applied, then asking one compact prefilled question only
when high-impact trip facts remain unresolved, should reduce typing and produce
a stronger first itinerary faster than either a small chat dock or a questionnaire.

## Variants

- **A - Docked sidecar:** attaches Assistant to the right half of the workspace.
  Itinerary and Map remain bright, visible, and usable at the same time. Saved
  defaults collapse into one compact disclosure bar so chat has enough width.
- **B - Focus modal (recommended):** opens one large centered layer over a dimmed
  workspace. Saved defaults sit beside the conversation; the user completes one
  concentrated planning turn, closes it, and returns to the unchanged trip view.
- **C - Guided takeover:** replaces the entire workspace with an explicit three-step
  path: Trip brief, Research, Review. It gives the process maximum authority but
  hides Itinerary and Map until the first complete plan is ready.

All variants use the same live interaction fixture: saved-default disclosure,
single choice, multiple choice, traveler stepper, direct-flight toggle, skip path,
and one-click build handoff.

## Scope

Changed experiment files:

- `frontend/labs/chat-assistant.html`
- `frontend/labs/src/chat-assistant/main.tsx`
- `frontend/labs/src/catalog/main.tsx`
- `frontend/labs/vite.config.ts`

Related backend foundation:

- `src/tripplanner/chat_interactions.py`
- additive `input_request` SSE event
- shared web/native TypeScript contract

Non-goals for this experiment:

- No production Assistant layout change before owner selection.
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
4. Verify A keeps the workspace usable, B keeps it visible but inactive, and C
  replaces it with the staged planning path.
5. Use keyboard-only controls and verify every field has a visible label and state.

## Scorecard (1-5)

- Completion speed:
- Clarity:
- Cognitive load (higher is easier):
- Mobile adaptability:
- Delight:
- Confidence while editing:

## Decision

- Decision: pending
- Recommendation: B - Focus modal
- Rationale: it gives the Assistant enough room for rich choices while preserving
  a visible relationship to the itinerary being built.
- Next action: save the preferred option and modifications in the Lab, then approve
  the production implementation slice.
