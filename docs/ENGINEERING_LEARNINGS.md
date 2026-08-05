# Engineering Learnings

Durable architectural and travel-domain lessons learned while building tripplanner.
This is a joint working log for decisions that should shape future features and
fixes. Keep entries concise, generalizable, and tied to observed behavior.

## 2026-08-05 - Split Modules at the Substitution Boundary

- A module can only be split where its callers do not reach inside it. Tests
  substitute `_place_coords`, `_airport_pin`, `_maps_browser_key` and
  `get_settings` on `trip_view`'s own namespace, so any extracted module that
  called them directly would silently bypass the substitution. The facade must
  resolve those dependencies itself and pass the resolved values in; the
  extracted module then does pure assembly and needs no test seams of its own.
- Prefer in-module helper extraction when a function's dependencies are mostly
  private helpers of the same module. Moving `build_itinerary` to a new file
  would have required importing a dozen private names across a new boundary;
  decomposing it in place into named steps removed the same complexity with
  none of the coupling.
- Duplicated accumulation is a reliable dead-code signal. The per-day coordinate
  list was built twice and the first result was unconditionally discarded before
  use — visible only once the enclosing 371-line function was read end to end.
## 2026-08-05 - A Shared "Last Run" Log Is a Lock, Not a Log

- Every entry-point script wrote its transcript to one fixed `logs/last-run/<script>.log`.
  That held while runs were serial. The moment a sandbox could be served in the
  background, its transcript stayed open for hours and every other invocation of the
  same script lost its log to a file lock — including the runs most likely to need
  diagnosing.
- Key the transcript by whatever makes the run distinct, not by the script name:
  sandbox runs by slug plus verb, the dev stack by API port. The canonical stack keeps
  its original name so existing habits and docs still point at the right file.
- Anything reaching a filesystem path before validation must be sanitised there.
  The sandbox slug names the log file before `Assert-Slug` ever sees it.

## 2026-08-05 - Verify Against a Running Endpoint, Not Just the Suite

- A blocking runner is not servable. `dev-spa.ps1` holds the terminal on
  `npm run dev` and tears the stack down in its `finally`, so the sandbox
  workflow could create an environment nobody could probe without a second
  window. Wrapping the existing runner in a detached process and waiting on its
  endpoints beat modifying the runner to background itself.
- Probe local dev servers by name, never by literal `127.0.0.1`. Vite binds
  `::1` only while uvicorn binds `127.0.0.1`, so a hardcoded IPv4 health check
  reported a perfectly healthy SPA as down. `localhost` lets the resolver try
  both families.
- Readiness budgets must match the slowest first-run path. A fresh sandbox
  installs frontend dependencies before Vite binds, so a timeout tuned to a warm
  start reports a false failure on exactly the run that matters most.
- Unit tests proved the refactored view-model assembly was consistent; only the
  live endpoints proved the day routes, legs, schedules, and hotel anchors it
  produces are still complete. Both are needed.

## 2026-08-05 - Recovery Belongs in the Flow That Broke

- A recovery step that exists only as a separate command is a step the owner has
  to notice, remember, and run. The conflict resolver was already scripted and
  non-interactive, yet every routine conflict still stalled a sync until someone
  invoked it by hand. Automation is not finished when the capability exists; it
  is finished when the failing flow calls it.
- Retry on state, not on an error message. The all-worktrees launcher aggregates
  per-lane errors into its own summary, so matching `SYNC_CONFLICT_PENDING` in
  the exception text silently missed the very case that needed help. Asking git
  whether unresolved markers exist works no matter who rewrapped the message.
- Automatic retry must be narrow enough to stay honest. A retry that fires on any
  failure would re-run a merge whose validation gate just failed and eventually
  let it through. Retrying only when a conflict is actually pending keeps the
  test gate authoritative, and Copilot stays denied `git push` so it can never
  publish what it edited.

## 2026-08-05 - Keep the Run Before the One That Failed

- Every launcher transcript was written with `Start-Transcript -Force`, so each
  run destroyed the only record of the previous one. Debugging a sync usually
  means comparing the failing run against the last good one, which is exactly the
  file the failing run had just overwritten.
- Two generations of history are cheap and enough. Rotating `<name>.log` to
  `.1.log` and `.2.log` costs nothing and removes a whole class of "please run it
  again so I can see the error" round trips.

