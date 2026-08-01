# Pane Control Polish UX Lab

**Status:** Active enhancement and polishing experiment  
**Production impact:** None until the owner selects and separately approves an option

## Decision boundary

This Lab varies only the presentation of each pane's existing Hide and Maximize/Restore actions: labels, icon grouping, and optional local disclosure.

The following remain fixed:

- Hide and Maximize stay independently owned by each pane.
- Existing handlers, disabled states, pane recovery, resizing, and layout behavior do not change.
- Workspace command-bar controls, pane content, Map controls, and responsive composition do not change.

## Options

- **A - Compact semantic actions:** direct icon-and-text Hide and Maximize actions.
- **B - Restrained icon pair:** direct icons in one quiet pane-local group.
- **C - Pane action menu:** one local trigger reveals labeled Hide and Maximize actions.

The Lab is available at `http://127.0.0.1:5175/pane-controls.html`. It is intentionally separate from the Map command refinement requested on 2026-08-01.
