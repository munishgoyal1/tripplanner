# Booking Readiness and Budget-Constrained Selections

## Document control

| Field | Value |
| --- | --- |
| Brief ID | `009` |
| Status | Web intent workflow shipped in child #323; provider/dependency/native follow-ups remain |
| Owner | Munish Goyal |
| Created / Updated | 2026-09-12 / 2026-09-13 |
| Baseline | `origin/master` at `f07f96dd` |
| Shipped milestone | [009 web workflow](../implemented/009-booking-intent-workflow.md), child [#323](https://github.com/munishgoyal1/tripplanner/issues/323) |
| Feature issue | [#315](https://github.com/munishgoyal1/tripplanner/issues/315) — keep open until all feature criteria pass |
| Foundation issue | [#316](https://github.com/munishgoyal1/tripplanner/issues/316) — configuration, fallback boundary and workflow |
| Related capabilities | `PLAN-01`, `PLAN-02`, `DEAL-01`, `LIFE-01`, `ITIN-01`, `MUT-01`, `EXPORT-01` |
| Advances | [004 comparison foundation](004-item-comparison-budget-what-if.md) |
| Provider evidence | [Provider API Access](../research/provider-api-access.md) |

## User problem and outcome

The traveler needs a trip that satisfies spending and practical constraints,
plus exact selections they can book externally. Price discovery must influence
itinerary construction: a late booking page cannot repair an unaffordable trip
without changing its selections.

The user directed provider identification and next planning steps. This brief
records the delivery contract; it does not claim shipment or authorize provider
purchases, new commercial commitments, external messages or production deployment.

As the trip owner, I need price-aware recommendations, saved alternatives and
a final item-to-seller list so that I can book without repeating the research.

## Current behavior and gaps

Canonical docs and brief 004 describe saved flight/stay candidates, deterministic
comparison, user-owned budgets, FX provenance, explicit rechecks and synchronized
mutations. EB-DEAL-001 requires exact identity and known mandatory costs for
savings comparisons. Verify behavior with focused tests before changing it.

The inspected registry wires LiteAPI for hotels/flights and Viator for activities;
rail/coach/ferry registries are intentionally empty. Configuration is not proof
of production access, inventory coverage or checkout readiness.

New work: early category-cap feasibility, booking readiness, product-versus-seller
comparison, dependency-aware overrides and a dedicated booking review surface.

## Scope and milestones

The shipped portion is split into the linked implemented brief. This backlog
retains the broader design contract and the remaining work under #315, not a
second queue entry for the completed web implementation. Current behavior is
authoritative in BOOK-02 and EB-BOOKING-001.

Implementation lane: `gpt/booking-intent-flow`, claimed under #315. Deliver the
responsive Bookings surface, exact saved alternatives, preview/apply, category
caps, lock/unlock, explicit research, PDF/HTML/JSON/email/share intent exports,
and manual external/offline booking reconciliation in one coherent feature.
Reuse existing LiteAPI adapters and export delivery. Ticket/ground items support
manual intent, reported actuals and sourced links; Tiqets live integration remains
conditional on selected, verified account access and is not invented here.

### Current milestone — LiteAPI-only search foundation

- Explicitly select LiteAPI for flight/hotel inventory in all environment profiles.
- Prevent either flight tool from falling through to legacy inventory after an
  empty/error LiteAPI result. Keep metadata-only hotel context available.
- Isolate explicit LiteAPI tool-result keys from retained legacy/automatic
  results without deleting earlier research.
- Preserve existing indefinite stable/volatile retention. Retained observations
  keep their original timestamps and expiry; refresh remains explicit.
- Start with available account access. Per the owner, defer commercial/policy
  review rather than blocking implementation on negotiation. Technical access
  denials remain visible; no access bypass or fabricated booking conversions.
- Track every feature with a GitHub issue and keep cross-linked repository briefs.

### First implementation milestone — flight-and-stay readiness

- Structured category caps influence itinerary recommendations.
- Project exact saved flight/stay decisions into a trip-scoped Bookings page.
- Compare alternatives; show multiple sellers only with equivalent actual offers.
- Preview/apply overrides through existing authoritative mutations.
- Explicitly recheck where supported, lock choices and export a versioned
  booking-intent list through the existing itinerary export patterns.
- Record bookings made with any provider or offline and reconcile the actual
  details back into the authoritative itinerary through a previewed mutation.
- Show unsupported required bookings and unpriced costs as gaps; do not claim
  whole-trip readiness simply because supported flights/stays are ready.

The first version uses one inventory source for flights/hotels. Compare its
saved alternatives and disclose coverage; do not imply multi-source price checks.

### Following milestones

Activity/ticket variants with Tiqets and Viator; second-source stays with
Booking.com if admitted; selected ground/transfer/car coverage after validation.
Native clients use the same contract; device parity requires actual checks.

### Out of scope

Provider holds/purchases/payments/cancellations/order management, autonomous
monitoring, card/loyalty offer ingestion, commission-led ranking, a second trip
agent and broad unconditional provider fan-out.

## Experience contract

### During planning

1. Interpret explicit category caps using known party, currency, dates and rooms.
   Label assumptions; ask only indispensable questions.
2. Persist/render a useful draft promptly, then research major cost constraints
   within the authorized planning action before declaring them satisfied.
3. Check hard constraints deterministically before preference ranking.
4. Assess combinations: hotel location affects transfers; arrival affects usable
   time and tickets. Cheapest independent items need not be the best trip.
5. Keep a bounded shortlist with meaningful cost, convenience or flexibility differences.
6. If no feasible combination exists, propose concrete constraint changes and
   consequences; never silently relax caps or omit required stops.

Flight and stay caps are independent. Cheap hotels cannot subsidize a flight
cap breach. Unknown mandatory charges prevent verified-fit claims; missing cost
is never zero. Estimates can inform a clearly provisional draft but cannot
enter the existing exact-price ranking tier as quotes.

### Bookings page

Implemented route: `/bookings`, optionally `?trip_id=...`, bound to the active trip and revision.
Read persisted state. Page GET/render causes no provider calls; research/recheck
is an explicit action or part of the authorized itinerary-building turn.

Show category caps, selected booking subtotal, separately labeled estimated
whole-trip costs, freshness and unresolved required items. Each row carries
exact choice, dates/local times, party, inclusions, fees, cancellation terms,
source, seller, checked time and handoff level.

Separate two intents: changing the product/rate, and changing seller for the
same exact product/rate. Saved alternatives need no fetch to display. Expired
or context-mismatched options remain identifiable but need validation before
presenting them as current bookable choices.

Preview the cost, terms, timing and dependent-stop impact before application.
If repair is needed, present the full repair. Reject hard-constraint violations
unless the user explicitly changes the constraint. Apply accepted patches
atomically by trip revision across Itinerary, Map, Details, Assistant and Bookings.
Failed/stale writes preserve the saved trip. Restoration does not resurrect
historical price or availability evidence.

Desktop may compare beside an item; mobile stacks with a clear return path.
Use keyboard controls, visible focus, announced errors and focus restoration.
No essential facts depend on hover. Preserve semantics across shared clients.

### Lock, export and handoff

Selection state (recommended/user-selected/locked) is independent of evidence
state (checked/stale/unverified/unavailable). Lock saves reversible user intent,
not inventory. Relevant trip changes invalidate affected readiness.

Before handoff, recheck where supported, disclose movement, revalidate constraints
and trip revision, and obtain acceptance of material changes. Never auto-switch
a selected product/seller because its quote changed.

Research may be locked/exported with stale or unavailable evidence if clearly
labeled; that export makes no current-price or booking-readiness guarantee.
Do not make a checkout account or an exact-offer redirect a prerequisite to export.

Save a versioned mapping of purchase unit to product/rate, operator, seller,
payable-price evidence and destination. Return-flight bundles and multi-night
stays remain single purchases. Ticket slots retain itinerary occurrence IDs.

Handoff levels must be literal:

- Exact-offer checkout: tested product/rate/date/party continuity.
- Product/date-context page: remaining checkout selection is visible.
- Search/official-provider page: copyable checklist, price does not carry over.
- No online handoff, pay locally, no booking needed, or unresolved.

Do not manufacture URLs from opaque IDs or attach one seller's price to another
seller's link. Preserve required attribution. A link click records handoff only;
booked externally requires explicit user reporting or future supported evidence.

Reuse itinerary-export delivery patterns for a dedicated **Export booking intent
list** action: downloadable document, email and share. Snapshot the trip revision,
export time, grouped items, selected product/variant, dates/local times, travelers
and occupancy, operator/source/suggested seller, quoted currency/amount, included
and unknown fees, terms, checked time/expiry, handoff level and verified URL.
Include unresolved items and copyable details for offline or other-provider use.
Private references and traveler details follow the export's audience/privacy rules.

### Report externally booked items

Let users mark one or several items booked with the suggested provider, another
provider or offline. Capture actual product, dates/times, party, paid amount and
currency, optional booking reference and confirmation document. Preserve the
selected-intent snapshot separately from reported actuals. A link click or lock
never supplies booking evidence; manual reports are labeled user-reported.

Match to the existing purchase unit/itinerary occurrence, handle partial and
duplicate reports, and preview date, budget and dependent-stop conflicts before
applying actuals. Do not create a second stay/flight for an existing purchase.
Accepted changes update Itinerary, Map, Details, Assistant and Bookings together
under the current revision; stale writes preserve the saved state. Keep private
references out of shared exports unless the user explicitly includes them.

## Business, data and architecture rules

Reuse decisions, cost ledger and mutation owners. Extend backward-compatible
contracts only where existing fields cannot represent required facts:

- Category cap amount/currency/scope/hardness and explicit user ownership.
- Inventory provider, operator/supplier, seller and internal provider offer ID.
- Exact search context: market, dates/time zone, legs, ages and occupancy.
- Flight segments/cabin/fare/bags; hotel identity/room/board/refundability;
  activity variant/language/slot/age bands for equivalence.
- Original and refreshed observations, expiry, evidence and fee completeness,
  native amount/currency and sourced display-FX provenance.
- Handoff level, verified URL, carried/omitted fields, trip revision and lock.

List price, conditional discount and payable total remain distinct. Include
mandatory local-pay charges in obligations. Deposits/refundable card blocks
are separate cash requirements, not double-counted costs. Uncertain name-based
matches may be alternatives but cannot support same-product savings claims.

Invalidate only affected dependencies after edits. Preserve original timestamps
and good saved evidence on partial failure. Deduplicate shared inventory and
disclose source/seller coverage; never promise a global optimum.

`graph.py` remains the agent/tool loop and completion authority. `decisions/`
owns deterministic comparison/feasibility; `providers/` owns clients, cache,
capability checks and fallback; `api.py` retains HTTP adaptation;
`web/trip_view.py` projects authoritative state. Model prose explains evidence;
it cannot manufacture amounts or provider facts.

## Privacy, provider terms and cost

- Compare a small number of eligible sources when useful within the user's
  planning/recheck action, not unconditional background fan-out.
- Preserve pooled HTTP, attribution, kill switches and measured spend ceilings.
  Account for newly billable provider operations before enablement.
- The owner explicitly chose indefinite LiteAPI research retention for the initial
  experiment and deferred provider-policy review. Preserve attribution, original
  checked timestamps and expiry; retention is not freshness or availability.
- Opaque handles, raw checkout tokens and traveler-sensitive data remain out of
  public shares, analytics and logs. Credentials remain server-side secrets.
- Endpoint support, account entitlement and successful live evaluation are
  separate facts. Sandbox success cannot satisfy production readiness.

## Acceptance criteria

- **AC-01:** INR 100,000 whole-party return-flight cap and INR 80,000 all-night
  stay cap are enforced separately without cross-category subsidy.
- **AC-02:** Unknown required fees, occupancy, FX or bags prevent verified fit
  while preserving a useful provisional draft.
- **AC-03:** Saved choices originate from exact responses with context/timestamps;
  opening Bookings initiates zero provider calls.
- **AC-04:** Non-equivalent room/refund/bag/ticket variants never appear as exact
  seller comparisons; missing mandatory charges suppress savings claims.
- **AC-05:** Override previews price, timing and terms; accepted application
  updates all trip surfaces atomically under the current revision.
- **AC-06:** Conflicting/over-cap choices do not silently apply; stale writes and
  dependent patch failures leave the saved trip unchanged.
- **AC-07:** Expired/sold-out rechecks retain selected intent, disclose new
  evidence and require explicit acceptance before replacing a choice.
- **AC-08:** Lock creates no hold/booking; relevant edits invalidate readiness;
  unlock/restore never claims historical availability is current.
- **AC-09:** Final rows group purchases correctly and retain exact context,
  seller, terms, amount provenance and verified handoff level.
- **AC-10:** Generic/product links never imply exact-rate continuity; clicking
  never changes an item to booked.
- **AC-11:** Single-source coverage and missing categories stay visible; no
  complete-trip-ready/global-best-price claim follows from partial evidence.
- **AC-12:** Currency conversions retain provenance; local fees and refundable
  deposits are represented without omission or double counting.
- **AC-13:** Trip ownership and revisions protect reads/writes; shared payloads
  and telemetry exclude secrets and private provider references.
- **AC-14:** Disabled, unentitled or unvalidated capabilities fail closed;
  sandbox data cannot satisfy live budget/readiness evidence.
- **AC-15:** Explicit LiteAPI flight selection never calls Duffel/Amadeus after
  empty/error results. Profiles select LiteAPI for both flight and hotel inventory.
- **AC-16:** Repeated cache reads retain the original observation/expiry, forever
  settings retain saved research, and explicit refresh bypasses lookup.
- **AC-17:** Download/email/share export the same versioned intent snapshot,
  including gaps, freshness and copyable details. Export requires no purchase,
  provider account, exact-offer URL or claim of current availability.
- **AC-18:** Reporting partial or complete external/offline bookings preserves
  planned vs actual values, deduplicates matched items and previews conflicts;
  accepted actuals update every trip surface under revision/ownership checks.

## Validation matrix

| Layer | Smallest proving check | Status |
| --- | --- | --- |
| Research | First-party sources and accurate access/claim labels | Refreshed 2026-09-13; live access untested |
| Domain | Caps, party totals, unknown fees/FX, equivalence, grouping | Web milestone focused checks pass; richer FX/dependency optimization remains |
| Provider | LiteAPI-only empty/error boundary; dated live coverage probes | Focused fallback checks in milestone #316; live access untested |
| API/state | Revision conflict, atomic rollback, ownership, zero fetch on GET | Web milestone focused checks pass; existing authenticated request context reused |
| Web | Compare, preview, apply, restore/recheck, lock, degraded handoff | Implemented; component and Chromium checks pass |
| Accessibility | Keyboard/focus/errors; 320px and desktop | Chromium keyboard and overflow checks pass; screenshots inspected |
| Shared/mobile | Contract compatibility and changed device surfaces | Pending; no parity claim |
| Handoff | Browser continuity check through redirect; stop before purchase | Pending permitted provider access |
| Export/reconcile | Snapshot formats, privacy, partial/duplicate/conflicting actuals | HTML/PDF/JSON/email/share and manual actuals tested; document extraction remains |
| Local/CI | Ruff, focused fallback/cache tests; existing CI typecheck/build | Recorded in milestone #316 |

## Next work and unresolved evidence

1. Engineering/account owner: exercise search with available credentials and exact
   trip context. Flight production enablement is separate from hotel access;
   surface actual access failures without inventing live evidence.
2. Engineering: extend dependency-aware repair, sourced multi-currency category
   feasibility and exact seller/redirect continuity beyond the shipped web flow.
3. Engineering: evaluate Tiqets Essential for attraction/experience variants,
   exact totals and affiliate URL continuity; no Full Booking API is needed.
4. Later: confirmation-document ingestion, native Bookings UI, second-source
   comparisons and ground coverage. Booking.com admission
   and broader commercial negotiations are not prerequisites for this milestone.

Provider names and current access evidence belong in the linked research
catalog, not duplicated as enabled configuration here. Material unknowns are
entitlement, planning-heavy usage economics, exact checkout continuity and
regional coverage. Resolve these with evidence rather than another broad
product-design approval loop. Canonical shipped-behavior docs update only when
implementation and its focused validation land.