## 2026-08-05 - A Gate Must Reproduce the Environment It Judges

- Integration validation ran pytest in a fresh merge worktree, where git-ignored
  local configuration like `.env` does not exist. Settings-dependent tests failed
  there and passed everywhere else, so the gate reported confident regressions
  that no commit had caused. Seed a validation sandbox from the primary checkout.
- A false regression is worse than a noisy one: it blocks the merge and, on the
  next clean pass, writes phantom ids into the baseline that then mask real
  failures. Verify a suspected regression against the same code in a known-good
  checkout before attributing it to the change under test.
- The bisect that matters is environment versus code. Swapping only `src` between
  the two trees, holding the test file and working directory constant, disproved
  the code theory in one run and pointed straight at the missing config.

## 2026-08-05 - A Merge Driver Only Helps Once It Is Declared

- Append-only logs kept conflicting even though the repository already used Git's
  union driver, because the attribute named only two of the three files. Union is
  not a policy the tooling infers; it applies strictly per declared path. Confirm
  coverage with `git check-attr merge -- <path>` rather than assuming it.
- Union is correct only while every writer appends. The moment an agent edits or
  reflows an existing entry, union keeps both versions silently, which is a
  quieter and worse failure than a conflict. Pair the attribute with a written
  rule that entries are immutable once recorded.
- Structured documents that agents genuinely revise must stay conflict-visible.
  The safe test is whether two lanes' versions of the file are always meant to be
  concatenated; if not, the file does not belong in the union list.

## 2026-08-05 - An Empty Gate State Must Not Read as an Absent One

- A regression gate has three distinct states — no baseline, green baseline, and
  known failures — and collapsing the middle one into the first turns the gate off
  exactly when it should be strictest. The clean run seeds; the next real
  regression is then absorbed as "pre-existing" and never blocks.
- In PowerShell this happened silently: `return @($data.failures)` unrolls an empty
  array to `$null`, so a green baseline read back as "no baseline". Return `, $ids`
  when a collection's emptiness carries meaning.
- The visible symptom was a recurring warning about failures that already passed.
  The warning was the artifact; the real defect was a gate that had stopped
  blocking. Treat a nagging false warning as a signal to check what it guards.

## 2026-08-05 - Pin Every Package Source the Image Build Touches

- The corporate network TLS-blocks the PyPI CDN (`files.pythonhosted.org`) while
  `pypi.org` itself still answers, so a package index that resolves is not proof
  that its downloads will. Verify the download host, not just the index.
- This is host-wide, not container-specific. Reproducing the failure on the host
  before blaming Docker avoids a long detour through image and cache theories.
- The build reached the same failure twice because only npm had been routed to
  the 1ES public mirror. When one ecosystem needs a mirror, route every ecosystem
  the image build touches; a partial fix reads as fixed until the next clean build.
- Read `logs/last-run/<script>.log` first. The canary transcript named the failing
  step immediately, but not the underlying tool output, so rerun the tool directly
  with plain progress to get the real error.

## 2026-08-05 - Reconcile Sync State With Git State

- A successful branch update can still fail while restoring a safety stash. That
  leaves unmerged index entries without `MERGE_HEAD`, so recovery must model stash
  conflicts separately and must not commit or push the restored local edits.
- A sidecar pending-state file is a recovery aid, not the source of truth. Before
  syncing or resolving, reconcile it with Git's unmerged indexes so interruption
  or stale metadata cannot make the resolver falsely report that nothing is pending.
- Concurrent tail appends to owner-authored chronological logs should use Git's
  union driver; semantic resolution adds risk without useful conflict information.

## 2026-08-05 - A Transcript Only Sees What PowerShell Writes

- `Start-Transcript` records the PowerShell host's own output. An unpiped native
  process inherits the console handles and writes past the transcript, so the
  failing output an operator reads on screen never reaches the log file.
- Stream long external tools through PowerShell (`Invoke-LoggedNative`) so their
  merged stdout and stderr land in the run log. Docker and the Azure CLI degrade
  to line-oriented output when they are not attached to a terminal, which is the
  better form for a log anyway.
- Redirecting native stderr with `2>&1` yields error records, so a caller running
  under `$ErrorActionPreference = "Stop"` terminates on the first progress line.
  Capture wrappers must relax that preference locally and check the exit code.
