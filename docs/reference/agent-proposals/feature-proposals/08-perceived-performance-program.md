# Feature 08 — Perceived-Performance & Responsiveness Program

- **Pillars:** D (breezy, not laggy), A (breezy UX), B (smooth editing)
- **Status:** Proposed (new coherent program; incorporates tech-debt items #2 and #10)
- **Size:** L · **Risk:** low–med · **Suggested lane:** Agent 1 (frontend) + Agent 2/3 (view-model + cache)

## The pain

Laggy edits and reloads kill the "breezy" feel. Whole-itinerary refreshes, un-memoized map
overlays, and long lists cause jank; the planning turn itself can feel slow without steady,
truthful feedback. The owner's original latency concern (see
[`../../owner-inputs/Performance.txt`](../../owner-inputs/Performance.txt)) is directly on point.

## Outcome

The workspace feels instant: edits apply optimistically and reconcile, long lists
virtualize, place details prefetch on hover/focus, and map overlays memoize — turning
"laggy" into "breezy" while keeping the truthful build-progress feedback.

## Bounded v1 (bundle of low-risk wins)

1. **Optimistic mutations** — apply add/remove/move/reorder client-side immediately, show a
   quiet "updating…", then reconcile with the authoritative reflow (supersede rule
   preserved). This is the foundation under Features 02 and 03.
2. **Precompute occurrence maps** in `build_view` (tech-debt #2): O(items×days×stops) →
   O(1) lookups (~50 ms → ~5 ms on a 7-day trip).
3. **Memoize map overlays + `React.memo` MapPanel** (tech-debt #10) for smooth drag/focus.
4. **Virtualize long lists** (itinerary / gallery / reviews) so large trips stay smooth.
5. **Prefetch place Details on hover/focus** using the `places_cache` split cache; keep the
   300 ms stale-swap and never blank a pane.

## UX

- The user perceives an immediate response; the authoritative result quietly confirms.
  Dimmed stale content swaps at 300 ms (existing taste); no blanking.

## Implementation notes

- **Frontend:** optimistic layer in `frontend/src/workspaceState.ts` + `frontend/src/api.ts`;
  virtualization in `ItineraryPanel` / `DestinationOverview`; memoization in `MapPanel` /
  `map/overlaySync`; a hover-prefetch hook.
- **Backend:** occurrence-map precompute in `src/tripplanner/web/trip_view.py`; ensure
  `places_cache` batched persist (shared with the tech-debt **P0** fix) so prefetch does not
  multiply Cosmos writes.

## Perf / privacy / cost

Fewer redundant scans and writes; no new provider calls; lower Cosmos RU usage.

## Risks & mitigations

- **Optimistic vs. authoritative divergence** → always reconcile to server truth and
  supersede stale reads (existing invariant). Low–med risk.

## Acceptance

- Edits feel instant and reconcile correctly; no stale read overwrites newer state.
- Large-trip scroll and overlay drag stay smooth.
- No oversized cache writes; build/refresh feedback stays truthful.
