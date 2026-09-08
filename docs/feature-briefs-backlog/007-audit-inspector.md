# 007 - Audit inspector

> Sections 1-5 are **agent-drafted from the owner's dictated intent** on
> 2026-08-15. Overwrite them freely; the rest was normalized against the current
> system and is the part to argue with.

Continues [004 - Auto-validation harness](004-auto-validation-harness.md). The
harness finds problems; this brief is about *looking* at them.

## 1. Raw mind dump

> OWNER INPUT (agent draft)

The audit prints findings I cannot see. It tells me Day 1 draws an inter-city
train from Hampi Bazaar to Virupaksha Temple that covers no distance, and I have
no way to open that trip and look at it. Reading a defect in a terminal and
believing it are different things, and the ones I cannot see are the ones I
cannot prioritize.

I want to load a particular trip in the UI exactly as a user would see it. Maybe
a parallel debug trips UI, separate from the main app, on its own port like the
labs catalog. Something where I can also see the audit findings visually, with
highlighting on the thing being complained about — the rules we have today, what
is fixed, what is still open.

## 2. User problem

The owner is the only reviewer of audit output, and the output is currently a
terminal report of grouped symptoms with a single exemplar id like
`28:hampi_2027-01-05_2027-01-09#r1`. Turning that id into something they can look
at requires knowing that corpus trips are stored under synthetic `corpus-<slug>`
identities, opening the browser console, and hand-editing `localStorage`. Nobody
does that forty times, so triage collapses to whichever finding has the largest
count rather than the largest consequence.

Two failure modes follow. Real defects go unfixed because their exemplar was
never opened — the Hampi zero-distance train sat in the report for a full audit
cycle. And **noise gets accepted into the baseline unexamined**, which is worse:
an accepted finding stops being reported, so a rule that is firing wrongly and a
rule that is firing correctly become indistinguishable once both are silenced.

## 3. Desired outcome

The owner can go from a line in the audit report to the trip that produced it,
rendered by the real product UI, in one click — and see the finding marked on the
day or stop it names. Separately, they can see the whole rule set at a glance:
what each rule asserts, how often it fires, what is open, and what previous fixes
have retired.

## 4. Must-have examples

1. The report says `[R3] x3 Day 1 draws an inter-city Train ... covers no
   distance`. The owner clicks it, the Hampi trip opens in the normal itinerary
   and map panes, and Day 1's train leg is marked.
2. A finding's exemplar is a *revision* (`#r1`), not the trip's current state.
   Opening it must show the revision that was flagged, or say plainly that it is
   showing a later state.
3. The owner wants to know whether `[I9] x64` on the Coorg trip is a real
   routing defect or an artifact of the hotel being a placeholder called
   "3-star+ Hotel in Coorg". They need the trip and the finding side by side to
   tell, because the answer is visible in neither alone.

## 5. Boundaries

- Do not fork the product UI. A separate copy of the itinerary and map panes
  would drift and stop being evidence of what the user sees.
- Nothing here ships to canary or production. It is a local development surface.
- No writes to trips. The inspector reads; fixing happens in code.
- Do not let the debug surface change product behavior when it is switched off.

---

## Document control

| Field | Value |
| --- | --- |
| Status | In progress |
| Owner | Munish |
| Sandbox | `sbx-2-auto-validation` |
| Depends on | 004 auto-validation harness (phases 1-4, 7 shipped) |
| Supersedes | Nothing |

## One-sentence requirement

Make every audit finding openable in the real product UI and make the rule set,
its hit counts, and its open/fixed state visible on one page.

## Why now and evidence

- The 2026-08-15 audit reported **38 finding groups over 957 occurrences** across
  114 records. That is past the point where a terminal list can be triaged.
- The corpus build produced two trips with no itinerary at all. They were visible
  as a number in a manifest, and the defect behind them was found only because
  someone went looking in Cosmos by hand.
- `[R4] x100` "never reached the map (no_match)" is currently un-triaged
  precisely because deciding it needs the map, and the map needs the trip open.
- The baseline mechanism already distinguishes accepted / new / stale, so
  "what is open" and "what a fix retired" are derivable today and simply not
  displayed anywhere.

## Current behavior

- `scripts/dev/trip_audit.py` prints grouped findings and, with `--json`, emits
  `{corpus, provenance, sources, skipped, groups[]}`. Each group carries
  `rule, symptom, count, example, new` — the exemplar's **message** but not its
  record id, so the output cannot be linked back to a trip.