- A log without a start stamp, an outcome, and an elapsed time cannot answer when
  a run happened or how far it got. Emit those from the shared logging entry
  point, not per script.

## 2026-08-03 - Keep Display Identity Authoritative Across Surfaces

- Provider metadata may enrich authoritative itinerary places, but a first search
  result must not rename or relocate a stop without a plausible identity match.
- Aggregate day focus and exact-place focus are different selection states. Test
  viewport, itinerary highlight, and details-tile context together so one surface
  cannot retain stale place state after another moves correctly.
- Shared concepts need shared normalization and formatting. Exact hotel strings,
  pin IDs, and duplicate duration formatters create cross-surface regressions even
  when each component looks locally correct.
- Hotel aliases can differ by omitted locality as well as spelling or generic
  property words. Compare meaningful property-name tokens across every labeling
  surface while preserving fully qualified same-brand hotels in different cities.
- Persisted mode fields and display names are independent evidence. Normalize them
  once before deriving terminal expansion, clickability, or map edges; requiring a
  magic `Drive:` prefix makes valid saved car legs disappear from interaction.
- Parse transport wording before splitting route endpoints. Otherwise labels such
  as `Drive from A to B` create a fake `Drive from A` origin and only appear to
  work on days where a carried hotel later happens to replace that bad endpoint.
- Transfer chronology crosses day boundaries. If a later transfer omits its origin
  stay, carry the prior active hotel into both itinerary and map derivation rather
  than inventing a city origin in one pane or dropping the endpoint in the other.
- A transfer mode applies to an ordered journey, not only the first edge after its
  label. Preserve it through authored scenic and meal waypoints until the
  destination stay, and calculate guidance from that same complete path.
- Grounded route distance and duration are persisted domain data, not display
  labels. Preserve them through normalization and allocate the same exact totals
  across itinerary and map waypoint legs; independent geometric estimates make
  two correct-looking surfaces contradict each other.
- An inter-city road journey is independently focusable domain data, not a
  day-number display mode. Give every Drive or Bus circuit a stable identity,
  explicit scenic/meal waypoint roles, ordered pins and legs, and authoritative
  route metrics. Filtering a day route cannot reliably distinguish that journey
  from destination-local geometry.
- Build each road circuit from its own resolved endpoints, not from
  opportunistically tagged day-route legs. Reconstructing a circuit from legs that
  only get tagged when a following non-terminal place pin appears silently drops
  every journey whose destination is a terminal (hotel-to-airport departures) or the
  next transfer (chained drives), so the circuit never maps and never zooms.
  Resolve origin (prior place pin, carried stay, or parsed origin), on-the-way
  waypoints, and destination (next hotel, the next transfer's origin terminal, or
  parsed destination) directly for every road-transfer row.
- A focus fit must always be consumed. When a drive-circuit fit can fail because
  the circuit is missing or unbuilt, fall back to the day-route fit instead of
  leaving the pending focus set, or the map silently retries the same failure on
  every redraw and never frames the drive.
- Resolve typed hotel identity before generic partial-name matching. Shared words
  such as Hotel, Resort, or a locality can otherwise attach a day's circuit to a
  different selected stay and silently remove its real endpoints.

## 2026-08-03 - Require Native Environment Selection

- A hardcoded production fallback turns missing development configuration into
  real production traffic. Native builds must select their API environment
  explicitly and fail during startup when it is absent.
- Keep public endpoint selection in build configuration, not source code. Test
  normalization and missing-value behavior at the shared client boundary.

## 2026-08-03 - Long Agent Work Needs Two Completion Boundaries

- Token streaming alone does not reassure a user during multi-minute tool and model
  work. Surface truthful domain milestones, one total elapsed clock, and a measured
  expected range in both the initiating pane and persistent workspace status.
- Agent completion and usable-screen completion are different events. Report loading
  after the terminal SSE event, and declare success only after the authoritative view
  refresh succeeds; otherwise retain the prior view and report the reload failure.
- Restarting elapsed time on every subtask hides the true wait. Keep one turn start,
  change only the milestone label, and never fabricate percentage-complete estimates.

## 2026-08-03 - Treat Trip Shape as a Deterministic Product Decision

- A global date-range fallback silently becomes a duration recommendation. It can
  produce sparse plans that satisfy minimum itinerary completeness while feeling
  obviously worse than manual planning.
