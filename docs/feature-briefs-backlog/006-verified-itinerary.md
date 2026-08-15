# Brief 006 — Verified Itinerary: feasibility certificate and freshness

## Document control

| Field | Value |
|---|---|
| Brief ID | `006` |
| Status | Must-ship shipped; should-ship outstanding |
| Owner | Munish Goyal |
| Created | 2026-08-14 |
| Updated | 2026-08-14 |
| Baseline | `docs/REQUIREMENTS.md` |
| Target milestone | Verified Itinerary (milestone 1 of the research sequence) |
| Related capability IDs | PLAN-03, PLAN-04, ITIN-01, PLACE-01, SAFE-01 |
| Evidence | [`../research/ai-trip-planner-landscape-2026-08.md`](../research/ai-trip-planner-landscape-2026-08.md) |

## One-sentence requirement

As a traveller, I need to see what the planner checked, what it found, and what it
could not verify, so that I can trust the itinerary without re-checking every stop
by hand.

## Why now

The August 2026 landscape research found feasibility to be the category's largest
unsolved problem: r/travel and r/solotravel have both banned AI-generated
itineraries for producing plans that are not physically completable, and the
documented failures are opening-hours, closure, and travel-time errors. This
repository already owns a deterministic invariant engine that no competitor has.
The gap is that its findings are invisible to the user and incomplete on
closures.

## Current behavior

- `trip_guard.validate_plan` evaluates thirteen invariants and returns violations.
- `trip_validation.planning_completion_gaps` promotes a subset to a completion
  gate the agent must clear.
- `trip_view._opening_hint` attaches a soft per-stop `concern` string.
- Nothing tells the user which checks ran, which passed, or which could not be
  evaluated. Silence currently means both "verified fine" and "never checked".
- Closure knowledge stops at the weekly schedule. Public holidays, seasonal and
  renovation closures, and last-admission times are not represented.
- `find_local_events` returns prose from a web search, so it cannot feed an
  invariant.

## Scope and priority

### Must ship

1. A verification model that reports, per trip and per day, which invariants were
   evaluated, which passed, which failed, and which could not be evaluated and
   why.
2. "Could not verify" as a first-class result, distinct from "verified fine".
3. A read-only API surface carrying the certificate alongside the trip view.
4. A compact web surface showing the trip-level verdict, per-day badges, and the
   unverified list.
5. Public-holiday closure as a deterministic invariant, from a structured holiday
   source rather than prose search.
6. Last-admission handling so a visit that starts before closing but cannot
   finish is caught.

### Should ship

7. Seasonal and renovation closure detection, grounded and dated per place.
8. A pre-departure re-check that refreshes place facts and reports what changed.

### Could ship later

9. Certificate in exports and share views.
10. Native client parity.

### Out of scope

- Any change to booking, purchase, or handoff behavior.
- Blocking a user-initiated mutation on a soft or unverifiable finding.
- New paid provider dependencies.

## Settled business and data rules

- An invariant that cannot be evaluated is reported as unverified and never as
  passed. This preserves the existing guard rule that silence is not a verdict.
- Only invariants decided by a fetched fact may gate a planning turn. Invariants
  that depend on guessed coordinates or speeds remain advisory.
- The certificate is derived, never persisted as trip truth, so it cannot go
  stale against the itinerary it describes.
- Holiday data is per country and per date, resolved through the existing
  `place_country` boundary, and cached like other place facts.
- A holiday closure is asserted only when the source names the date as a public
  holiday in that country and the place is a kind that observes it.

## User scenarios

1. A traveller opens a finished Paris itinerary and sees "12 of 13 checks passed,
   3 stops unverified", with the Louvre flagged as closed on the chosen Tuesday
   and a one-tap move to Wednesday.
2. A traveller plans Christmas week in Rome. The Vatican Museums stop on 25
   December is reported as a public-holiday closure even though the weekly
   schedule says open.
3. A traveller plans a trip to a small town where the places cache has no hours.
   The certificate says those stops could not be verified rather than implying
   they are fine.
4. A traveller returns to a trip planned three months ago; the pre-departure
   re-check reports that one restaurant has closed permanently since planning.

## Privacy, security, and cost

- The holiday source is queried by country and year only; no trip, user, or
  place identity leaves the system.
- Results are cached per country-year, so a trip costs at most one lookup per
  destination country.
- The certificate contains no new personal data and is redacted from public
  shares only where it names private stops.

## Acceptance criteria

- AC-01 A trip whose stop falls on a known closed weekday reports a failed
  closed-day check naming the stop, the day, and the weekday.
- AC-02 A trip whose places have no fetched hours reports those stops as
  unverified, and the trip-level verdict is not "all checks passed".
- AC-03 A public holiday closure is reported for a place open on that weekday in
  its normal schedule.
- AC-04 A visit that starts before closing but ends after it is reported.
- AC-05 The certificate never contradicts `validate_plan` for the same trip.
- AC-06 The web surface renders verdict, per-day badges, and the unverified list,
  and remains correct when the trip has no itinerary.
- AC-07 No new invariant can gate a planning turn unless it is decided by a
  fetched fact.
- AC-08 Holiday lookups are cached and a failed lookup degrades to unverified
  rather than to an error or a false pass.

## Validation matrix

| Area | Validation |
|---|---|
| Facts | `tests/test_place_facts.py`, holiday parsing and caching tests |
| Invariants | `tests/test_trip_guard.py` closed-day, last-admission, holiday |
| Certificate | new `tests/test_trip_verification.py` for coverage and verdict |
| API | trip view/certificate response shape test |
| Web | Vitest for verdict, badges, and empty-itinerary states |
| Regression | full backend suite, frontend build, lint |

## Remaining follow-up

- Seasonal and renovation closure grounding (should-ship item 7) may land as a
  second increment once the certificate surface is validated.
- Export, share, and native parity are deliberately deferred.
- The arrival day has no soft protection. A plan with no inbound leg is not
  evidence that the traveller lands that morning, so the rebalance may place an
  early stop on day one. This closes when a trip records its travel scope.
- Retitling changes the theme term, so a second repair can find further
  improvements the first could not see. It converges within two or three runs
  and then reports nothing to do.
