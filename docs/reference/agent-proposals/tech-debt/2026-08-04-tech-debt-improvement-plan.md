# Tech-Debt Improvement Plan — 2026-08-04

Status: **Proposed, awaiting owner sign-off.** Nothing implemented yet.

Origin: owner prompt in [engineering.txt](../owner-inputs/engineering.txt) — periodic
tech-debt window. Requested analysis of (1) performance, (2) race conditions / high-probability
bugs, (3) architecture & maintainability vs. the repo principles in
[PRODUCT.md](../../PRODUCT.md) §6 "Owner taste — code & process" and the copilot-instructions
architecture invariants.

Analysis baseline: `origin/master` at `9ffc98b` (worker-3 synced 2026-08-04).

## Verified correction (do NOT re-file)

- **"SSE replay permit leak" is a FALSE POSITIVE.** The early replay path in
  [api.py](../../../src/tripplanner/api.py) (~L653) returns *before* `acquire_chat`, and the
  `finally` (~L676) releases `replay_permit`; the post-admission replay already carries
  `BackgroundTask(release_chat, permit)`. No leak. Excluded to avoid churning a safe path.

## Size hotspots (measured 2026-08-04)

Python: `web/trip_view.py` 3377, `tools/trip_planner.py` 2104, `api.py` 2104,
`agents/trip_agent.py` 936, `tools/user_preferences.py` 864, `web/chat_store.py` 831.
Frontend: `components/ChatPanel.tsx` 918, `components/MapPanel.tsx` 821, `App.tsx` 804,
`api.ts` 694, `components/TripPanel.tsx` 496.
Principle bar: one file per concern, ~400–500 line split guideline.

---

## P0 — Confirmed production bug (do first, standalone)

### 1. places_cache writes >2 MiB to Cosmos → `RequestEntityTooLarge`
- Evidence: live log `C:\repos\tripplanner\logs\diagnostics\local-app.jsonl`, repeated
  `places_cache cosmos persist failed: (RequestEntityTooLarge) ... 2.1–2.4 MB` at 04:17–04:32 on 2026-08-04.
- Root cause: [web/places_cache.py](../../../src/tripplanner/web/places_cache.py) evicts by
  entry count (`_MAX_ENTRIES = 800`, lazy, ~L195), not serialized byte size; the whole `_CACHE`
  dict is upserted as one document. Reviews (~300 chars each) + photo refs bloat it past 2 MiB.
- Also: individual getters (`get_summary` ~L465, `get_photos` ~L493) each call `_persist()`, so
  one `/trip/view` can trigger 10+ Cosmos upserts. `_batched_persist()` exists but is only used by `prefetch()`.
- Fix:
  1. Byte-size guard before upsert; if serialized snapshot > ~1.5 MiB, prune oldest and/or split.
  2. Prune entries older than the 1-week `_META_TTL_S` instead of relying on lazy count eviction.
  3. Cap stored review text (e.g. 100 chars) and drop redundant photo payload from the snapshot.
  4. Wrap `build_view`'s place warming in a single `_batched_persist()` block so per-getter persists collapse to one write.
- Risk: **low**, behavior-preserving. Owner suggested pair-fix separately from the assistant-error triage.

---

## P1 — Performance (backend hot path, behavior-preserving)

### 2. O(items × days × stops) rescans in trip_view
- [web/trip_view.py](../../../src/tripplanner/web/trip_view.py) `_place_occurrences` (~L1134),
  `_terminal_occurrences` (~L1155), and `_day_for_place` (~L1345) re-scan the full itinerary once
  per gallery item / map pin. 10 items × 7 days × 5 stops ≈ 350 substring matches per request.
- Fix: precompute one `{name.lower(): [{"day", "stop"}]}` occurrence map + `{pin_name: day}` map
  once in `build_view`; reuse across item/pin builders and return the pin→day map so the frontend
  stops re-scanning. Est. ~50ms → ~5ms on a 7-day trip.
- Risk: **low**.

### 3. Unbounded model context replay  (⚠ NEEDS EXPLICIT OWNER YES — can alter agent behavior)
- [graph.py](../../../src/tripplanner/graph.py) `_messages_for_model` (~L145) truncates individual
  tool results (1.5 KiB each, 12 KiB total) but replays the entire message list every turn; 20+ turn
  conversations re-send everything.
- Fix: after ~10 turns, summarize early conversation losslessly (preserve trip diffs + user
  constraints), keep last ~5 turns + summary.
- Risk: **medium** — behavior-sensitive. Do not implement without a separate yes.

---

## P2 — Concurrency / correctness (reproduce with a focused test, then fix)

### 4. Frontend stale-trip overwrite after trip creation
- [App.tsx](../../../frontend/src/App.tsx) (~L804) + [useChatStream.ts](../../../frontend/src/hooks/useChatStream.ts) (~L132):
  a trip-creating turn changes `active_trip_id`; an in-flight OLD trip view fetch can resolve after the
  new turn completes and overwrite `view` with stale `trip_id` / itinerary / focus.
