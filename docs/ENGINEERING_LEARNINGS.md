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
## 2026-08-05 - Partition Agent Logs Instead of Merging Them

- The shared owner prompt log conflicted on almost every parallel task, and each
  conflict invoked the Copilot CLI resolver to re-derive an answer nobody
  disputed. A log with no semantic content should never cost a model call.
- Union merge is a safety net, not a design. It survives concurrent appends, but
  it cannot stop two lanes from allocating the same entry number, and prepending
  newest-first forces every lane to read the shared file before writing.
- Partitioning removes the merge entirely: one file per lane means two lanes can
  never touch the same file. Prefer that over any merge strategy for a new
  agent-written log.
- Tail-append plus a timestamp identifier makes a log write a pure append. No
  read, no counter, no coordination, so the cheapest write is also the one that
  cannot conflict.
- The real conflicts came from the one file that was left off the union list.
  When a strategy depends on an allowlist, the omission is the defect, so derive
  the allowlist from a single source and have the tooling read it.

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

## 2026-08-05 - A Merge Reported As Done Is Not A Merge Verified

- Promotion printed the discard hint straight after `gh pr merge` returned 0, so
  the agent asked the owner to discard a sandbox it had never re-inspected. The
  CLI's exit code only says the request was accepted: branch protection can queue
  the merge, and the validation step runs long enough for an editor or formatter
  to dirty the worktree after the initial clean-tree check.
- The last step of promotion now asks git, not the tool that did the work: the
  worktree is clean, the branch is pushed, and `origin/<base>..HEAD` is empty.
  Anything outstanding throws instead of printing the discard hint.
- Discard refuses on the same three conditions unless `-Force`, so the
  destructive verb re-derives safety itself rather than trusting that whoever
  called it had already promoted. Both verbs share one function, which is what
  keeps the two answers from drifting apart.

## 2026-08-08 - A Partial Tool Payload Must Merge, Not Replace

- `update_trip_plan` wrote `plan[key] = val` for every key, so when the model
  resubmitted only the day it had edited, `day_wise_itinerary` lost every other
  day. The owner saw a three-day trip collapse to Day 1 after asking for a cheaper
  hotel, and the obvious suspect was a stray UI filter — the frontend was innocent.
- A tool argument that names a whole collection is a claim about the whole
  collection only when the model means it to be. `_merge_itinerary_days` now
  treats a strictly shorter incoming list whose day numbers are a subset of the
  planned days as a partial edit, replaces those days in place, and keeps the rest.
  A same-length or longer list, an unnumbered day, or a day the plan does not have
  still replaces outright, because those are the shapes that mean "the trip changed".
- The merge is announced back to the model in the tool reply, so a genuine
  shortening is not silently refused: it reads the note and resends the full list.
- The general rule for any destructive tool write: decide replace-versus-merge from
  the payload's relationship to the stored value, never from the fact that the key
  was present.
## 2026-08-06 - A Held Transcript Silently Files Output Under Another Name

- A served sandbox holds its `-Run` transcript open for hours. A second run of
  the same verb could not open the file, `Start-RunLog` returned `$null` without
  registering anything, and the nested `dev-spa.ps1` then opened its own
  transcript. The run was not merely unlogged: its output was filed under
  `dev-spa-8110.log`, so the log that was read while debugging belonged to a
  different script.
- Registration and transcription are now separate. `Start-RunLog` always records
  a marker in `$global:TripplannerRunLog`, with a `Transcript` flag saying
  whether a transcript actually opened, so the nested-script guard holds even
  when logging fails. A locked shared file falls back to `<name>.pid<id>.log`
  instead of dropping the transcript, and those private files are pruned after
  three days.
- A process that already redirects its own output must opt out rather than
  compete for the shared file. `TRIPPLANNER_RUN_LOG=0` is set for the detached
  sandbox runner, which writes to `logs/sandbox/<name>.log` regardless.

## 2026-08-06 - Sandbox Discard Safety Is Relative To The Base

- A promoted sandbox was synchronized forward to current `master`, while its
  remote sandbox branch stayed at the merged feature tip. Comparing `HEAD` only
  to that stale remote falsely classified ordinary `master` commits as unpushed
  sandbox work and blocked discard.
- Destructive safety asks the actual loss question: is the worktree dirty, or
  does `origin/<base>..HEAD` contain commits? A lagging sandbox remote is harmless
  when every local commit is already in the base.
- Promotion records verification evidence before automatic teardown. If any
  cleanup step fails, the registry entry and promoted status remain visible for
  retry instead of reporting success and orphaning hidden resources.

## 2026-08-06 - UX Lab Status Is Not In The Repository

- Lab lifecycle state is owned by the machine-local decision store at
  `%LOCALAPPDATA%/Tripplanner/ux-labs/selections.json`, written by the Labs dev
  server. `labRecords.ts` only carries the fallback default. Reading the
  committed file alone reported ten open labs when four were open, one parked and
  the rest completed.
- Run `pwsh -File scripts/dev/show-lab-status.ps1` before quoting which labs are
  open. It prints live state beside the committed default and flags drift.
- The record now carries one status field: `defaultDisposition` is required and
  the displayed label is derived from it. A free-text `status` string, a separate
  `completedLabs` array, and a card that fell back to `In evaluation` whenever
  no decision was saved were three independent ways for the same lab to claim
  three different states.

## 2026-08-06 — UX Lab state is not review history

A mutable current selection cannot prove owner review. Every handoff save must append immutable option, notes, state, and time evidence. Lifecycle state is independently selectable and must not erase history. Implementation evidence is a separate append-only record linked to the handoff version.

## 2026-08-07 - Isolation Is A Promotion Boundary, Not A Synchronization Boundary

- A sandbox is isolated in execution, data, ports, and the direction in which
  its changes flow. It should still receive `master` frequently so integration
  conflicts are discovered while the feature context is fresh.
- "Sync all to latest" means every registered branch is current locally and on
  its remote. After receiving its own remote head and `master`, a sandbox update
  pushes the resulting committed head; a rejected non-fast-forward push is a
  failure and is never repaired with force.