- Corpus trips live in the sandbox Cosmos database under `corpus-<slug>` user
  ids. `resolve_user_id` honors a claimed `user_id` when not hosted, so the data
  is reachable; there is just no route to it.
- The SPA takes its identity from `localStorage.tripplanner_user_id` and offers
  no way to set it other than `signIn()` for `user-*` and `local` ids.
- `registry()` already assembles all rules with severity and statement. Nothing
  displays it.

## Scope and priority

### Must ship

1. **Deep link into the product UI.** `?inspect=<user_id>` (optionally
   `&trip=<trip_id>`) adopts that identity and opens that trip. Gated behind a
   build flag so it cannot exist in a production bundle.
2. **A linkable audit report.** `trip_audit.py --report` writes
   `corpus/audit-report.json` containing the rule registry, every group with its
   individual findings (record id, day, provenance, message), the baseline state
   per group, and the observation block.
3. **Inspector app** on its own port with two pages that matter first:
   - **Findings** — groups, filterable by rule and provenance, each finding
     linking into the product UI.
   - **Rules** — every rule, its statement, severity, hit count, and state.

### Should ship

4. **Finding highlight in the product UI.** With `?inspect=`, findings for the
   open trip render as markers on the day or stop they name.
5. **Trips page** — the corpus browser: every record, its provenance, its
   finding count, one click to open.

### Could ship later

6. **Trend view** — groups over time, so a fix visibly retires a symptom.
7. **Rule authoring aid** — draft a new rule from a described symptom and show
   what it would fire on before it is committed.

### Out of scope

- Editing trips, accepting baseline entries, or triggering corpus builds from the
  UI. Accepting a finding stays a deliberate command-line act.
- Any hosted deployment, auth, or multi-user concern.
- Replacing the terminal report. It stays the fast path.

## Experience contract

### Entry point and workflow

The owner runs the audit, opens the inspector, scans Findings ordered by count,
clicks an exemplar, lands in the product UI showing that trip with the finding
marked, decides, and returns. Rules answers the separate question of what the
harness currently knows.

### Cross-surface behavior

- Identity adopted via `?inspect=` is real for the session: itinerary, map,
  details, and assistant all show that user's trip, because that is the point.
- Leaving inspection restores the previous identity rather than signing out, so
  the owner does not lose their own workspace.

### UI states

- **No report** — the inspector says the audit has not been run and gives the
  command, rather than rendering an empty table.
- **Stale report** — the report records when it ran and against which databases;
  the inspector shows that, so a finding that no longer exists is explicable.
- **Missing trip** — a finding whose record is no longer in the emulator says so
  instead of opening an empty workspace.

## Business and data rules

- The inspector is read-only against Cosmos and against the report file.
- `?inspect=` must be inert unless the debug flag is on at build time.
- The report is generated, not hand-edited, and is safe to commit alongside the
  corpus.
- Revision exemplars (`#rN`) are historical states. The product UI shows current
  state, so any revision finding must be labelled as such.

## Acceptance criteria

| # | Criterion |
| --- | --- |
| A1 | `?inspect=corpus-hampi` opens that trip in the product UI with no console use |
| A2 | The same URL with the debug flag off changes nothing |
| A3 | `--report` output contains, for every finding, a record id that resolves to a corpus record |
| A4 | Findings page lists all 38 groups and filters by rule and provenance |
| A5 | Rules page lists every rule in `registry()` with severity and current hit count |
| A6 | A rule that fires zero times is visible as such, not absent |
| A7 | Restoring identity after inspection returns the owner's own workspace |
| A8 | Nothing in the production bundle references the inspector |

## Validation matrix

| Risk | Check |
| --- | --- |
| Debug surface leaks to production | Build the production bundle and assert the flag-gated module is absent |
| Report drifts from the rules that run | Report is generated from `registry()`, and a test asserts every reported rule code exists in it |
| Identity swap corrupts owner data | Inspector never writes; a test asserts the restore path |
| Findings unlinkable | A test asserts every finding in the report carries a resolvable record id |

## Delivery and rollout

Local only. Ships behind `VITE_DEBUG_TOOLS`, off by default, enabled by the
sandbox dev stack. No canary or production exposure at any phase.