- Fix: tie trip/map/itinerary fetches to a generation token; verify the SSE `done.trip_id` matches the
  fetched `trip.id` before committing; abort in-flight requests on trip/version change.
- Risk: **low–med**. Matches ENGINEERING_LEARNINGS "stale reads must not overwrite newer state".

### 5. chat_store migration/adoption races
- [web/chat_store.py](../../../src/tripplanner/web/chat_store.py) `adopt_state` (~L598) and first-trip
  general→trip migration (~L620–670): not serialized against a concurrent turn on the same trip; a turn
  written between merge and delete can be lost from the transcript / operation index.
- Fix: serialize adoption + migration with the existing workspace-exclusive lock (request_limits); or
  make source→target migration a single conditional swap.
- Risk: **med** — reproduce with a focused interleaving test before editing.

### 6. Silent partial-turn persist on error
- [api.py](../../../src/tripplanner/api.py) error path (~L828) swallows a failed `_save_chat` under a bare
  `except`, leaving trip-created-but-chat-lost (or vice versa) inconsistency invisible.
- Fix: log the persist failure and surface it (telemetry + client-visible for partial turns).
- Risk: **low**.

---

## P3 — Maintainability (split oversized files, pure moves, behavior-preserving)

### 7. Split web/trip_view.py (3377 → ~4 modules)
- `web/budget.py` — `fmt_money`, `_to_number`, `_sum_item_prices`, `traveler_count`, `build_budget` (~L77–200).
- `web/gallery.py` — `itinerary_items`, `_selected_names`, `_itinerary_names`, `_planned_place_names`,
  `_place_occurrences`, `_terminal_occurrences` (~L254–367, 541–590).
- `web/map_pins.py` — `_map_pins`, `_airport_pin`, `_haversine_km`, route/terminal/intercity helpers (~L949–1109).
- `web/schedule.py` — `_route_stats_*`, `_day_schedule`, `_enrich_stop_timing`, `_enrich_drive_transfer_timing` (~L1138–1468).
- Keep `build_view` as the assembling boundary; preserve the UI-independent view-model invariant. Risk: **very low**.

### 8. Split tools/trip_planner.py (2104 → 3 modules)
- `tools/trip_validation.py` — `*_warnings`, `_hotel_destination_errors`, `planning_completion_gaps`,
  `assess_itinerary_change` (~L156–619).
- `tools/itinerary_edit.py` — `_closest_insert_index`, `_remove_candidate`, `_rebalance_day`,
  `_place_selected_stop`, `add_selection`, `remove_selection` (~L693–955, 1252–1308).
- `tools/trip_history.py` — saved-trip list/load/delete/archive, `switch_active_trip` (~L1465–1598).
- @tool signatures unchanged. Risk: **low** (#6 itinerary_edit low–med since it's a core agent tool path).

### 9. Frontend api.ts (694) — extract auth + add cache TTL
- Extract Google OAuth / guest-session / `apiFetch` into `frontend/src/auth/authSession.ts` (~L90–210).
  (Report mislabeled the path as `src/tripplanner/web/api.ts`; correct path is `frontend/src/api.ts`.)
- Add a 5-min TTL + trip-switch invalidation to the destination-overview response cache (~L602).
- Risk: **low**; enables mobile auth reuse.

### 10. MapPanel memoization
- Wrap [MapPanel.tsx](../../../frontend/src/components/MapPanel.tsx) in `React.memo`; memoize
  `visitOrdersForDay` / `hotelLabelsForDay` results and the active-day pin map inside
  `map/overlaySync.ts` to avoid full overlay rebuilds on every chat-driven render.
- Risk: **low**.

---

## Deliberately deferred (avoid over-engineering this window)

- Typed Pydantic `Trip` / `TripView` / `TripItem` models replacing `dict[str, Any]` — medium-high risk,
  broad blast radius. Only if owner wants it.
- `TransportRoute` regex consolidation in trip_view.py — medium risk of subtle parsing changes.

---

## Suggested execution (parallelizable across workers)

Aligned with default worktree ownership; each item = one PR-sized commit + focused tests, validated once
per milestone, then guarded-integrated to master (same flow as prior wave).

- **Agent 3 (Infra/storage):** #1, #5, #6
- **Agent 2 (Detail-Chat / backend):** #2, #7, #8  (+ #3 only if approved)
- **Agent 1 (Iti-Map / frontend):** #4, #9, #10

## Validation gates per milestone

- Backend: targeted `pytest` suites + `ruff check` on touched files (`PYTHONPATH=src`,
  interpreter `C:\repos\tripplanner\.venv\Scripts\python.exe`).
- Frontend: `npm --prefix frontend test` on touched specs + `npm --prefix frontend run build`.
- Mobile (if touched): `npx tsc --noEmit` + `expo lint`.
- Infra (if touched): PowerShell `Parser::ParseFile` across `infra/*.ps1` + release-workflow tests.
- Do NOT start/stop the canonical stack (MasterAgent-owned); no deploys.

## Open decisions for owner

1. Scope: (a) all except deferred, (b) P0+P1 first then review, or (c) a specific subset.
2. Explicit yes/no on **#3** (graph context change) — only behavior-altering item.