- Regular synchronization never promotes sandbox commits into `master`. Only
  the explicit promote workflow validates, opens and merges the PR, verifies
  containment, and tears down the isolated environment.

## 2026-08-07 - An Invariant Nobody Reads Back Is Not A Guard

- The trip guard shipped with a working temporal invariant that would have
  caught a stop scheduled on top of an intercity drive. Nothing called
  `validate_plan` on the result of a rebalance, so the mutation reported
  success anyway. Writing the rule and enforcing the rule are separate pieces
  of work; a guard layer is only as strong as the point where its output is
  read. Report only the violations the edit itself introduced, so inherited
  flaws do not turn the check into noise.
- Special cases written for the trip's arrival and departure legs quietly
  applied to every journey. A day trip is transport too, and skipping "all
  transport" when computing occupancy told the scheduler that the hours the
  traveller spends in a car are free. Scope an exemption to the specific
  entities it was reasoned about, not to their kind.
- A stop moved to a different day carries a clock time that was chosen against
  a different day's shape. Relocation must invalidate the time, otherwise the
  stale value silently competes with whatever the new day already does at that
  hour.
- Constants borrowed from one mode of travel leak into others. A two-hour
  pre-departure buffer is an airport rule; applied to a drive it generated
  confident, wrong warnings. Make the threshold a function of the thing being
  boarded.
- Unit tests passing is not evidence the itinerary looks sane. Both defects in
  this layer were found by a throwaway probe that printed every day's stops,
  and neither was covered by an assertion until after it was seen.

## 2026-08-07 - A Rebalancer That Deletes Is Not A Rebalancer

Automatic day-rebalancing removed a stop the traveller had explicitly chosen when
a day went over its cap, and said so only in a passing alert. A crowded day is a
smaller problem than a choice that silently disappears. Displacement must be
relocation: ask the placement guard for another legal day, and if none exists,
leave the stop where it is and say that plainly. Capacity heuristics may reorder
user intent; they may not discard it.

A regression test that passes against the pre-fix code is not a regression test.
The first version of the relocation test drove the change through the normal
selection path, where the day never actually reached its cap, so it passed on the
old code and proved nothing. Verify every new regression test by stashing the fix
and watching it fail for the reason you expect, then restoring.

A status line that replaces its label loses the record of what was done. During a
multi-minute build, swapping "Searching hotels" for "Working out routes" leaves
the user with a single word and no sense of progress. Accumulating the stages that
genuinely ran is more informative than inventing a plausible-sounding sequence,
and unlike a scripted narrative it cannot lie about what the model is doing.

A notice that expires on a timer is a notice the user may never read. Outcomes now
persist until something newer replaces them or the user dismisses them, and carry a
headline plus a detail line so a consequence can be explained without truncating
the outcome.
## 2026-08-07 - Bootstrap From Current Shared Contracts

- Package-manager names are not stable contracts. PowerShell moved from a removed
  Homebrew cask and archived tap to a Core formula, while Docker's cask token was
  renamed; machine setup must encode current package type and migrate sources that
  can shadow the replacement.
- A fresh worker branch may predate the machine-setup fix needed to install it.
  Bootstrap shared dependencies from the current primary lockfile, then install
  the worker's own editable source, so stale lane metadata cannot block setup.
- Treat built-in editor extensions as installed. VS Code can omit them from
  `--list-extensions`; attempting to install an obsolete companion extension can
  instead trigger a downgrade conflict with the built-in version.

## 2026-08-07 - Keep Repository Package Sources Public

- Repository defaults, container builds, and committed lockfiles must resolve
  through public ecosystem registries rather than organization-specific mirrors.
- A corporate network workaround is machine-local configuration, not a portable
  project default. Preserve standard overrides such as `PIP_INDEX_URL` for
  constrained environments without encoding their private infrastructure.
- Audit resolved lockfile URLs as well as installer flags. Package managers may
  retain an old tarball host even when regeneration is given a different registry.

## 2026-08-07 - Compose Operational Paths With Platform APIs

- PowerShell providers may accept a Windows backslash on macOS while native tools
  receive it literally. A successful `Test-Path` therefore does not prove that
  the same string is valid for `git -C`, `code`, or another native process.
- Use `Join-Path` and `System.IO.Path` separators in shared infrastructure and
  developer scripts. Keep Windows and macOS on one implementation when that is a
  local, low-complexity change; surface the tradeoff before adding platform forks.

## 2026-08-07 - Process Exit Precedes Windows Handle Release

- Stopping a process does not guarantee Windows has released every handle by the
  time the stop command returns. A single immediate recursive delete can leave an
  empty worktree directory and falsely turn successful promotion into manual cleanup.
- Retry a destructive cleanup against observable state for a short bounded window.
  Preserve the registry entry and final operating-system error when the path truly
  remains locked, so the same cleanup operation can be retried safely.

## 2026-08-08 - A Marketing Page Cannot Be More Capable Than Its Engine

- The Lab 22 entry page was hand-written and quietly promised a whole-trip total,
  beaten prices, and priced rail on every hop. None of those exist. Generating the
  page from a captured real run removed the claims automatically, because a number
  the engine never produced has nowhere to come from.
- Capture the run, then derive the page. A capture also becomes a regression test
  for the engine's own honesty: three defects surfaced only when a real run was
  rendered, including a receipt that named Amadeus for a search it answered from
  Google Places metadata.
- Prefer the tool's own words on a public surface. When the agent wrote "no live
  room rate available for these dates", the page's job was to show it, not to
  paraphrase it into a number.

## 2026-08-08 - A Fuzzy Geocoder's Top Hit Is Not Evidence

- Document readiness demanded passports for the whole family on a Bengaluru-to-Goa
  trip. The gate was right and the data was wrong: `resolve_country` took the
  geocoder's first row, and Open-Meteo answers "Goa" with Genoa in Italy and
  "Bangalore" with a village in Sindh. The places the traveller meant are absent
  from the results entirely, so no ranking could have recovered them.
- A search endpoint that matches loosely returns near-misses, not alternatives.
  Require the returned name to equal the query before treating the row as an
  answer, and rank what survives by significance rather than by the order the
  service happened to return.
