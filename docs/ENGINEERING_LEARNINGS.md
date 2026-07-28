# Engineering Learnings

Durable architectural and travel-domain lessons learned while building tripplanner.
This is a joint working log for decisions that should shape future features and
fixes. Keep entries concise, generalizable, and tied to observed behavior.

## 2026-07-28 - Replay Intent, Not Stale Snapshots

- An ETag protects only the state it was read with. Reading a fresh ETag and then
  attaching it to an older full-document snapshot still loses concurrent data.
- Model each read-modify-write operation as semantic intent that can be replayed
  against a fresh body after a conditional create or replace conflict.
- Append-only transcripts need the exact completed turn as their write unit.
  Inferring a suffix from a capped full-history snapshot becomes ambiguous once
  the retained window shifts under a concurrent writer.
- Idempotent conflict retries need operation identity separate from message text.
  A bounded fingerprint ledger suppresses exact retries while preserving two
  legitimate identical turns that started from different transcript bases.
- Request identity must survive transport failure and storage-bucket migration.
  Let the caller retain it, persist completed/interrupted operation state, and
  return a completed replay before applying admission rules for new model work.
- Trip-scoped dedupe cannot replay after another tab changes the active trip.
  Keep a bounded principal operation index, persist completion there first, and
  use its original request text to repair a missing transcript on replay.
- Replay-before-admission still needs an abuse and lifecycle boundary. Throttle
  storage lookups separately from model work and count lookup/repair as active
  workspace access so deletion or identity migration cannot race data recreation.
- Identity adoption must merge all durable conversation state, not just visible
  messages for the active trip: include general and saved-trip buckets,
  interrupted request metadata, and completed replay results.
- Cross-document moves are not atomic just because both writes are conditional.
  Copy every newly observed source suffix, then delete only the exact source ETag;
  on conflict, reread and replay before considering cleanup complete. If the
  destination append fails after identity state changes, reconcile the retained
  source into the now-active destination on the next request.
- Default-valued settings need explicit ownership metadata. Sparse clients must
  send only edited fields, and identity adoption must transfer ownership only for
  guest values that actually contributed to the merged result.
- Account-scoped native reads need the same abort/generation guard as trip reads;
  otherwise a response from the prior identity can overwrite the signed-in view.

## 2026-07-28 - Bound Idempotency to the Provider Write

- A completed-response ledger does not close the crash window after provider
  acceptance but before local completion persistence. Carry one caller-owned
  operation ID through the API and into the provider's idempotency primitive.
- Never fail over to a second write provider after an ambiguous first-provider
  result. The fallback can turn one logical request into two real side effects.
- Providers without idempotency support can only offer at-most-once claiming.
  Persist the claim before sending and surface uncertainty instead of silently
  retrying an operation whose outcome cannot be proven.
- Bind request IDs to a fingerprint of principal-owned target and payload. A
  repeated key may replay the same operation but must reject changed content.

## 2026-07-28 - Recovery Requires Offline Evidence

- A database-to-database copy is migration tooling, not a backup, when restore
  still depends on the source remaining readable. Materialize a portable
  artifact and prove recovery from that artifact alone.
- Validate checksums and item counts before the first target write, then compare
  exact restored content. A successful write loop is not recovery evidence.
- Recovery tooling must make the dangerous target impossible by construction:
  reject live environment names, same coordinates, nonempty targets, missing
  containers, and partial scopes before restoring anything.
- Report RPO as artifact age and RTO as measured restore duration. A manual
  drill proves recoverability but does not imply continuous point-in-time backup.
- Generated summaries must validate both their durable input digest and the
  user-editable summary state observed before generation, or late model output can
  overwrite a concurrent user correction.

## 2026-07-26 - Cross-Surface Interaction Consistency

- One conceptual action must have one owner-level behavior across every surface.
  A day click in Itinerary and a day click in Map both mean aggregate day-circuit
  focus: clear exact-place selection, activate that day, fit the full route, and
  place the itinerary at the start of the day-level summary.
- An all-days map action is aggregate trip focus: clear exact-place and
  single-day circuit state, fit every circuit, and place the itinerary at its
  trip-level summary. Model this as an explicit summary target, not a fake Day 0.
- Exact-place focus and aggregate day focus are mutually exclusive modes. Do not
  let a component invent a representative-place side effect for a day-level action.
- Selection styling must be exclusive and visually distinct from status styling.
  Warnings, booking state, and "In trip" state must not make multiple rows look
  selected; only the current exact occurrence receives the selected card/marker
  treatment.
- When adding an interaction available in multiple panes or form factors, verify
  the same acceptance matrix everywhere: owning state, map viewport, itinerary
  current row, Details context, desktop wiring, and mobile wiring.
- Prefer shared App/workspace handlers over parallel component-local semantics.
  Local state may render the action, but it must not redefine what the action means.
- A completed agent turn is a trip-content invalidation boundary. Refreshing
  Details directly is insufficient when Map and Itinerary subscribe to a shared
  revision token; advance that token in the same owner-level completion handler
  so all mounted panes request the persisted plan concurrently.
- Rendered itinerary arrays are zero-based, but persisted occurrence identities
  are one-based. Translate once at the navigation boundary so repeated-place
  move/remove actions target the exact backend stop.
- A multi-surface refresh is one logical request generation. Share one abort
  signal across its reads and commit results only while that generation is
  current; otherwise an older trip can overwrite a newly selected one.

## 2026-07-26 - Itinerary Chronology Is One Contract

- Persisted stop-array order, displayed visit times, itinerary numbering, and map
  circuit order are four views of the same schedule. Validate them together.
- Route optimization or cross-day reflow invalidates old time slots. Reorder meals
  and visits coherently, then recompute times with duration and transfer buffers;
  never preserve stale times on moved stops.
- Reject model-authored duplicate or backwards visit times atomically. A warning
  after saving is too late because every downstream view will faithfully render
  contradictory source data.
- Provider-canonical place names may not match itinerary text. Route completion
  must use authoritative occurrence day/stop identity, not global pin insertion
  order, so name enrichment cannot reorder a circuit.

## 2026-07-26 - Persisted Services Need Runtime-State Recovery

- A persisted database volume can retain process locks after an abrupt container
  stop even when its data is healthy. Readiness must distinguish stale runtime
  state from corrupt data instead of waiting repeatedly or resetting the volume.
- PostgreSQL lock cleanup is safe only after proving no server process exists.
  Remove the complete runtime lock set, restart once, and preserve all database
  files; never turn automatic local startup into automatic data deletion.