- Keep explicit duration authoritative, but derive flexible duration from ranked
  place workload, travel overhead, partial-day capacity, destination scope, and
  the traveler's learned daily capacity. Persist the evidence and reasons.
- Validate both maximum fullness and minimum usefulness. Exempt genuine transfers,
  partial days, and deliberate leisure; never solve sparsity with low-value filler.
- Personal outcomes and platform aggregates are different trust domains. Personal
  pace can learn from stated post-trip feedback. Cross-user insight must be
  anonymized, versioned, cohort-gated, confidence-gated, and tightly bounded.

## 2026-08-02 - Bound Semantic Work Before Framework Recursion

- Framework recursion limits count graph nodes, not meaningful planning work. A
  normal agent/tool alternation can exhaust the limit after twelve tool phases
  even when every tool succeeds.
- Enforce a smaller domain-level tool-phase budget that reserves a terminal model
  round. Unexpected framework exhaustion should summarize persisted side effects
  instead of returning a generic error.
- A parallel provider batch is usable when any subquery returns grounded choices.
  Triggering a fallback because one city failed adds research and synthesis rounds
  without improving successful cities.
- Log model latency, prompt size, tokens, tool phase, forced-gate reason, and
  remaining-gap count together. Tool-only timing can misattribute more than 90%
  of a slow planning turn.

## 2026-08-02 - Preserve Compose Identity When Moving Files

- Docker Compose derives its project identity from the Compose file directory
  unless a project name is explicit. Moving a file can make a healthy existing
  container look unrelated and cause fixed container-name collisions.
- Preserve both project and volume identities when relocating stateful Compose
  services. Validate the resolved project and confirm the existing container is
  discovered before running `up`.

## 2026-08-01 - Budget Parallel Research Before Synthesis

- A parallel research batch can succeed at every provider and still fail when
  all verbose tool results are replayed into the next model call. Diagnose the
  terminal model response separately from tool health.
- Keep full tool results in graph state for persistence and diagnostics, but send
  bounded copies to synthesis. Distribute the budget across every result so a
  multi-city plan does not discard one destination entirely.
- Pair context reduction with bounded provider retries. Retries alone prolong a
  token-bucket failure, while truncating stored state would destroy evidence.

## 2026-07-31 - Synchronize Rejected Placeholders

- Filtering a placeholder from a selected-items collection does not remove the
  same placeholder from a separately persisted itinerary.
- When one concrete replacement is unambiguous, synchronize placeholder anchors
  even if the prior selected-items collection was empty. A normal old-to-new diff
  cannot detect a placeholder that was deliberately rejected from that collection.
- Validate both normalized selections and rendered itinerary occurrences; either
  can look correct while the other retains stale planning data.

## 2026-07-31 - Never Recover Create With Update

- Treat an explicit whole-trip request for a destination different from the active
  trip as a creation boundary before running any itinerary-completion gates.
- A fallback updater must prove that the same operation created the object it is
  repairing. Never apply parsed output to whichever unrelated object happens to be active.
- Prompt instructions are insufficient for identity-changing writes. Deterministic
  orchestration must establish the destination-specific trip before enrichment begins.
- Diagnose cross-object corruption from persisted operation identity plus tool telemetry:
  a completed turn can be operationally healthy while every update targets the wrong object.

## 2026-07-31 - New Intent Must Preempt Old Completion Gates

- An active domain object does not imply that every planning message mutates it.
  Explicit new-object language must enter the creation workflow even from an old
  object's scoped conversation.
- Once a required structured kickoff has been answered, force the create mutation.
  Prompt guidance alone can leave the user chatting against the prior object.
- New-object routing must run before quality/completion gates for the old object;
  otherwise an incomplete old state can capture and mutate a clearly separate request.

## 2026-07-30 - Validate Geographic Identity Before Persistence

- Preference fit, price, and luxury do not compensate for a hotel in the wrong
  destination. Preserve searched locality on normalized offers and selected plans.
- A search destination is query context, not proof of a returned property's physical
  location. Validate actual city, address, and country evidence independently.
- Reject explicit hotel locality mismatches atomically at the mutation boundary;
  a late finalization warning leaves every live workspace surface showing bad data.