- When the correct answer can be missing from the source, the only honest
  outcomes are a confident match or "unknown". Resolving to unknown was already
  safe here because the caller stays silent without both countries; the defect
  was that the resolver had no way to express doubt.
- Tightening a resolver silences its callers, so check what else depended on the
  loose answer. A bare "Bangalore" no longer resolves, which would have muted
  genuinely international trips, so the origin falls back to the home country the
  user declared - better evidence than a guess either way.
- The stubbed unit tests passed throughout, because they returned one row with a
  country and no name. A fixture simpler than the real payload cannot fail the
  way production does; the bug was only visible against the live service.

## 2026-08-09 - Workflow State Is Repository Data, Not Machine Data

- UX Lab choices, handoff notes, implementation evidence, and lifecycle states
  were written only under the operating system's local data directory. A new
  machine therefore fell back to stale committed defaults and silently presented
  completed Labs as in progress, while the exact history remained on the old host.
- Keep workflow history in one tracked canonical record. A machine-local file may
  remain as a draft cache or migration source, but reads must union its immutable
  histories into the canonical record and prefer newer top-level state without
  dropping older notes.
- A fallback default is not synchronization. Make every UI and script writer touch
  the tracked record so an unsaved lifecycle change is visible in `git status` and
  travels through the same commit, review, and merge path as the implementation.

## 2026-08-09 - A Hard Gate Must Fail Closed

- PowerShell directory-link types are platform-specific: use a junction on
  Windows and a symbolic link on macOS/Linux. Suppressing a failed Windows-only
  junction on macOS made frontend validation disappear while the merged tree was
  still published.
- A validation step described as a hard gate must add a blocking failure when its
  installed dependencies cannot be reused. A warning plus success is an implicit
  bypass and gives stronger assurance than the run actually earned.

## 2026-08-10 - A Fallback That Returns Early Is Not A Fallback

- `search_flights_duffel` called the registry provider and then returned
  unconditionally, including on an empty result. The documented Duffel fallback
  below it was unreachable for every environment with a provider key set, so a
  provider with no coverage silently degraded to no flight prices at all. A
  chain step must return only on success; empty and error must fall through.
- Two vocabularies for the same fact will disagree. The provider runtime emitted
  `live_search`/`cached_live` while the receipt layer matched the literal string
  `"quote_status": "live"`, so genuinely live stay searches were recorded as
  unpriced evidence. Freshness states belong in one enum that every layer imports.
- Configuration that nothing reads is worse than no configuration. Six
  `*_CACHE_TTL_SEC` settings existed while the caches used hardcoded literals,
  advertising control that did not exist. Either wire a knob to its behavior or
  delete it.
- Money needs a unit before it needs a comparison. Ranking subtracted raw amounts
  from different currencies, so a fare in a weaker unit always looked worse. When
  a rate is unavailable, drop the money term instead of mixing units — a slower
  ranking is recoverable, a confidently wrong price is not.

## 2026-08-10 - Verify The Vendor Before Keeping The Adapter

- `providers/liteapi.py` carried `search_rails`, `search_coaches` and
  `search_ferries` posting to `trains/search`, `coaches/search` and
  `ferries/search`. LiteAPI's own endpoint index documents hotels and flights
  only; those three endpoints do not exist. Because provider adapters degrade to
  an empty list, the code would have failed silently forever. Removed. The same
  check confirmed the flight adapter is correct — `/flights/rates` is real and
  legs-based, exactly as implemented — so verification cuts both ways.
- An empty provider registry deserves a comment saying it is deliberate. Three
  empty dicts looked like an oversight and invited someone to "fix" them by
  wiring an unverified adapter.
- A total the model writes is not evidence. `total_cost` had no provider, no
  checked-at and no expiry, so a stale or invented figure was indistinguishable
  from a live quote. The ledger in `decisions/trip_cost.py` derives what is
  actually backed by a recorded check and names the rest as stale, unverified or
  unpriced.
- Respect an invariant before adding a feature that breaks it. Driving needed a
  cost, but the decision model states there is deliberately no estimated price
  tier. Modelled fuel therefore became `RunningCost` — a separate field that
  never enters `Price`, never joins a fare total and takes no part in ranking.

## 2026-08-10 - A Regional Fixture Is One Versioned Unit

- Replacing place names and currency strings inside one captured run creates a
  plausible-looking mixture whose route, hotels, decisions, and receipts no
  longer describe the same trip. Regional examples must be standalone artifacts.
- Validate relationships, not a blacklist: declared cities own route endpoints
  and hotels, hotel markers own day references, decisions belong to trip
  comparisons, money uses one currency, and entities declared by another market
  cannot appear in the rendered payload.
- Availability and freshness are separate concerns. Render the bundled artifact
  synchronously, fetch a complete active version opportunistically, and publish
  refreshes by writing every immutable document before replacing one manifest.

## 2026-08-11 - Authenticate the Registry Before Paying the Build Cost

- A cached Docker credential can exist after its token expires, so treating the
  credential store as proof of authentication defers a predictable failure until
  after an expensive image build.
- Release automation should establish a fresh registry session before building.
  Automatic credential fallback is valid only when both identity and required
  package scope are verified; otherwise fail with the exact refresh command.

## 2026-08-13 - A Matcher That Cannot Match Turns Its Invariants Off

- The trip envelope recognised its arrival and departure legs by looking for the
  plan's `destination` string inside a leg name. A regional trip names its real
  cities, so "Flight Bengaluru to Jaipur" never contains "Rajasthan" and the
  envelope came back empty. Nothing failed: leg ordering silently stopped
  running and the return-coverage invariant silently stopped firing, so a flight
  home landed mid-afternoon between two attractions and a missing return leg was
  never reported.
- Anchor on the fact that is always present. The traveller's home city appears on
  both bounding legs by definition, while the destination is a label that may
  describe a region, a country, or nothing the legs ever say.
- An invariant that returns early on unparseable input is indistinguishable from
  an invariant that passed. When a guard depends on a match, test the case where
  the match cannot succeed, or the guard will report health it never checked.

