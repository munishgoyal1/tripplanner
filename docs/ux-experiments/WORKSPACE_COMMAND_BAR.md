# Experiment: Workspace command bar controls

## Meta

- Owner: Munish Goyal
- Date started: 2026-07-31
- Status: implemented
- Lab: `http://127.0.0.1:5175/workspace-command-bar.html`

## Variants

- **A - Direct pane toggles:** every pane remains one click away in the command bar.
- **B - Segmented view group:** visibility appears as one compact workspace mode.
- **C - Layout popover:** visibility and focus controls move into one menu.

## Decision

- Decision: **A - Direct pane toggles**
- Production status: implemented on 2026-07-31.
- New trip is a labeled primary command followed by a stable visibility group for
  Itinerary, Map, Details, and Assistant.
- The previously implemented semantic icons and active states remain authoritative.
  Pane labels collapse at compact desktop widths without header overflow.
- Hide and Maximize remain local actions in each pane header. Pane layout, sizes,
  content, resizing, Assistant behavior, and mobile UI are unchanged.

## Restoration

The accepted UI immediately before this Lab is preserved as immutable pushed tag
`ui-stable/2026-07-31-semantic-command-bar` at commit `2665f7b`. Restoration must
follow the stable UI workflow and create a new validated commit; do not reset master.

## Validation

- Focused App suite: 27 tests pass.
- Live desktop command bar: no overflow at 1440 px or 1024 px.