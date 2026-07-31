# Experiment: Workspace visual refresh

## Meta

- Owner: Munish Goyal
- Date started: 2026-07-30
- Status: evaluating
- Lab: `http://127.0.0.1:5175/shell-visual-refresh.html`
- Full-size preview: choose an option, then use **Open full-size preview**

## Hypothesis

A quieter operational shell can feel more modern without reducing scan speed or
changing workspace behavior. Pane controls should communicate the surface they
open, rather than its current screen position.

## Variants

- **A - Semantic icon + text:** list, map, inspector, and conversation symbols
  pair with short labels. This is the clearest direction at wide desktop sizes.
- **B - Compact control rail:** the same semantic symbols become stable icon
  buttons with tooltips. Commands retain text where recognition is weaker.
- **C - Text-led command bar:** pane names carry navigation; icons are reserved
  for familiar commands such as add, export, settings, and account.

All variants use the same realistic itinerary, map, Details inspector, and the
selected centered Assistant focus modal. The controls are interactive, and every
variant can run as a full-viewport preview.

## Scope

Changed experiment files:

- `frontend/labs/shell-visual-refresh.html`
- `frontend/labs/src/shell-visual-refresh/main.tsx`
- Lab catalog and build registration

Non-goals:

- No production pane-icon or shell-style change before owner selection.
- No change to itinerary, map, Details, or Assistant contracts.
- No production tests for an unselected visual direction.

## Decision

- Decision: pending
- Production status: unchanged
- Next action: compare all three full-size variants and save one handoff with any
  requested combinations or refinements.
