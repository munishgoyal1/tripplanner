# 004 - Auto-validation harness

> Sections 1-5 are **agent-drafted from the owner's dictated intent** on
> 2026-08-14. Overwrite them freely; the rest was normalized against the current
> system and is the part to argue with.

## 1. Raw mind dump

> OWNER INPUT (agent draft)

Manual testing is the bottleneck. I plan the same trip again and again, eyeball
one pane, notice one or two things, tell the agent, wait for a fix, then replan
and re-eyeball. Each round costs me real attention and surfaces only a couple of
bugs. Most of what I find is mechanical — a guard that did not fire, an edge case
nobody thought about — and a machine should be finding all of that without me.

I want a wide array of local data and a way to run every rule we know against it,
plus new rules we brainstorm together. I will give ideas in plain language and
the agent turns them into checks. 100 trips is impossible to create by hand, so
the corpus has to be generated.

It is not only about bugs. With a big corpus I want to see what the planner
actually does across many trips, because that is where the ideas for smart
itinerary features that wow a customer come from — the gaps announce themselves
instead of being guessed.

## 2. User problem

The owner is the only tester, and the current loop is serialized through their
attention: plan, eyeball, report, wait, replan, re-verify. Yield is one or two
defects per cycle, biased to whichever pane they happened to look at. Defects in
panes they did not open, and defects in trip shapes they did not think to try,
are found only by accident — usually much later, by a customer-facing surface
looking wrong.

The deeper problem is that **the guards themselves are untested**. On
2026-08-13 an audit over seven stored trips found two trips whose missing
`origin` had silently switched off four invariants. Those plans reported clean
because nothing looked. No amount of manual testing finds a guard that is not
running.

## 3. Desired outcome

The owner keeps using the app normally. One command then reports every new way
the system contradicts itself across the whole local corpus, grouped and
deduplicated, with everything already discussed suppressed. Fixing a defect is
proven by the same command. The owner never replans a trip to re-check something.

Separately, the same corpus produces a description of what the planner actually
does — where days are thin, which options never win, which preferences never
change an itinerary — so feature work starts from observed gaps.

## 4. Must-have examples

1. **The reported defect is found before it is reported.** The Paris trip
   `paris_2026-09-06_2026-09-12` lists a Paris stay at 23:59 on Day 7, after
   landing back in Bengaluru. The harness reports it as a continuity violation
   without anyone opening the map.
2. **A guard that stops running is caught.** Blanking `origin` on any trip makes
   the plan report *fewer* violations than before. The harness fails on that
   alone, without a rule that mentions `origin`.
3. **Awkward edge case.** A synthetic corpus run produces a trip whose itinerary
   is empty because the agent spent its tool budget on research. Nothing in the
   plan is malformed — the harness must still report that a trip presented as
   planned holds no itinerary.

## 5. Boundaries

- Never runs against canary or production data, and never writes there.
- The customer-facing product gains nothing from this: no new UI, no new user
  endpoint, no runtime cost in the hosted app.
- Corpus generation calls the model and costs money. It must be explicitly
  invoked, budgeted, and never triggered by a build, test run, or commit hook.
- The debug store's real-trip archive and its trip numbering must not be polluted
  by synthetic data.
- The harness reports; it does not silently rewrite plans to make itself pass.

---

## Document control

| Field | Value |
|---|---|
| Brief ID | `004` |
| Status | Draft |
| Owner | Munish Goyal |
| Created | 2026-08-14 |
| Updated | 2026-08-14 |
| Baseline | `docs/REQUIREMENTS.md` @ `8cdfc23` |
| Target milestone | Phase 1-3 (offline loop) |
| Related capability IDs | Trip guard invariants I1-I10, `planning_completion_gaps`, `debug_store` |

## One-sentence requirement

As the sole tester of a preference-aware trip planner, I need every rule run
automatically over a large local corpus of real, synthetic and mutated trips, so
that defects and feature gaps surface in one batch instead of one at a time
through manual replanning.

## Why now and evidence

- **Trigger:** three separate bug reports on 2026-08-13 (`Paris replan drives
  between airports`, `Nashik itinerary not saved`, `Goa hijack`) were all the
  same class — a guard that could not see the case in front of it.
- **Evidence:** a one-off audit over the owner's seven stored trips
  reproduced the reported Paris defect *and* found two previously unknown
  classes (missing-`origin` guard disablement, unreported I4/I5 findings) in a
  single pass, with zero false positives.
