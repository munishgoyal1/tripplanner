# Booking intent web workflow

## Document control

| Field | Value |
| --- | --- |
| Brief | 009, shipped web portion |
| Status | Implemented and validated; see publication in #323 |
| Owner | Munish Goyal |
| Implementation date | 2026-09-14 |
| Lane | `gpt/booking-intent-flow` |
| Baseline | `origin/master` at `fb383961` |
| Milestone | [#323](https://github.com/munishgoyal1/tripplanner/issues/323) |
| Parent | [#315](https://github.com/munishgoyal1/tripplanner/issues/315) |
| Remaining contract | [009 backlog](../feature-briefs-backlog/009-booking-readiness.md) |
| Canonical owners | BOOK-02 in REQUIREMENTS; EB-BOOKING-001; CODEMAP |

## Problem and outcome

The earlier foundation configured LiteAPI and cache/fallback boundaries. It did
not provide the complete user-facing booking-intent workflow. Travelers needed
to research practical choices within category budgets, understand alternatives,
export a final list, book anywhere, and reconcile what actually happened.

This milestone supplies that loop on responsive web. Tripplanner does not sell,
hold, purchase, pay, cancel, or verify provider confirmations. Lock means saved
intention; reported booking means the user says they booked elsewhere.

## Delivered scope

1. `/bookings`, accessible through Trip actions, reads the active saved trip.
2. Independent flight/hotel/ticket/transport caps with explicit amount/currency.
3. Exact saved flight/stay alternatives, including one-offer results and separate
   room/board/refund variants from the same property.
4. Explicit LiteAPI research with dates, party, cabin or room occupancy.
5. Before/after adjustment preview, affected day schedules, caps and warnings.
6. Revision-bound application, reversible intent locks and manual research.
7. Optional public HTTPS product links, or copyable details usable offline.
8. HTML/PDF/JSON/email/share booking-intent packets with private data redacted.
9. Actual external/offline bookings reconciled into existing purchase units.

## User flow

- Open an existing trip, then Trip actions → Bookings.
- Inspect independently capped category totals and missing evidence.
- Expand saved alternatives or explicitly research flights/hotels.
- Preview a choice; confirm only after reviewing product/price/terms/impact.
- Edit researched intent details for manually researched items and provider links.
- Lock the intention. The page continues to disclose stale or missing quotes.
- Export/share the booking intent list, or open an available provider product page.
- Complete purchases through any provider, agent, venue or offline channel.
- Return and record actual product, provider, dates/time, amount/currency and an
  optional private confirmation reference. Preview and apply to the same trip.

An unknown amount is blank, never zero. A click is never proof of booking.
Saved research may be exported with gaps and no working provider account.

## Architecture and data

`decisions/booking_intent.py` groups purchase units and constructs isolated
candidate changes. Return-flight bundles are one unit; repeated hotel anchors
share a stay unit bounded by dates. Ticket occurrences receive stable identities
when changed. The existing decision models remain the exact-offer evidence owner.

`category_caps` stores independent category amount/currency pairs. The planning
tool persists them before search and constrains recommendation ranking to known
affordable offers. Existing selection mutations reject known cap breaches.
Unknown currency, occupancy, bags, fees and stale quotes remain unverified.

`booking_intent.records[item_id]` stores lock fingerprint/snapshot, disposition,
original intention, user-reported actuals and review warnings. Selected items and
their itinerary anchors carry `booking_item_id`, plus decision ID where known.
Source timestamps are independent of intent state and never renewed on cache reads.

`web/booking_http.py` reuses authenticated request context, workspace exclusion,
the existing per-user mutation lock and `trip_planner._save_active_trip`.
All commands bind trip ID and `updated_at`; applying also requires the same exact
command's preview token. A failed/stale command writes nothing. The main planner
reloads the authoritative trip when returning from Bookings.

`web/booking_export.py` projects one redacted snapshot for packet formats. Export
endpoints require the reviewed trip/revision. Existing email orchestration owns
ACS/SMTP idempotency and fallback; booking packets do not introduce a send path.
Shares store immutable HTML, not a live pointer into the owner's active trip.

No storage migration, second agent or new provider client is introduced.
`graph.py` retains completion ownership; planning validation exposes category
breaches and incomparable whole-trip totals.

## Important behavior

- Re-search preserves the selected intention, even if the provider reuses an ID
  with a different price. The user explicitly previews and accepts the new quote.
- Non-equivalent rooms remain alternatives, without same-product savings claims.
- Repeated reports edit the same unit and apply one cost delta. A duplicate
  confirmation already attached to another unit is rejected.
- Actual product changes drop stale coordinates, private provider handles and
  original product-specific terms. The intention snapshot retains old evidence.
- Ticket/flight occurrences may move to another existing trip day. Missing days
  must be added to the itinerary before reporting those changes.
- Actual timing/cost conflicts are retained as warnings. Unknown/incomparable
  totals require recalculation rather than mixing raw currencies.
- Schedule, traveler and trip-date edits conservatively invalidate locks.
- Public packets omit private confirmation references and notes; only public
  researched variant/inclusion notes are included.

## Acceptance and evidence

| Criterion | Evidence |
| --- | --- |
| Separate INR 100,000 flight / INR 80,000 stay caps | Domain selection/ranking tests |
| GET projection does not fetch provider data | Network-denying projection test and mocked browser read |
| Historical/mismatched evidence is unverified | Expiry, currency and changed-party tests |
| Distinct room variants and repeated stays | Variant identity/reconciliation/grouping tests |
| Preview does not mutate; apply is atomic and revision-bound | API preview/tamper/replay/cross-trip tests |
| Same-ID refreshed quote requires explicit acceptance | Refresh/acceptance regression test |
| Lock is not booking; changed context requires review | Lock/fingerprint regression test |
| Manual research remains unverified intention | Ticket variant/link/total test |
| Actuals retain intent and avoid duplicate units/cost | Hotel, flight and ticket actual-report tests |
| Private reference redaction | JSON/HTML/PDF/share and fake-email tests |
| Email retry does not duplicate sends | Existing idempotency tests plus booking-template test |
| Responsive keyboard review flow | Desktop and 320px Chromium test; screenshots inspected |

Focused validation: 91 backend tests across booking, decision apply/API/store/
receipts, provider boundary, price recheck and email orchestration; seven web
component tests; two Chromium scenarios. Critical Ruff and frontend typecheck/
production build pass. Full suites remain suspended from lane gates and were not
claimed to pass. Provider and email calls are synthetic in this validation.

Commands use `pytest -o pythonpath=src` in the worktree so the shared interpreter
cannot accidentally import the primary checkout's editable installation.

## Limits and remaining work

The broader parent remains open. This milestone does not claim live production
account entitlement, Tiqets integration, exact checkout-link continuity,
multi-provider best-price coverage, full dependency repair, sourced multi-currency
category optimization, confirmation-document extraction, or native UI parity.
These remain in the backlog brief and parent issue.

Manual research and externally reported bookings work without those extensions.
No provider-side transaction or production deployment was performed. The primary
backend and built frontend need restart/rebuild after the merged code is synced.