- Prompt instructions should retain provider evidence, but deterministic persistence
  validation owns the invariant when the model strips or misreads that evidence.
- A selected-hotel replacement is incomplete until the structured itinerary anchors
  change in the same write; chat confirmation and selection metadata alone do not
  update itinerary or map truth.

## 2026-07-30 - Keep Deterministic Gates Cheap

- Measure model rounds separately from tool execution. A 49.5-second planning
  turn with 1.17 seconds of tool work is an orchestration problem, not a reason
  to optimize persistence or provider code.
- When the graph forces one tool, bind only that tool's schema. Resending every
  unrelated schema adds context cost without giving the model any real choice.
- Handle a known primary-provider outage inside the provider tool when a
  grounded fallback has the same contract. Requiring the model to notice the
  failure and choose the fallback adds a full inference round.

## 2026-07-30 - Preserve Provider Evidence Semantics

- Keep place identity/reviews separate from date-specific inventory evidence.
- A provider's activity from-price is not an exact party total, and an operating
  schedule is not a held quote. Preserve those distinctions in normalized models.
- Return affiliate deep links unchanged; provider attribution parameters are data,
  not URLs for the application to reconstruct.

## 2026-07-30 - Complete Persisted Defaults Across Provider Failure

- Enforce required defaults from persisted state, not from whether the model
  happened to call a research tool. A complete itinerary with a placeholder
  hotel is still incomplete even when the first update succeeded.
- A forced provider call is not a completion guarantee. Inspect its result and
  deterministically route known unavailable, empty, or error outcomes to a real
  fallback before forcing the final persistence step.
- Regression tests for agent completion must cover the sequence boundary:
  immediate draft, missing required default, primary-provider failure, fallback
  research, and the final persisted replacement.

## 2026-07-28 - Enforce Persistence at the Agent Boundary

- Prompt instructions are not a completion guarantee. If a newly created
  domain object requires a second mutating tool call before it is useful, make
  that call a graph-level completion gate rather than relying on prose or a
  best-effort response parser.
- A fallback updater cannot recover a missing create operation, and format-based
  parsing cannot recover prose that does not match its headings. Test recovery
  from an empty workspace, not only with the update tool mocked.
- Keep request-level and child-operation timers in separate variables. A reused
  closure variable can corrupt terminal telemetry or fail before the transport's
  final completion event, preventing client invalidation even after persistence.
- Completion gates should evaluate persisted domain quality after research, not
  merely whether an update tool was called once. Require researched choices to
  replace the first cut, but cap corrective retries so missing provider data
  degrades honestly instead of creating an infinite agent loop.

## 2026-07-28 - Performance Evidence Has Distinct Layers

- A hermetic in-process benchmark is a regression tripwire, not production
  capacity evidence. Keep real routing, identity, thread offload, and admission
  while replacing network, provider, and persistence variability.
- Rebuilding map markers, routes, labels, and listeners is synchronous main-thread
  work even when the underlying data is already loaded. Schedule that work after
  the focus-state paint and cancel superseded frames so rapid navigation builds
  only the latest requested scope.
- Deferred rendering tests should assert final visible state and geographic
  bounds, not the exact number or ordering of intermediate viewport fits.
- Use a conservative percentile ceiling with warmups and repeated samples to
  detect gross blocking or accidental network access without optimizing CI noise.
- Production SLO telemetry, Cosmos RU/throttling metrics, and billing reports
  answer different questions. Correlate them before changing code or capacity,
  and optimize only the bottleneck supported by repeated evidence.

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

## 2026-07-30 - Cancellation Is Not Replay

- User cancellation belongs at the streaming transport boundary. Abort the active
  fetch/read, let server disconnect cleanup release admission, and recover the
  composer without failure telemetry or a same-request retry affordance.
- Token paints and transcript hydration are asynchronous writers. A cancelled turn
  must cancel queued token work, and initial history restoration must finish before
  accepting a new turn so stale rows cannot replace newer visible state.
- Chat edits cannot imply rollback when a prior turn may have persisted itinerary
  mutations. Preserve the audit trail and send revised text under a fresh operation
  identity as a corrective turn.

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
- Preserve the itinerary source name beside the provider-canonical map name.
  Exact focus and repeated-terminal occurrences must resolve through that alias;
  deleting it at serialization breaks cross-surface identity after enrichment.