- **Frequency and severity:** every planning session produces trips nobody
  re-checks. Severity is high because the defects reach the surfaces the owner
  shows people — an itinerary that asks a traveller to drive between continents.
- **Expected signal:** defects found per owner-hour rises sharply; the count of
  *new* findings per run trends to zero between deliberate rule additions;
  manual replan-to-verify cycles disappear.

## Current behavior

Verified today:

- `trip_guard.validate_plan` evaluates I1-I10 as pure arithmetic over a plan and
  degrades to silence when facts are missing.
- `trip_validation.planning_completion_gaps` bundles restaurant, empty-day,
  round-trip, hotel and coherence gaps; `_COHERENCE_CODES` currently gates on
  I1, I2, I5, I9.
- `debug_store.record_trip` captures every locally saved trip into
  `debug-store/`, one file per planning run, deduplicated by content hash,
  numbered by `archive_no`, restorable into any sandbox emulator. Currently
  holds 0 records (landed 2026-08-14).
- `scripts/dev/sandbox_seed.py` can `capture` a trip into a reusable fixture,
  `seed` a sandbox database, and `move` one between sandbox names.
- The emulator's `places_cache` container holds real coordinates (153 entries in
  sandbox 2), so the whole rule set runs offline at full strength.

Assumption, not verified: that render-level view-models (`build_itinerary`,
`build_map_view`) are stable enough to assert against across many trips. Phase 2
must confirm before its checks are allowed to gate.

## Scope and priority

### Must ship

- One corpus reader that yields `(plan, provenance)` regardless of source.
- A corpus store that is **separate from the debug store** (see D-01).
- `Build-Corpus` and `Audit-Trips` entry points with macOS and Windows launchers.
- Plan-level checks (existing invariants + completion gaps) over the whole corpus.
- Render-level checks over the built itinerary and map view-models.
- Grouped, deduplicated findings with a committed baseline; non-zero exit only
  on findings absent from the baseline.
- A deterministic mutation engine and the metamorphic assertion that a
  degrading mutation never reduces reported violations.

### Should ship

- A rules registry: one table mapping rule id to the rule stated in the owner's
  words, its severity tier, and its evaluator.
- Planner-driven synthetic generation against a dedicated sandbox, resumable and
  capped by trip count and budget, whichever is reached first.
- Corpus observation report (statistics, not violations) for feature discovery.
- A tagged reference corpus of proven real-world itineraries, and a comparison
  that reports where our generated itineraries differ structurally from
  reference itineraries carrying the same tags.

### Could ship later

- Screenshot/visual diffing of the map and itinerary panes.
- Trend tracking of finding counts across runs.
- Automatic bisection of which commit introduced a new finding.

### Out of scope

- Any customer-visible feature, endpoint, or UI.
- Running against canary or production.
- Auto-fixing plans, or mutating stored trips to satisfy a rule.
- Replacing the existing pytest suite; the harness complements it.

## User scenarios

1. **Primary path**
   - Given the owner has planned trips normally for a week
   - When they run `Audit-Trips`
   - Then they get findings grouped by rule and symptom, one exemplar and a
     count each, listing only what is new since the last accepted baseline
2. **Edge case — a guard goes dark**
   - Given a change that makes an invariant return early on absent input
   - When the mutation engine blanks that input on every corpus trip
   - Then the run fails because a degrading mutation reduced violation count,
     naming the rule that stopped firing
3. **Recovery — findings are agreed, not fixed**
   - Given the owner reviews the report and decides three findings are
     acceptable for now
   - When they accept the baseline
   - Then those findings never appear again until their shape changes, and the
     acceptance is recorded in the baseline file with a date

## Experience contract

### Entry point and workflow

- Entry: `scripts/mac/user/validation/Build-Corpus.command` and
  `Audit-Trips.command`, with `.cmd` twins under `scripts/win/user/validation/`,
  both dispatching to one PowerShell script over one Python implementation.
- Shortest normal path: `Audit-Trips` with no arguments — audits everything,
  prints new findings only.
- Reversal: `Audit-Trips --accept` rewrites the baseline; the baseline is a
  committed file, so acceptance is reviewable and revertible in git.

### Cross-surface behavior

Developer tooling with no customer surface. The harness *reads* the web
view-models to assert cross-surface agreement, but changes no surface.

| Surface | Current behavior | Required change | Must stay synchronized with |
|---|---|---|---|
| Web Itinerary | Renders `build_itinerary` | None; harness asserts against it | Web Map |
| Web Map | Renders `build_map_view` | None; harness asserts against it | Web Itinerary |
| All others | — | None | — |