## 2026-08-13 - Validate Where the Write Happens, Not Where It Is Convenient

- The deterministic invariants existed and were correct, but `validate_plan` was
  reachable from exactly one mutation (`add_selection`). The tool that writes
  flights and whole itineraries never called it, so the guard that would have
  caught a stop stranded after the flight home simply never ran on the path that
  produced the defect. A rule enforced on one of five write paths is a rule the
  product does not have.
- Repair and detection belong together and belong at the persistence boundary.
  Ordering ran only as a side effect of a hotel change, which meant adding a
  flight reordered nothing. Anchoring both to the write makes the guarantee
  independent of which field the edit happened to touch.
- Stage a new invariant before it can block. Continuity (I9) reports on the edit
  that introduces it but does not gate completion, because a new rule meets its
  real false-positive rate on existing data, not in tests.
## 2026-08-13 - Remote-Call Cost Belongs to a Runtime, Not to Call Sites

- `httpx.get`/`httpx.post` build a throwaway client per call, so every provider
  request re-loaded the CA bundle and re-handshook TLS. The same defect existed
  one level up: a model client built per graph round re-handshook Azure OpenAI
  before every tool phase. Connection reuse is a property of the process, not of
  whichever call site was written last.
- A per-call `timeout=20` is not a budget, it is a tail. One sick dependency
  then costs twenty seconds on every attempt, repeatedly, for the whole turn.
  Latency budgets belong to the endpoint so they can be reasoned about together.
- Without a circuit breaker, a failing dependency keeps charging full timeout to
  every caller. Deriving the endpoint from the request URL means a newly added
  provider inherits pooling, budget, breaker, and telemetry with no registration,
  which is what keeps the pattern true as providers are added.
- Make the fail-fast error a subclass of the transport error the call sites
  already catch. An open circuit then degrades through the existing fallback
  path instead of needing a new branch at every provider.
- Composite responses assembled from unrelated sources cost their sum only
  because nobody made them concurrent. Fan them out; keep ordered fallback
  within a single capability sequential, because there the order is the policy.

## 2026-08-13 - An Owner Launcher Must Not Depend on the Inherited PATH

- A GUI-launched `.command` runs with a minimal PATH, and any process started
  from inside a running `brew` command inherits Homebrew's sanitized PATH, which
  substitutes the shim directory for the Homebrew bin directory. `pwsh` was
  installed and runnable in both cases; only the bare-name lookup failed.
- `brew shellenv` is a no-op inside a brew command context, so a `.zprofile` that
  relies on it cannot repair such a shell. Even a login shell stays broken, while
  a pristine `env -i` login shell works, which makes the fault look intermittent.
- Diagnose the launching process, not the shell: `ps eww -p <pid>` shows the PATH
  a GUI application actually holds and hands to every terminal it spawns.
- Owner-facing launchers resolve the interpreter explicitly through one shared
  helper and fail with the install command. Bare-name lookup is a convenience for
  interactive shells, not a contract a one-click entry point may rely on.

## 2026-08-13 - A Rewrite Must Carry the Recovery It Replaces

- Consolidating the sync launchers into `sync-latest-from-remote-master.ps1` kept
  the happy path and silently dropped the conflict-recovery retry that
  "Recovery Belongs in the Flow That Broke" had already established. A rewrite
  that reproduces the primary flow is not equivalent until it also reproduces the
  failure handling; port the recovery step in the same change or the lesson is
  re-learned from the owner's next stalled sync.
- Three scripts each carried their own registry lookup, so only `sandbox.ps1`
  understood a bare sandbox number while the resolver silently accepted fewer
  forms. Duplicated lookup logic does not stay equivalent; the shared
  `lib/sandbox-registry.ps1` resolver is what makes "1", "1-stay-comparison", and
  "stay-comparison" mean the same thing from every entry point.
- An unmerged path with no conflict markers reads as resolved to both the editor
  and the eye, because the merge state lives in the index rather than the file.
  `fx.py` had been rewritten with `_SOURCE` referenced but never defined, so the
  merge looked finished while every real conversion would raise `NameError`.
  Judge a conflict by `git diff --diff-filter=U`, then run the code, not by
  whether the file still shows markers.
- A test that seeds a cache with a hardcoded timestamp expires. Once the fixed
  date aged past the FX rate TTL, the assertion started reaching the live rate
  service and failing on a real published rate. Seed freshness relative to now
  and keep the fixed value only where the assertion depends on it.

## 2026-08-13 - A Surface That Cannot Render a Stop Must Not Drop It Silently

- The itinerary renders every stop verbatim, while the map renders only stops it
  can resolve to a pin. Anything it cannot resolve is skipped with no marker and
  no message, so the two surfaces disagree and only the map looks "wrong".
