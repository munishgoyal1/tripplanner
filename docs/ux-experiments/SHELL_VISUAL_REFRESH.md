# Experiment: Workspace visual refresh

## Meta

- Owner: Munish Goyal
- Date started: 2026-07-30
- Status: implemented
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
selected lower-right Assistant conversation sheet. The controls are interactive, and every
variant can run as a full-viewport preview.

## Scope

Changed experiment files:

- `frontend/labs/shell-visual-refresh.html`
- `frontend/labs/src/shell-visual-refresh/main.tsx`
- Lab catalog and build registration

Non-goals:

- No visual or behavioral change below the desktop top command bar.
- No change to itinerary, map, Details, or Assistant contracts.
- No mobile workspace redesign.

## Decision

- Decision: **A - Semantic icon + text**
- Owner boundary: only change the top row.
- Production status: implemented on 2026-07-31.
- Implementation: Itinerary, Map, Details, and Assistant use meaning-first icons
  with short labels at wide desktop sizes and icon-only controls at compact
  desktop widths. Familiar New trip, trip actions, account, and preferences
  commands remain compact icons. Existing handlers, pane behavior, and all UI
  below the command bar are unchanged.
- Validation: focused App tests pass; the live command bar has no horizontal
  overflow at 1440 px or 1024 px.