### UI states

Not applicable: command-line output only. Terminal output states are
`no new findings`, `N new findings`, `corpus empty`, and `emulator unreachable`.

### Accessibility and responsive behavior

Not applicable.

## Business and data rules

- **Source of truth:** every finding is derived from a stored plan; the harness
  keeps no independent state beyond its baseline and corpus manifest.
- **Provenance is mandatory.** Each corpus record declares `real`, `revision`,
  `synthetic`, `template`, `mutated`, `golden`, or `reference`. Findings are
  reported with provenance so a synthetic artefact is never mistaken for a real
  defect, and so a reference itinerary is never reported as our bug.
- **Isolation:** the harness refuses any database not prefixed
  `tripplanner-sbx-` or the local store, reusing `sandbox_seed`'s existing
  refusal of `tripplanner-canary` and `tripplanner-prod`.
- **Trip numbering:** synthetic trips must never consume `debug_store`'s
  `archive_no` sequence, which is owner-facing.
- **Determinism:** mutations are a pure function of `(source plan, seed,
  generator version)` and are never stored. Planner-generated trips are stored
  and committed because regenerating them costs money.
- **Retention:** the corpus is preserved, not regenerable. The golden set is
  permanent. Reference records keep third-party text quarantined in one
  `source_text` field that analysis never reads, so it can be stripped in one
  command if the licensing position changes.

## Tag vocabulary

A tag is **not new state**. It is a named bundle of values in the preference
document the planner already keeps: `trip_style`, `budget_level`,
`planning_preferences.target_active_minutes_per_full_day`,
`planning_preferences.major_attractions_per_day`,
`planning_preferences.preferred_free_time_ratio`, `preferred_day_start` and
`preferred_day_end`, `interests`, `dislikes`, `transport_preferences.*`,
`food_preferences.*`, `hotel_preferences.*`.

Example bundles, to be confirmed against the corpus rather than assumed:

| Tag | Sets |
|---|---|
| `relaxed` | fewer major attractions per day, higher free-time ratio, later day start |
| `see-it-all` | more attractions per day, low free-time ratio, early day start |
| `party` | later day end, nightlife interests, later meal timing |
| `mountain` | nature and viewpoint interests, road-break preferences, drive limits |

Two consequences:

1. There is one source of truth for preference, so a tag click and a free-text
   statement cannot disagree.
2. Because each tag declares its fields, the harness can test whether the tag
   changes anything. Tags whose generated itineraries are indistinguishable are
   the same tag, and a tag that changes nothing does not ship.

The user-facing selector built on this vocabulary is **out of scope here** and
belongs in its own brief once the corpus has proved the list.

## Corpus tiers

| Tier | Provenance | Source | Committed | Purpose |
|---|---|---|---|---|
| Debug store | `real`, `revision` | every locally saved trip, automatic | yes (exists) | authentic shapes, free, includes intermediate states |
| Corpus - generated | `synthetic` | our planner driven by the request matrix | yes | authentic shapes at volume; costs money |
| Corpus - templates | `template` | built in code from the matrix | yes | free volume to stress guards |
| Corpus - reference | `reference` | curated real-world itineraries, tagged | yes (structure only) | benchmark: what a good itinerary looks like |
| Golden | `golden` | pinned known-good and known-bad shapes | yes (exists) | regression |
| Mutations | `mutated` | derived at run time from any of the above | no - zero bytes | metamorphic testing |

## API and integration contract

- Reuses `trip_guard.validate_plan`, `trip_validation.planning_completion_gaps`,
  `trip_view.build_itinerary`, `trip_view.build_map_view`.
- Reuses `sandbox_seed`'s emulator client, database-name guards, and `capture`.
- Reuses `debug_store.iter_records` as one corpus source.
- Agent generation drives the existing `/chat` endpoint of a running sandbox; it
  introduces no new backend contract.
- No shared-client or mobile impact.

## Privacy, security, abuse, and cost

- The corpus is single-owner local data and never leaves the machine. The debug
  store is already documented as raw and unredacted local-only data; the corpus
  inherits that stance.
- Nothing is added to analytics, logs, URLs, or third parties.
- Synthetic generation is the only cost: it calls the model and the place
  providers. It must print an estimate before running, accept a `--budget` cap,
  stop when the cap is reached, and be resumable rather than restarted.
- The offline loop must cost nothing: no model calls, no provider calls, place
  facts served from the emulator cache.

## Observability and feedback

- Each run writes a machine-readable report: findings by rule, by provenance,
  corpus size, and duration.
