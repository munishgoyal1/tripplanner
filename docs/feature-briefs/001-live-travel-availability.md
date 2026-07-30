# Live Travel Availability and Rate Evidence

## Document control

| Field | Value |
|---|---|
| Brief ID | `001` |
| Status | Draft - awaiting LiteAPI account credentials |
| Owner | Munish Goyal |
| Created | 2026-07-30 |
| Updated | 2026-07-30 |
| Baseline | `docs/REQUIREMENTS_V2.md` v2.0 |
| Related capability IDs | PLAN-01, PLAN-02, PLAN-03, LIFE-01, REL-01, SAFE-01 |

## One-sentence requirement

As a traveler, I need itinerary hotel and flight choices backed by recent,
date-specific rates and availability so that the plan is trustworthy before I
leave the app to book elsewhere.

## Why now

Current hotel fallback can prove that a property exists and is well reviewed,
but it cannot prove room availability or an accurate stay price. Existing
provider tools also flatten offers into prose, losing provider IDs, quote age,
occupancy, taxes, cancellation terms, and expiration evidence.

LiteAPI (Nuitee Connect) currently exposes real-time hotel rates/availability,
flight rates, and flight-offer verification. Booking.com Demand API can later
provide accommodation search/availability through an affiliate account. Its
current public Demand API does not provide flight search.

## Scope

### Must ship

- Confirm with LiteAPI that planning-only/read-only rates traffic is allowed
  under the account's commercial terms and document applicable limits.
- Provider-neutral, separate hotel and flight search contracts. Do not create
  one lowest-common-denominator travel-provider interface.
- A LiteAPI adapter for read-only hotel rates and availability, including dates,
  occupancies, guest nationality, room/board, refundability/cancellation terms,
  taxes/fees, total display price, currency, provider IDs, and quote time.
- A LiteAPI adapter for flight search and read-only offer verification, including
  segments, fare/baggage terms, seats when supplied, total price, offer ID,
  retrieval time, expiration, and verification changes.
- Selected itinerary hotel and flight snapshots retain normalized quote evidence
  and provider references without storing credentials or raw provider payloads.
- Every rate is labeled `live`, `stale`, `unavailable`, `estimated`, or
  `provider_error`. Only a successful date/party-specific provider response can
  be labeled `live`.
- Explicit refresh bypasses shared tool cache. Volatile inventory must use the
  provider's expiration when available and otherwise a short provider-specific
  TTL; it must not inherit the existing 20-minute hotel cache.
- Provider failure preserves the itinerary and last quote as stale evidence.
  Google Places remains content/review fallback, never availability evidence.
- Web, mobile, export, and Assistant use the same normalized quote semantics.

### Should ship

- Compare a small set of preference-matched alternatives using total stay/trip
  price rather than an ambiguous nightly or base fare.
- Refresh selected offers when opening a saved trip and on explicit user action,
  with request coalescing and provider rate-limit protection.
- PII-safe provider latency, result count, stale age, error class, and price-change
  telemetry.

### Later

- Booking.com accommodation adapter using the same hotel contract after affiliate
  access and allowed integration flow are confirmed.
- Provider routing or comparison across LiteAPI and Booking.com.
- Redirect/affiliate handoff links.
- Prebook, booking, payment, cancellation, or post-booking operations.

## Business and data rules

- Catalog data and live inventory are different sources: a real hotel is not
  necessarily available, and a prior price is not a current quote.
- Search identity includes dates, origin/destination, travelers, child ages,
  rooms/occupancies, cabin/room preferences, nationality/point of sale, and
  currency. Cache keys must include every price-affecting input.
- Persist normalized evidence, not provider response blobs. Provider-specific
  IDs stay in an opaque `provider_ref` object owned by the adapter.
- Display totals inclusive of known taxes/fees and state plainly when provider
  charges remain payable at the property or are otherwise excluded.
- Currency conversion may be shown separately, but provider currency and amount
  remain immutable evidence. Never present a converted estimate as provider price.
- Hotel quote refresh calls rates/availability only. Flight quote refresh calls
  the provider's verify endpoint when the offer is still verifiable, otherwise
  reruns search and marks the prior offer unavailable until matched.
- No read path may call prebook, order preview, booking, payment, or cancellation.

## Proposed code ownership

```text
src/tripplanner/providers/
  models.py                 Normalized queries, offers, money, policies, freshness
  registry.py               Configured capability selection
  hotels.py                 Hotel provider protocol
  flights.py                Flight provider protocol
  liteapi/
    client.py               Authenticated HTTP, errors, timeouts, observability
    hotels.py               LiteAPI hotel normalization
    flights.py              LiteAPI flight search and verify normalization
  booking_com/
    hotels.py               Later accommodation-only adapter
```

Existing LangChain tools remain the agent boundary and delegate to the registry.
The model sees compact normalized JSON, not provider-specific schemas. Existing
Duffel and Amadeus implementations can be adapted behind the flight/hotel
contracts incrementally rather than rewritten in the first milestone.

## Acceptance criteria

- **AC-01:** A hotel search for exact dates and party returns normalized available
  room offers with total price, currency, inclusions, cancellation evidence,
  provider IDs, and quote time.
- **AC-02:** A flight search returns normalized offers with expiration; selecting
  or refreshing an offer verifies it and surfaces any price or fare change.
- **AC-03:** A selected quote older than its allowed freshness is visibly stale
  and cannot be described by the Assistant as currently available.
- **AC-04:** A provider timeout, 204/no availability, expired offer, or malformed
  response does not erase the itinerary or silently substitute Google content as
  live inventory.
- **AC-05:** Saved trips and older clients remain readable when quote evidence is
  absent; legacy prices are classified as `estimated`.
- **AC-06:** No endpoint or tool performs prebooking, booking, payment, order
  creation, cancellation, or modification.
- **AC-07:** Credentials remain server-side and are redacted from logs, errors,
  persisted plans, exports, and client contracts.

## Delivery plan

| Milestone | Outcome | Gate |
|---|---|---|
| 1 | Normalized models, protocols, registry, fake adapters, freshness tests | No credential needed |
| 2 | LiteAPI hotel adapter and itinerary rate evidence | Search-only terms confirmed; LiteAPI key supplied locally |
| 3 | LiteAPI flight search/verify adapter and selected-offer refresh | Flight access confirmed on account |
| 4 | Shared web/mobile/export freshness presentation | Backend contracts stable |
| 5 | Booking.com hotel adapter | Affiliate access and integration flow approved |

No Azure deployment or production credential configuration is included without
separate owner approval.