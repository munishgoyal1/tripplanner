# Feature 05 — Conversational Change Diff & Undo Timeline

- **Pillars:** C (easier chat), B (easy editing), E (insightful/trust)
- **Status:** Proposed (new; builds on workspace revisions + `LIFE-02` history + `DATA-01` versioned writes)
- **Size:** L · **Risk:** med · **Suggested lane:** Agent 2 (diff) + Agent 3 (revision store/prune) + Agent 1 (UI)

## The pain

Chatting with a planner is scary because you can't see what it changed, and you can't
easily undo. "It rewrote my whole trip" is the top trust-killer and makes users hesitant
to let the agent edit at all.

## Outcome

Every agent turn that mutates the trip shows a compact, plain-language diff
("Added Aguada Fort to Day 2 · Moved dinner to 8:30 · Swapped hotel to Taj"), and a trip
timeline lets the user revert to any recent revision with one click.

## Bounded v1

- After each mutating turn, compute a **structured diff** (added / removed / moved /
  retimed / hotel / stay / booking) from before/after view models; render it in the
  command-bar mutation region + an expandable chat diff.
- Keep the last **N in-session revisions** with one-click "Undo to before this change"
  using authoritative conditional replace (ETag) — a real persisted revert, not a client
  illusion. Reflow refreshes all panes coherently.
- Full persisted history timeline (beyond N) is a later phase.

## UX

- Mutation outcome shows the existing one-line summary + "Details" to expand the diff.
- A small history control lists recent revisions with revert; revert runs as a normal
  authoritative mutation.

## Implementation notes

- **Backend:** a pure diff over two `TripView` snapshots (new `src/tripplanner/web/trip_diff.py`);
  return it on mutating SSE completion in `src/tripplanner/api.py`. Store bounded recent
  revision snapshots keyed by trip + revision; leverage `DATA-01` versioned reads / conditional
  replace for revert.
- **Frontend:** render diff in `TripSnapshot` / command bar + `ChatPanel`; a compact history
  list; wire revert to a mutation call. `frontend/src/workspaceState.ts` tracks revision tokens.

## Perf / privacy / cost

Diff is O(stops); snapshots are bounded (e.g. last 10) and pruned. No content in analytics.

## Risks & mitigations

- **Snapshot storage size** → heed the `places_cache` 2 MiB lesson: keep snapshots/diffs
  lean, cap count, prune oldest, guard byte size before any Cosmos write. Med risk.

## Acceptance

- Diffs accurately describe each mutation.
- Revert restores the exact prior itinerary and reflows all panes.
- Storage is bounded; no oversized Cosmos writes.