- Failure signal: count of new findings, and the metamorphic failure count
  separately, because the latter means a guard is broken rather than a plan.
- Quality metric: new findings per run should fall to zero and rise only when a
  rule is added or a regression lands.
- Rollout evidence: a new rule stays at `observe` severity until it has run over
  the full corpus with an understood false-positive rate, then is promoted. This
  is the process already used to promote I9 to the completion gate.

## Acceptance criteria

- **AC-01:** `Audit-Trips` runs the full rule set over every corpus record with
  no network access and no model calls, and completes over at least 100 trips
  within one minute.
- **AC-02:** The report groups findings by rule and symptom shape, showing one
  exemplar and an occurrence count, never one line per occurrence.
- **AC-03:** The command exits non-zero if and only if a finding is present that
  the committed baseline does not contain.
- **AC-04:** `Audit-Trips --accept` updates the baseline, and the diff is
  human-readable in git.
- **AC-05:** The harness reproduces the known Paris Day 7 continuity defect from
  the stored trip, identified by rule I9, without manual input.
- **AC-06:** For every mutation classified as degrading, the harness asserts the
  violation count does not decrease, and fails naming the rule that stopped
  firing when it does.
- **AC-07:** Reverting the 2026-08-13 `origin` coverage fix (I10) makes AC-06
  fail — the harness demonstrably catches a silently disabled guard.
- **AC-08:** Corpus records carry provenance, and findings are attributable to
  `real`, `synthetic`, `mutated`, or `golden`.
- **AC-09:** `Build-Corpus` stops at whichever of the requested trip count or
  the budget is reached first, defaults to 100 trips, and leaves a resumable
  manifest recording seed, matrix, generator version, model, date and spend.
- **AC-10:** No harness code path can address a database outside
  `tripplanner-sbx-*` or the local corpus directory.
- **AC-11:** `debug-store` `archive_no` values are unchanged by any corpus
  operation.
- **AC-12:** `Build-Corpus` imports the debug store by default, expanding each
  archived planning run into its final plan plus its stored revisions as
  separate corpus records.
- **AC-13:** `Audit-Trips` analyses every tier by default, and reports findings
  attributed by provenance so a reference or synthetic artefact is never
  presented as a product defect.
- **AC-14:** A reference record keeps all third-party text inside a single
  `source_text` block that no check or report reads, alongside `source_url` and
  `retrieved_on`, and a documented command removes that block from every record
  without changing any finding.
- **AC-15:** Given a reference tag set present in the corpus, the report states
  how our generated itineraries differ structurally from reference itineraries
  carrying the same tags, on at least stops per day and meal coverage.
- **AC-16:** Every tag in the vocabulary declares the preference fields it sets,
  and the report shows, per tag pair, whether generated itineraries under those
  tags actually differ — so a tag that changes nothing is visible as such.

## Validation matrix

| Layer | Required check | Evidence |
|---|---|---|
| Pure/domain logic | Unit tests for each new check and the mutation engine | Pending |
| Backend contract | Unchanged; regression suite must stay green | Pending |
| Web behavior | Unchanged | N/A |
| Shared client | Unchanged | N/A |
| iOS/Android | Unchanged | N/A |
| Accessibility/responsive | N/A | N/A |
| Build | Existing suite plus harness self-test | Pending |
| Canary | N/A - local tooling | N/A |
| Production | N/A - local tooling | N/A |

## Delivery and rollout

Smallest coherent milestone is **Phase 1**: corpus reader over the existing
stores plus plan-level checks, grouped report, baseline. It is useful on its own
against the seven real trips already stored.

- **Phase 1** - corpus reader, plan-level checks, grouping, baseline, launchers.
- **Phase 2** - render-level and cross-surface checks.
- **Phase 3** - mutation engine and metamorphic assertions.
- **Phase 4** - rules registry, so a new owner rule costs one entry.
- **Phase 5** - planner-driven synthetic generation, budgeted and resumable.
- **Phase 6** - reference corpus, tagging, and structural comparison.
- **Phase 7** - observation report for feature discovery.

Phases 1-3 carry nearly all the speed-up and do not depend on 5. No feature
flag: the harness ships disabled by virtue of being an explicit command. Rollback
is deleting the corpus directory; nothing else is touched.

Documentation: `docs/CODEMAP.md` gains the harness entry;
`docs/development/` gains the workflow; `scripts/README.md` gains the commands.

## Decisions and open questions