- Map occurrence indexes must come from the rendered itinerary when presentation
  expands one persisted stop into multiple rows. Mixing raw indexes with rendered
  click indexes makes valid exact-stop focus requests silently miss their pin.
- Explicit airport names are self-locating provider queries. Appending the trip
  destination can resolve an origin airport to an unrelated destination-region
  airport, and the cache key must use the same unbiased query context.
- Geographic distance does not prove transit capability. A 10 km urban leg may
  support Metro in one city and not another; use a conservative Taxi fallback
  until a route source explicitly establishes transit service.
- Airport schedules need separate flight, preflight, and post-arrival clocks.
  Keep persisted/provider flight timing authoritative, label derived timing as
  estimated, and apply configurable check-in/security and baggage/exit buffers
  before calculating the next itinerary stop.

## 2026-07-26 - Persisted Services Need Runtime-State Recovery

- A persisted database volume can retain process locks after an abrupt container
  stop even when its data is healthy. Readiness must distinguish stale runtime
  state from corrupt data instead of waiting repeatedly or resetting the volume.
- PostgreSQL lock cleanup is safe only after proving no server process exists.
  Remove the complete runtime lock set, restart once, and preserve all database
  files; never turn automatic local startup into automatic data deletion.

## 2026-08-05 - Atomic Panel Switch And One Notice Channel

- A panel that intentionally keeps prior content while refetching becomes the
  visible tear in an otherwise atomic trip switch. Reset such caches during
  render when the identity prop changes; an effect-based clear still paints one
  stale frame after every other panel has already swapped.
- Long workspace operations need a single global notice channel with explicit
  ids, tone-based priority, and outcome replacement. Per-surface banners cannot
  express in-progress state and compete for the same screen space.
- Hold a workspace lock only across the state flip. Building read-only view
  models inside the lock lengthens the window enough for unrelated requests to
  collide, and the client should still retry once on a 409 using Retry-After.

## 2026-08-05 - Per-Call HTTP Clients Dominated Trip Switch Latency

- A cold trip switch spent 14.1s server-side. Profiling attributed 6.7s of
  self-time to TLS context setup: warming one destination issues ~60 Places
  calls, and `httpx.get`/`httpx.post` build, verify, and discard a client per
  call. A process-wide pooled client with keep-alive cut that path to 0.05s and
  the live switch to 0.3-1.4s. Route outbound HTTP through the shared client
  rather than the module-level convenience functions.
- Best-effort persistence must never run on the request thread. A single stalled
  cache upsert against the local emulator added 65s to a switch that had already
  produced its answer. Hand durable cache writes to a background writer and
  expose an explicit drain hook so tests can still assert on the store.
- Measure through the running endpoint, not the profiler alone: the profile
  named the hot function, but only the live switch showed how much of the wall
  clock the user actually felt.

## 2026-08-05 - Render-Phase State Resets Need A State Tracker, Not A Ref

- Resetting derived state when a prop changes must compare against a `useState`
  tracker, not a `useRef`. A ref mutates immediately, but React can discard a
  concurrent render and replay it from the last committed state: the queued
  `setState` resets are thrown away while the ref keeps the new value, so the
  reset never fires again. Console tracing showed exactly that - the retry render
  saw the cleared value, and a later render was back to the stale one.
- Unit tests passed on the ref version because React Testing Library renders
  synchronously and never discards a render. The bug only appeared in the running
  app during a trip switch, so verify render-timing fixes live, not just in
  vitest.

## 2026-08-05 - Colliding Refactors Are Redone On The Merged Base, Not Picked

- Two sandboxes split the same 520-line `build_map_view` in different
  directions: lab 14 pulled out `day_journey` and deleted the pending-intercity
  state machine, while the refactor sandbox moved the whole body, state machine
  included, into `map_view`. Git offered ours-or-theirs, and both answers were
  wrong: ours reintroduced deleted code, theirs threw away the extraction.
- The resolution that works is to take the already-merged side as the base and
  re-perform the other side's mechanical move on top of it. Here that meant
  keeping `trip_view`'s facade, then rewriting `map_view` to plan journeys
  through `day_journey` and keep only the pure assembly. Same tests, same
  behaviour, no resurrected code.
- The signal to look for before merging is a semantic collision rather than a
  textual one: grep the incoming branch for identifiers the base branch deleted.