- `_transport_terminal_refs` understood a flight only as `Flight: A to B`. When
  the agent wrote one stop per terminal ("Kempegowda International Airport,
  Bangalore (BLR)", kind `flight`), endpoint parsing failed, and the caller's
  `if kind in {"flight", "transport"}: continue` discarded the stop. The same
  name with kind `airport` produced a pin, so a tag the user never sees decided
  whether their flights appeared. Parse the route form, then fall back to the
  stop as its own named terminal.
- The guard that rejects a geocode whose provider name does not match the stop
  name prevents wrong pins, but it also drops real ones: "Seine River Cruise"
  resolves to "Bateaux Parisiens" with correct coordinates and shares no token
  with the stop, so it vanished from the map while staying in the itinerary.
- Audit cross-surface consistency by diffing the surfaces themselves, not by
  reading the builder. Comparing `/trip/itinerary` stop names against
  `/trip/map` pin names found seven missing stops in seconds, including one this
  investigation was not looking for.
- A journey the plan never spells out is still a journey. Recognizing legs only
  by their written form (`kind: "flight"`, or a name with a drive/train/bus
  word) made a Paris replan read as a local day: the two airports it listed were
  dropped from the map route and the day was bookended by the destination stay,
  so the trip asked the traveller to drive between Bengaluru and Paris. Derive
  the leg from what the stops imply — two terminals in different cities are an
  inter-city hop — and keep that rule shared between the itinerary and the map
  so the two surfaces cannot disagree about whether a day is a transfer day.

## 2026-08-13 - Audit The Guards Against Real Trips, Not Against The Code

- Running every invariant over the owner's seven real stored trips found in one
  pass what three separate bug reports had been finding one at a time. Two
  classes of gap showed up, and neither was visible by reading the guard.
- **A guard that fires with the wrong words is a gap.** A Paris stay listed
  after landing back home was reported by I4 as "cannot reach Hotel Chambiges
  Elysees in time; short by 11294 minutes" — arithmetic that treats a
  wrong-continent stop as a scheduling problem. Nothing said the traveller was
  not in Paris. Continuity (I9) only compared the last stop of one day with the
  first of the next, and switched itself off whenever either day held any leg at
  all, so the intra-day case it was written for could not reach it. A trip is
  one body moving through one sequence of places; the rule is the same inside a
  day and across midnight.
- **A guard disabled by missing input is worse than a missing guard**, because
  the plan reports clean. Two trips had no `origin`, which silently turned off
  the envelope, presence, stay-coverage and return invariants, and made the
  round-trip transport check return an empty list rather than a complaint. Every
  early return on absent input should be a report, not a pass (I10).
- Audit with the owner's own data. The emulator's `places_cache` container has
  real coordinates, so `validate_plan` runs at full strength offline. Seven real
  trips produced exactly one new violation and zero false positives, which is
  the evidence that let continuity join the completion gate the same day.

- A fact stored in one shape and checked in another is not a check at all. The
  places cache wrote `weekday_descriptions`; the guard's opening-hours invariant
  read an `opening_hours` string nothing produced, so I3 could never fire and a
  museum closed on Tuesdays was scheduled on a Tuesday while the view layer
  quietly printed "Likely closed" next to it. Renaming the key would have fixed
  that one trip. What actually closes the class is a single fact boundary --
  `place_facts` -- that every consumer reads, a contract test asserting the cache
  still emits the keys that boundary needs, and a rule that a fact good enough to
  show the traveller is good enough to hold the turn open. Display-only knowledge
  is knowledge the planner has decided not to act on.

- Tri-state is the whole design, not a nicety. `closed_on` had to distinguish
  "the schedule says closed", "the schedule says open", and "we never fetched a
  schedule", because an invariant that treats unknown as false blocks real plans
  and one that treats unknown as true is decorative. Keeping unknown separate is
  what made it safe to promote the fact-based invariants into the completion gate
  alongside the envelope rules, while travel feasibility -- which degrades on
  guessed coordinates -- stayed out.

- An integration test that reads a developer's home directory is a bug factory.
  `test_trip_guard_integration` scored placement against whatever coordinates and
  opening hours this machine had cached from real use, so the same commit passed
  here and would have failed elsewhere, and a genuine improvement to the guard
  looked like a regression. Isolating the suite from `places_cache` made the
  failure legible in one run.

- An absolute ordering is not a strong preference, it is a blank cheque. Ranking
  contradictions lexicographically ahead of cost meant no arrangement that
  cleared one could ever lose, so the first real run moved the Louvre onto the
  departure day and a Paris district onto the Versailles excursion -- the theme
  penalty fired on both and was simply outranked. A cleared fault is now worth a
  large finite number of minutes: heavy enough to beat any ordinary saving,
  finite enough that it cannot buy an arrangement which ruins the rest of the
  trip. Reserve lexicographic ordering for things that are genuinely
  incomparable, and price everything else.

- A rebalancer needs exchanges, not just relocations. Lifting one stop off a day
  and adding it to another always leaves one day heavy and one light, and that
  imbalance costs more than the travel it saves, so a search over relocations
  alone found zero improving moves on a deliberately scrambled trip and was
  right every time. Trading two stops keeps both days the size they were. If an
  optimiser reports nothing to do on an obviously bad input, suspect the
  neighbourhood before the objective.

- Rearranging a plan without rewriting what it calls itself leaves the plan
  lying. "Day 3 - Louvre & Marais" holding neither is worse than the crooked
  schedule that was just fixed, because the traveller now cannot trust the
  labels either. Any operation that moves things has to own the words that
  describe them.

- Do not point a new mutation at real data on its first run. The repair pass was
  wired to a button and tried against a live trip the same hour it was written;
  it degraded the trip and there was no undo. A corpus harness would have shown
  all three defects without touching anything a person cared about.
## 2026-08-14 - Missing Data Can Be An Answer, And Slack Is Not Symmetric

- The audit reported seven trips with no `origin` as a defect. It was not one.
  A traveller may want a destination-only itinerary and arrange their own way
  there, so the absence was sometimes a genuine choice and sometimes a question
  nobody had asked. Backfilling the field would have invented a home city the
  user never gave. The fix is to let the trip record the answer
  (`travel_scope: destination_only`) and to make the guard ask rather than
  accuse. Before adding data to satisfy a rule, check whether the rule should
  have asked a question instead.
- A tolerance has to be asymmetric around what the traveller cannot undo. The
  feasibility rule fired 21 times for arriving nine minutes after a restaurant,
  which no one would call a defect, while the same nine minutes against a
  ticketed entry or a departure is a missed trip. Slack now depends on who owns
  the clock: a stop with a booking or a timed entry gets none, an ordinary sight
  gets ten minutes. Occurrences fell from 90 to 82 and the only surviving
  feasibility finding is a real one, thirty-eight minutes short.
- Both changes came out of reading a grouped report rather than a single trip.
  One count of 21 identical findings is the signal that a rule is miscalibrated;
  the same 21 spread across weeks of manual testing read as noise.

## 2026-08-15 - A Test Suite That Six Lanes Share Is Not Isolated

- Seven test files pinned their fixture directory to a fixed name under the home
  directory (`~/.tripplanner_test`, `~/.tripplanner_chat_test`, ...) and deleted
  it in teardown. One suite at a time, that is fine. Six sandboxes running their
  suites at once means one run's teardown removes another run's fixture between
  two assertions, and the failure lands wherever the timing put it -- 15 failures
  in one run, 4 and 7 in the next, none of them reproducible alone.
- The tell was that the same test passed in isolation, three times in a row,
  after "failing" in a full run. A failure that will not reproduce alone is a
  statement about the environment, not about the test.
- The fix is one line per file: put the process id in the directory name. Proven
  by running two suites concurrently before the change (4 and 7 failures) and
  after it (both clean). `test_observability.py` already had the better pattern
  -- patch `Path.home` to a tmp_path -- and was the only one unaffected.
- Beware the automatic import fix. Running `ruff --fix` for the import sort my
  edit disturbed silently split one aliased import into five and added three
  E402s elsewhere in the file. Compare the lint profile by rule count before and
  after, not the raw line list, because inserting three lines renumbers every
  finding below it and hides a real regression among the noise.

## 2026-08-15 - The Day That Never Came Home

- The audit reported a Nashik excursion drawing an "inter-city Drive that covers
  no distance". Chasing it found a larger defect standing next to it: the day
  left the hotel, drove to Igatpuri, visited three places, and simply stopped
  there. The plan clearly returned -- it held a return drive and the stay twice
  -- but the map left the traveller at a temple.
- The cause was in the reorder that anchors a transfer day on its stay. It moved
  the stay to the front and filtered every other occurrence out, which is right
  for a day that ends in a new city and wrong for an excursion that comes home.
  The walk had already produced the correct path; the reorder deleted its ending.
- The finding that led here was not itself the bug, and calibrating it away
  would have buried the real one. A rule earns its place by what it makes you
  look at, not only by what it names. The rule was then narrowed to flights and
  trains, where a zero-distance journey is unambiguous, because a waypoint hop
  inside a drive is genuinely part of that drive.

## 2026-08-15 -- The safety limit that fired exactly where the safety net was

- Two of the twenty-four corpus requests spent real money and saved a trip with
  destination, dates, and travellers set but no days at all. The most expensive
  request of the whole run, at INR 47, was one of them and produced nothing.
- `graph_policy` already anticipated this: when the tool-phase budget runs out it
  lets the still-owed first `update_trip_plan` through before honoring the cap.
  That escape never got to run. LangGraph counts every node, and the flat
  `_CHAT_GRAPH_RECURSION_LIMIT = 24` equalled the worst-case walk to that point
  -- ten tool phases at two nodes each, plus the two forced saves. The graceful
  gate sat one step beyond the hard one, so the hard one always won.
- A backstop must be derived from the budget it is backing, not chosen next to
  it. The limit is now computed from `MAX_TOOL_PHASES_PER_TURN` and
  `MAX_INITIAL_ITINERARY_UPDATES`, so raising either cannot silently re-create
  the trap, and a test asserts the ordering rather than the number.
- The same turn on `/chat/stream` degraded politely while `/chat` raised a 500:
  only the streaming path passed the limit and caught `GraphRecursionError`. The
  SPA uses the streaming path, so the broken one stayed invisible until a script
  drove it. When two entry points reach the same graph, the protections belong
  to the graph call, not to whichever caller someone remembered.
- It took a paid corpus to surface this. No test failed, no user complained, and
  the failure was a trip that merely looked unfinished.

## 2026-08-18 - A Recoverable Stash Can Still Break A Live Agent

- Full synchronization temporarily stashed every dirty worktree, updated its
  branch, then restored the files. Git preserved the bytes, but an active agent
  saw its edits disappear in the middle of its reasoning and could continue
  against a source tree that was temporarily not its own.
- A live worktree is an interface, not just storage. Fetch remote refs freely,
  but preflight committed conflicts and incoming-path overlap before changing a
  dirty tree. Merge around non-overlapping work in place; on overlap, leave the
  files visible and name the paths.
- Publication and freshness are different outcomes. A dirty lane may safely
  ingest and push the current base while its own commits wait for a coherent
  boundary. Reporting that deferral is more honest than hiding WIP to satisfy a
  stronger convergence claim.
- Do not rewrite a generic lower-level error into a specific diagnosis without
  checking which worktree is dirty. The old wrapper blamed concurrent sandbox
  writes when the merge gate was actually rejecting primary-checkout WIP, and
  the empty path list was the clue that the diagnosis came from the wrong lane.

## 2026-08-18 - Reusable Worktrees Need An Explicit Freshness Boundary

- Fetching remote refs does not update a worker's base. The controller fetched
  before dispatch but still checked out its persisted integration SHA, so later
  sandbox promotions on `master` remained absent until batch finalization.
- A reusable idle slot does not need to display current `master`; changing it
  continuously can disturb a live agent. Refresh the integration lane on each
  idle controller cycle, then snapshot that validated baseline for every worker
  in the next batch. Leave slot files alone until assignment, when their fresh
  branch is created from that baseline.
- A second reconciliation before opening the pull request remains necessary.
  Master can advance while workers run, and a batch is not valid merely because
  it started from a current base.

## 2026-08-25 - Retry Isolation Must Include Persisted State

- Corpus retries changed request IDs but kept the same synthetic user. The API
  therefore began each nominally fresh attempt with that user's interrupted chat
  and empty active trip, so a failed paid turn could poison every later run of the
  same scenario even though idempotent request replay was no longer involved.
- The durable dedupe identity is the scenario slug in the manifest, not the API
  principal. Give each logical generation attempt a fresh principal and keep the
  same principal and request ID only for transport retries within that attempt.
  This also makes usage deltas exact without depending on historical ledgers.
- Concurrency is not free capacity. Two long planning turns share the same model
  quota and made throttling and barren output correlated, so paid generation now
  defaults to serial execution while retaining explicit bounded concurrency for
  deployments whose capacity has been verified independently.
- A failed response is not proof that generation failed. The server may have
  persisted a complete trip before the connection dropped; inspect that isolated
  principal before discarding the attempt. Conversely, do not repeat a full
  15-minute request timeout four times: shorter connection failures remain
  idempotently retryable, but the full timeout is the retry budget.

## 2026-08-25 - Paid Corpus Success Must Mean Rich Persisted Data

- A healthy HTTP response is not a successful corpus attempt. The planner can
  spend several minutes, reject both structured itinerary saves, narrate a useful
  plan in chat, and still leave a zero-day draft that produces no corpus file.
- After a completed empty turn, use one distinct-idempotency recovery request on
  the same isolated principal so it can repair the existing draft from gathered
  research. Never issue that extra paid turn after a timeout or transport failure.
- Measure acceptance against the corpus being built. The existing generated set
  had at least 2.7 stops per itinerary day, so new records require at least two;
  a merely non-empty day shell is not rich evidence. Report accepted yield and
  average stops/time, and stop with a failing exit after three consecutive
  completed turns save no acceptable itinerary rather than spending for an hour.

## 2026-08-25 - Audit Evidence Must Outrank Mutable Local State

- A deep link carrying both a saved trip ID and an immutable corpus record opened
  the saved copy first. Any stale or blank local document could therefore win even
  though the exact artifact that produced the finding remained healthy.
- When durable evidence and mutable convenience state are both available, restore
  the evidence first and use mutable state only as fallback. Canonicalize the URL
  only after that restore succeeds.
- Screenshots are useful only when they identify the finding point. Capture the
  explicit affected day, derive named days from deterministic finding text when
  necessary, and fall back to the itinerary pane only when no precise day exists.

## 2026-08-25 - A Model Client Without An Explicit Timeout Hides As Slowness

- A corpus turn wedged inside one Azure OpenAI call for sixteen minutes and
  emitted no log line, no error, and no usage record. The only visible symptom
  was the client-side `TimeoutError` a corpus run reports after its own long
  request timeout, which reads as "the planner is slow" rather than "one call
  never returned".
- The OpenAI SDK defaults to a 600s read timeout and applies the configured
  retry count on top of it, so a single stalled turn can hold a run for the
  better part of an hour while the process still answers `/health`.
- Set an explicit `timeout` on the model client sized against observed healthy
  latency, not against the worst case you can imagine. Healthy planning calls
  here finish under 40s, so 90s with three retries turns an invisible hour-long
  stall into a retryable error within minutes.
- When a long-running job reports only a client-side timeout, check the server
  log's last timestamp against wall clock before blaming throughput. A gap with
  no terminal event means a hung call, not slow work.
## 2026-08-25 - Unversioned Project Provisioning Drifts Where Deploys Cannot

- Prod alone failed every Google Places call while canary, which tracks prod
  closely in code, was healthy. The cause was not a deployment: the prod project
  had been created through the Maps Platform console wizard, which enables the
  legacy API bundle, and so never had `places.googleapis.com` enabled at all.
- Deployment gates cover code and infrastructure templates, not the cloud
  project a key belongs to. Anything provisioned by hand or by a vendor wizard
  sits outside every check and drifts silently until one environment alone
  misbehaves.
- When a single environment fails an external API, compare enabled services
  across projects before reading application code. A missing API presents as an
  authorization error, not as a configuration error.
- Cloud billing budgets only notify; they never stop spend, and their cost data
  lags by hours. Per-API quotas are the only real-time ceiling. Treat an
  automatic billing shutoff as a backstop for a slow leak, not as protection
  against a runaway loop.
- In Places API (New) the billed SKU is chosen by the request field mask, not by
  the endpoint. Asking for `rating`, `reviews`, or `editorialSummary` silently
  promotes a free ID lookup into the most expensive tier available.

## 2026-08-27 - A No-Op Persistence Path Must Not Write

- The trip archive correctly ignored `updated_at` when deciding whether a save
  was a new revision, then rewrote the existing revision and `last_seen_at`
  anyway. Opening an unchanged trip therefore dirtied the primary checkout and
  blocked sandbox promotion even though the archive's meaningful hash matched.
- Once durable content is known to be unchanged, return before collecting
  volatile metadata or serializing. Test the file bytes, not only the revision
  count; a structurally valid no-op rewrite is still an operational change.

## 2026-08-28 - A Paid Provider Key Is Not an Enable Switch

- Copying a development `.env` into isolated workers gave every lane the same
  billable key. Separate caches then turned one corpus run into repeated provider
  purchases even though the owner never used the primary local UI.
- Paid providers must require an explicit, fail-closed runtime switch in addition
  to credentials. Secrets prove authorization; they do not express owner consent
  to spend.
- Keep a second guard at the provider project: disable the service or enforce a
  tight quota outside approved environments. An application bug must not be able
  to bypass the owner's environment policy.
- Usage telemetry needs environment, lane, run, caller, field-mask class, and
  cache-hit dimensions. Provider request totals can prove when and under which
  key a leak occurred, but cannot reconstruct the responsible process afterward.

## 2026-08-28 - Never Arm a Budget Backstop Below Accrued Spend

- Cloud Billing evaluates an updated budget against already reported
  month-to-date cost. Lowering a threshold below that cost can publish an
  immediate breach event; repairing a broken consumer at the same time can turn
  a configuration apply into an account-wide outage.
- Provision the event path separately from arming it. Use an explicit arming
  switch, refuse deployment while disarmed, and check current reported spend
  before granting invocation.
- Removing an invoker binding is not guaranteed to cancel an event already
  accepted or in flight. Delete the trigger or function when immediate
  containment must be definitive, then restore billing links.
- Hard per-API daily and minute quotas are the safe real-time cost ceiling.
  Delayed account-wide billing detachment is only a secondary-period backstop.

## 2026-08-28 - Dry-Run Safety and Recovery Must Cover Every Lane Type

- Declaring `SupportsShouldProcess` on a wrapper does not make raw `git` calls
  honor `-WhatIf`. Every mutating helper must check `ShouldProcess` before it
  creates a worktree, merges, commits, or pushes.
- A synchronization flow that discovers several lane kinds must route every one
  through the same recovery contract. Handling only registered sandboxes left
  multiagent and standalone branches unable to replay known `rerere` decisions.
- Detect both unmerged index entries and `MERGE_HEAD`. With `rerere.autoupdate`,
  files can already be staged while the merge still needs its commit, so checking
  only `git diff --diff-filter=U` can skip the finalization step.
- After any preview-path defect, inspect and restore the exact worktree the
  preview touched before continuing; a dry run must leave byte and Git state
  unchanged.

## 2026-08-28 - Runtime Configuration Needs A Checked-In Owner

- A comprehensive `.env.example` is still only a catalog. When each real
  environment uses an ignored file, new non-secret controls can ship without
  appearing in any file the owner actually reviews or deploys.
- Keep complete non-secret profiles checked in with identical key sets, and use
  ignored environment files only as secret overlays. Tests should reject profile
  drift and known secrets in tracked profiles.
- Preserve one explicit precedence order: command/process override, then secret
  overlay, then checked-in profile, then code default. A setting with multiple
  hardcoded environment values has no clear owner even when all values agree.
## 2026-08-28 - PowerShell Script Success Must Reset Native Exit State

- Calling one PowerShell script from another does not clear `$LASTEXITCODE`.
  A resolver successfully committed a merge, then used a failing
  `git rev-parse MERGE_HEAD` probe to prove the merge was finished. Its caller
  received that probe's exit code `1` and reported the successful recovery as a
  failure.
- A script consumed by other scripts must establish an explicit success exit
  code after expected failing probes. Test the caller contract, not only the
  resulting files: both the Git state and the process result must say success.

## 2026-08-28 - Verify Cosmos Numbers by Value, Not Representation

- Cosmos and its emulator can deserialize the same JSON number into slightly
  different binary floats. A longitude written as `12.471670699999999` was read
  back as `12.4716707`, so exact document equality rejected a successful write.
- Verification should compare nested numeric values with a small absolute and
  relative tolerance while keeping booleans, object keys, list order, and all
  nonnumeric values exact. Pair the accepted round-trip case with a test that
  rejects a meaningful coordinate change so tolerance cannot hide corruption.

## 2026-08-28 - Provider Credentials Must Not Activate Sandbox Enrichment

- Copying a primary environment file into every sandbox changed a read-only,
  stored-data audit workflow into a spend-capable environment. The audit itself
  made no provider calls, but live view rendering in those lanes automatically
  warmed every place through isolated caches.
- Treat credential distribution, runtime enablement, and cloud Service Usage as
  independent gates. Sandboxes and evaluation jobs should remain disabled by
  default even when a key is present, and an emergency stop must close the cloud
  gate so already-running processes cannot bypass repository configuration.
- Request budgets must cover synchronous rendering and background warming as one
  scope. Concurrency reduces latency but does not reduce billable fan-out; without
  a shared budget it can multiply cold requests across both items and lanes.
- Diagnose billing incidents from provider request metrics before interpreting a
  changing console total. Delayed usage and credit allocation can revise cost
  after traffic stops; response-code and method dimensions distinguish retry
  storms from successful high-cardinality fan-out.

## 2026-08-28 - Offline Claims Need a Default-Deny Execution Boundary

- A full stored-corpus audit issued 14,847 successful Places Text Search calls
  over roughly four hours and generated no corpus trips. Its render fixture
  replaced details, photos, discovery, and the browser key but omitted coordinate
  lookup; each cache miss therefore escaped to live Places while hundreds of
  persisted records were inspected.
- The provider budget treated a missing scope as unlimited permission, and
  reusable view builders created their own scopes. Mocks could hide common paths
  but could neither express nor enforce permission to spend.
- Authorization belongs at execution entry points, not inside reusable domain
  functions. Admit only named user-interaction and budgeted-corpus scopes, deny
  absence, propagate one shared ceiling through workers, and check known billable
  hosts again immediately before network access.
- Attribution explains spend after it happens; it is not authorization. Keep
  cloud quotas as the independent last line of defense if application policy is
  bypassed.

## 2026-08-28 - Paid Response Caching Belongs Below Every Caller

- Graph-level tool caching did not cover direct domain calls such as route
  metrics, Static Maps exports, or one tool invoking another Places tool.
- Cache successful paid responses at the lowest shared provider boundary and
  check that cache before consuming paid-call budget. A fresh cache hit then
  consumes neither provider quota nor per-turn allowance, while transient errors
  remain uncached.

## 2026-08-31 - Fresh Cache Entries Can Still Have a Stale Schema

- Production destination metadata survived a deployment and remained fresh by
  TTL, but older entries lacked the durable `photo_refs` field. Attractions and
  ratings rendered from cache while every photo silently disappeared, making the
  hosted smoke look like an upstream Places outage.
- Treat an absent derived-source field differently from a present empty field.
  Absence requires one metadata refresh to migrate the entry; an empty list is a
  valid provider result and must not trigger repeated paid requests.
- A smoke failure should expose the earliest missing layer. Provider-call and
  cache-result logs distinguished "no photo request was attempted" from quota,
  authentication, and provider-data failures without weakening the smoke gate.

## 2026-08-31 - Thread Fan-Out Must Preserve Request Context

- The destination overview established a paid-provider budget in FastAPI, then
  moved its Places branch through the shared thread pool. Python `contextvars`
  did not cross that thread boundary, so every provider call was denied locally
  and degraded to empty output without reaching Google or emitting an HTTP error.
- Submit each branch with its own `contextvars.copy_context()`; one copied
  context cannot be entered concurrently by multiple worker threads.
- The earlier absent-versus-empty cache rule is insufficient by itself because
  legacy entries may contain `photo_refs: []`. Persist an explicit schema marker
  to distinguish unverified legacy metadata from a current confirmed-empty result.

## 2026-08-31 - Stable Cache Mode Must Exclude Transient Data

- Hosted environments set `CACHE_STABLE_FOREVER=1`, but the Places TTL helper
  applied that override to failed lookups and signed photo URLs as well as stable
  metadata. One quota-era empty Paris result therefore never reached its intended
  60-second retry window, while uncached destinations continued to work.
- Apply indefinite retention only to stable metadata. Provider misses must retain
  their short retry TTL, and signed URLs must retain an expiry-aware TTL even when
  their durable photo references are stable.