| ID | Question or decision | Recommendation | Owner answer/status |
|---|---|---|---|
| D-01 | Store the corpus in the debug store or separately? | **Separately.** The debug store is committed, owner-facing, and hands out human-readable trip numbers; hundreds of synthetic trips would bury the owner's real trips in `show`/`restore` and consume the numbering sequence they asked to expose in the UI. Five provenances, one reader. | **Resolved 2026-08-14: separate store.** |
| D-02 | Commit the synthetic corpus, or regenerate it from a manifest? | **Commit it.** Measured on 2026-08-14: a real 7-day trip is **7.3 KB** of JSON, so 100 trips is **0.7 MB** and 1000 trips is **7 MB**. Synthetic generation costs money and cannot be reproduced byte-for-byte anyway, so the earlier "regenerate from manifest" recommendation was wrong. Commit the corpus, keep the manifest for lineage, and fail the build if the corpus exceeds a declared size budget. | **Resolved 2026-08-14: commit and preserve.** |
| D-03 | Should the harness gate commits? | **Not initially.** Run on demand until new findings per run is near zero, then wire into pre-push. Gating on a noisy harness trains everyone to ignore it. | **Resolved 2026-08-14: no gating initially.** |
| D-04 | Template synthesis, or real planner runs? | **Both, two backends behind one command.** Templates are built in code from the request matrix and cost nothing, but their shapes are the ones we imagined, so they stress guards and discover nothing. Only real planner runs produce authentic shapes such as the three-airport `kind: "transport"` Paris leg. Default `Build-Corpus` uses the planner backend; `--templates` adds free volume. | **Resolved 2026-08-14: both.** |
| D-05 | How much corpus is enough? | Default target **100 planner-generated trips**, stopping at whichever of trip count or budget is reached first. Grow only while new findings per 100 trips stays above zero. | **Resolved 2026-08-14: default 100.** |
| D-06 | Nondeterminism of planner runs breaks regression comparisons. | Discovery uses fresh runs; regression uses the frozen golden set. Never compare two planner runs to each other. | **Resolved 2026-08-14: agreed.** |
| D-07 | Does the corpus include real trips from the debug store? | **Yes, by default and first.** Real trips are the highest-value records and cost nothing. Additionally, each debug-store record holds up to 50 **revisions** of one planning run, and intermediate states are exactly where guard defects live — the Nashik empty-itinerary defect was an intermediate state. Importing revisions as separate corpus records multiplies real coverage without a single model call. | **Resolved 2026-08-14: yes, default on.** |
| D-08 | Reference itineraries sourced from the internet: store the prose? | **Store it all for now, but quarantine it.** The owner's call: the planner is too small to attract attention, and the full text is more useful while the vocabulary is being derived. The risk is deferred, not accepted, so every reference record keeps third-party text in one `source_text` block that no analysis code may read, alongside `source_url` and `retrieved_on`. Stripping is then one command over one field, with no effect on any finding. | **Resolved 2026-08-14: store all, keep it strippable.** |
| D-09 | Are reference itineraries part of the golden set? | **No, a separate tier.** Golden records are *our* pinned known-good/known-bad shapes and must stay stable for regression. Reference records are *other people's* itineraries used as a benchmark. Conflating them would break regression the moment our planner legitimately differs from a reference. | **Resolved 2026-08-14: separate tier.** |
| D-10 | What vocabulary tags a reference itinerary? | **The planner's existing preference model, and the list is derived rather than invented.** A tag is not new state: it is a named bundle of values in the preference document that already exists (`trip_style`, `budget_level`, `planning_preferences.*`, `interests`, `transport_preferences.*`, `food_preferences.*`). Tagging the reference corpus in that vocabulary is what makes reference and generated itineraries comparable, and the corpus is then what proves which tags are real. | **Resolved 2026-08-14: planner's own model, derived from the corpus.** |
| D-11 | Should the tag vocabulary also become a user-facing click selector? | **Probably yes, but as a separate brief after the corpus has earned the list.** A tag qualifies only if it demonstrably changes what the planner does; a tag that changes nothing is decoration that creates expectation. The harness can settle this: generate the same request under two tags and compare. Two tags whose itineraries are statistically indistinguishable are one tag. Shipping a user-facing list before that check risks a preference contract we have to migrate later. | Open - propose as brief 005 |

## Agent execution contract

Per template. Additionally: the harness must never modify a stored plan, must
never call the model in its offline loop, and must state its corpus size and
provenance mix in every report so a clean run is distinguishable from an empty
one.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-08-14 | Brief created from owner's dictated intent | Agent |
