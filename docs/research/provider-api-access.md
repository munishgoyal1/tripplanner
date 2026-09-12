# Provider API Access — Booking Readiness

Reviewed 2026-09-12 against first-party documentation and partner pages.
This replaces the 2026-08-10 access review. It is an evaluation catalog, not
an assertion that accounts, production entitlements or integrations are ready.
Implementation contract: [brief 009](../feature-briefs-backlog/009-booking-readiness.md).

## Recommended direction

Keep Google Places/Routes for itinerary context. Evaluate existing Nuitee/LiteAPI
for exact hotel and flight choices, and Viator plus Tiqets for activities.
Target Booking.com Demand as the second stay seller if managed-affiliate access
succeeds. Multi-seller flight comparison remains an access-dependent gap.
Investigate Omio's referral model for global rail/coach before a full retail API.
For India, use IRCTC/redBus as external destinations until licensed inventory
access is established. No provider is assumed to cover every market.

Inventory source, operator and seller are separate identities. A LiteAPI or
Amadeus quote does not establish the same fare on an airline's consumer website.
Likewise, three brands backed by the same inventory are not three independent
price checks. Preserve source, seller and upstream identity where available.

## Verification boundary

- Public vendor documentation was researched. No authenticated inventory probes,
  checkout tests, applications, contracts, purchases or paid calls were made.
- Account entitlement, permitted search-only use, geographic coverage, actual
  quote completeness and link fidelity need separate evaluation before enablement.
- Sandbox results prove integration handling, not real budget feasibility.
- Public tariffs support estimates; exact dated party-specific offers support
  quotes. Catalog from-prices and fare indexes cannot become payable totals.
- A public consumer website is not an API. Never use unofficial scraped mirrors.
- No holds, purchases, payments, cancellations or provider orders are in scope.
  Inspect POST semantics: even a price check may create a checkout session.

## Providers by category

These are recommended evaluation choices, not measured inventory-quality rankings.
Evidence and limitations follow the table; references identify the source sections.

| Category | During itinerary construction | At booking handoff | First step / limitation |
| --- | --- | --- | --- |
| Flights | LiteAPI exact-date offers; permitted indicative data for date exploration | LiteAPI flight Whitelabel if entitled and verified; Skyscanner/Aviasales seller links if approved | Existing adapter first; second seller not yet accessible/proven. F1–F5 |
| Hotels | Places for location/amenities; LiteAPI dated occupancy rates | LiteAPI hosted checkout; Booking.com as second seller; separately checked hotel-direct offer | Match property, room, board and refund terms. H1–H3, C1 |
| Tours/activities | Viator catalog and Tiqets; exact dates/party at permitted tier | Viator referral, Tiqets affiliate, verified operator page | Evaluate Tiqets Essential alongside existing Viator. A1–A3 |
| Attraction tickets | Venue rules plus Tiqets/Viator variant, slot and age-band evidence | Verified venue/variant referral; product page when exact handoff unsupported | Admission-only, tours and bundles are different products. A1–A3 |
| Rail/coach outside India | Omio search if approved; operator schedules; Distribusion candidate | Omio referral or operator; contracted hosted retailer flow | Test individual routes and referral suitability. G1–G2 |
| Indian rail | Licensed IRCTC/authorized-partner inventory; official facts otherwise | IRCTC and copyable train/date/class/party checklist | No public live fare/seat API established here. G3 |
| Indian buses | Licensed redBus/operator inventory if contracted | redBus/operator booking page | No self-service inventory API or exact-seat link established. G4 |
| Ferries | Operator timetable; negotiated Distribusion coverage | Ferryhopper affiliate or official operator | Links are not fare feeds; include vehicle/passenger mix. G2, G5 |
| Airport/private transfers | Welcome Pickups partner API if approved; Routes timing | Welcome hosted widget or Kiwitaxi route link | Test luggage, child seats, pickup and waiting terms. T1 |
| Rental cars | Booking.com Demand car search if enabled | Returned car rental web/app URL | Driver, depots, mileage, fuel, excess and deposit matter. T2 |
| Local transit/walking/driving | Google Routes; official GTFS where available; existing routing fallback | Operator payment guidance or no booking needed | Journey/fare evidence is not reserved inventory. C1–C2 |
| On-demand taxis | Routes for timing; no invented future surge quote | Uber pickup/drop-off deeplink or verified local operator | Current price shown by destination app. T3 |
| Dining | Places, restaurant website/menu and hours | Restaurant's reservation page or verified linked reservation service | Places price level is not meal quote/table availability. C1 |
| Events/performances | Ticketmaster Discovery and venue calendars | Returned event URL or venue box office | Price ranges do not verify seats/final fees. A4 |
| Weather/seasonal context | Existing Open-Meteo and official advisories | No booking provider | Respect forecast horizon and service plan. C3 |

## Flights

**F1 — Nuitee/LiteAPI: first evaluation, production-gated.** The registry already
wires its flight adapter. Vendor docs say production and flight Whitelabel
require enablement; sandbox must not validate real-world pricing. Confirm
entitlement, route coverage and exact external handoff before claiming readiness.
[Flight access](https://docs.liteapi.travel/docs/getting-access-to-flights).

The current rate card charges EUR 0.005 per flight search above a 1,500:1
search-to-booking ratio. Hotel core usage also depends on reasonable look-to-book
usage; indexes cost USD 0.05/request and Places USD 0.01/request. Obtain written
clarification for planning-heavy use and whether hosted completions count toward
the ratio. Do not call discovery unconditionally free.
[Pricing](https://docs.liteapi.travel/reference/api-pricing-usage-costs).

**F2 — Skyscanner: future metasearch, not an MVP dependency.** Indicative and
live APIs are distinct. Public criteria exclude sites below 100,000 monthly
active users and some pre-product startups. Do not assume an exception.
Current docs include hotel/car products; an older 2023 support page says flights
only. Prefer current product docs and actual account entitlement.
[APIs](https://developers.skyscanner.net/docs/intro),
[access](https://www.partners.skyscanner.net/contact/travel-api).

**F3 — Aviasales via Travelpayouts: future comparison, access-gated.** The current
real-time guide requires at least 50,000 MAU and documents airline/agency purchase
links after selection. It requires actual initiating-user request context.
It points smaller projects to Data API; indicative/cache data is not live exact
inventory. Review user-trigger, comparison and retention rules before use.
[Search guide](https://support.travelpayouts.com/hc/en-us/articles/30565016140434-Aviasales-Flight-Search-API-real-time-and-multi-city-search).

**F4 — Duffel: defer for referral-only scope.** Search and offer refresh are
documented; the normal flow continues to order creation. Low conversion incurs
excess-search costs. A matching external consumer checkout was not established,
so this is not a drop-in second handoff source.
[Flow](https://duffel.com/docs/guides/getting-started-with-flights),
[economics](https://help.duffel.com/hc/en-gb/articles/4412912264466-What-is-Excess-Search).

**F5 — Amadeus Self-Service: optional research source, not handoff-ready.** Its
FAQ describes published-fare coverage limitations and consolidator requirements
for ticket issuance. Verify airline coverage and permitted search-only use; a
same-price consumer checkout was not established here.
[FAQ](https://admin.developers.amadeus.com/self-service/apis-docs/guides/developer-guides/faq/).

## Hotels

**H1 — LiteAPI: closest existing exact-selection path.** Whitelabel docs support
hotel/date/occupancy links and checkout using offer or prebook identifiers.
Evaluate the offer handoff before adding session-creating prebook calls. Hosted
checkout alone does not establish seller, merchant, support or refund ownership;
confirm these for the actual account.
[Deeplinking](https://docs.liteapi.travel/docs/deeplinking-to-whitelabel),
[prebook semantics](https://docs.liteapi.travel/reference/post_rates-prebook).

**H2 — Booking.com Demand: preferred second stay seller, gated.** The redirect
tutorial provides accommodation URLs with dates and guest context. Managed
Affiliate registration, an agreement and Partner Centre credentials are required.
Verify whether room/rate selection survives redirect; a property-context link
alone is not exact-rate continuity.
[Prerequisites](https://developers.booking.com/demand/docs/getting-started/prerequisites),
[tutorial](https://developers.booking.com/demand/docs/accommodations/accommodation-tutorial).

**H3 — Expedia Travel Redirect: defer new onboarding.** It supports flight/stay
search and external links, but new API applications are publicly marked paused.
Rapid's end-to-end booking product is a different integration, not a presumed
workaround. [Overview](https://developers.expediagroup.com/travel-redirect-api),
[onboarding](https://developers.expediagroup.com/travel-redirect-api/api/start-guide/getting-started).

## Activities, admission and events

**A1 — Viator: retain discovery, verify richer tier.** Basic affiliate access is
self-service and redirects to Viator. Full access adds richer data/live
availability with approval/certification. Exact checks require dates and party
mix; do not promote catalog from-prices.
[Tiers](https://partnerresources.viator.com/travel-commerce/levels-of-access/),
[availability](https://partnerresources.viator.com/travel-commerce/managing-product-availability-data/).

**A2 — Tiqets: first second-source evaluation.** April 2026 affiliate guidance
advertises instant Essential tokens for content, availability, pricing and
reporting. Extra content is on request; booking API restrictions are separate
and do not apply to our choice of a referral-only integration. The repository's
older generic partner-gated description is too coarse. Actual entitlement,
attribution, retention, image rights and variant/date link continuity need testing.
[Essential](https://partners.tiqets.com/en_us/do-you-offer-api-solutions-H1pJDp3zi),
[program](https://www.tiqets.com/en/partner-program/api-program/),
[docs](https://developers.tiqets.dev/).

**A3 — GetYourGuide: defer API.** September 2026 eligibility lists 100,000
monthly website visits or 50,000 app downloads for Basic; richer tiers require
more. Supplier-connectivity APIs are not the demand-side Partner API needed
here. Affiliate links can be evaluated separately.
[Eligibility](https://partner.getyourguide.support/hc/en-us/articles/13981133907613-API-integration-and-requirements),
[Partner API](https://code.getyourguide.com/partner-api-spec/).

**A4 — Ticketmaster: discovery and event handoff.** Discovery exposes event
URLs and price ranges. Exact seats, availability and final payable fees remain
unverified without appropriate additional evidence.
[Discovery](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/).

## Ground transport and India

**G1 — Omio: first referral-fit enquiry.** The affiliate page explicitly offers
search API, widgets and deeplinks. This fits our handoff goal better than
assuming a retail booking engine is suitable. It does not establish account
entitlement, cost, route coverage or exact checkout fidelity.
[Affiliate program](https://www.omio.com/affiliate).

**G2 — Distribusion: negotiated alternative.** Its platform covers rail, bus and
ferry distribution with retailer booking-engine products. Confirm market/carrier
coverage and hosted-checkout responsibilities. Broad supply alone does not
justify the earlier document's blanket recommendation over a referral API.
[Products](https://www.distribusion.com/products),
[network](https://www.distribusion.com/about-us).

**G3 — IRCTC: external Indian rail handoff, licensed machine access only.**
Official materials describe consumer booking and a formal B2C PSP policy.
Consumer accounts, PNR services and unofficial mirrors are not evidence of an
authorized fare/search API. Verify the applicable startup/MSME path separately;
no generic partner fee is assigned here.
[Consumer flow](https://contents.irctc.co.in/en/bookEticket.html),
[general PSP policy](https://contents.irctc.co.in/en/B2C_PSP_Policy_other_than_Startup_MSME.pdf).

**G4 — redBus: handoff candidate only.** Its public redTribe page is an
influencer program, not an inventory API. This review established no suitable
self-service machine access; a licensed integration needs its own documentation
and route tests. [Program](https://www.redbus.in/content/redtribe/).

**G5 — Ferryhopper: referral first.** Affiliate links, widgets and banners are
offered after application. This establishes a handoff path, not a live fare feed
or exact vehicle/seat reservation.
[Program](https://partners.ferryhopper.com/affiliates).

## Transfers, local movement and supporting context

**T1 — Welcome Pickups / Kiwitaxi.** Welcome offers partner API and hosted
affiliate widget paths; Kiwitaxi documents route links. Exact party/vehicle
pricing continuity, contracted cost and regional coverage still require tests.
[Welcome](https://partner.welcomepickups.com/el/travel-api/),
[Kiwitaxi](https://kiwitaxi.com/en/partner/webmaster/instructions/affiliate_links/).

**T2 — Booking.com cars.** Demand documents search/look/redirect with returned
booking URLs. Reuse partner access only if it includes cars and the selected
vehicle, driver, depots and terms survive handoff.
[Guide](https://developers.booking.com/demand/docs/cars/3.2/cars-quick-guide).

**T3 — Uber.** Official deeplinks carry pickup/drop-off context. Use for
on-demand handoff, without claiming a route estimate is an Uber fare or booking.
[Deeplinks](https://developer.uber.com/docs/riders/ride-requests/tutorials/deep-links/introduction).

**C1 — Google Places/Routes.** Places provides identity, website, hours and
price context; Routes supports itinerary feasibility. Neither is general hotel
rate, table-availability or ticket inventory. Transit fares are estimates and
returned only when all steps can be priced. Retain existing paid-use controls.
[Fields](https://developers.google.com/maps/documentation/places/web-service/data-fields),
[Routes](https://developers.google.com/maps/documentation/routes),
[transit](https://developers.google.com/maps/documentation/routes/transit-route).

**C2 — Official operator GTFS.** A schedule/realtime/fare format, not a single
inventory provider or reserved-seat API. Evaluate publisher, coverage period,
rights and freshness per feed.
[GTFS](https://gtfs.org/), [fares](https://gtfs.org/getting-started/features/fares/).

**C3 — Open-Meteo.** Context only. The hosted free service is non-commercial;
commercial use requires the appropriate plan. Service access and data
attribution licenses are separate.
[Pricing](https://open-meteo.com/en/pricing).

## Evaluated/deferred catalog

| Candidate or assumption | Decision now | Evidence to reopen |
| --- | --- | --- |
| LiteAPI discovery is unconditionally free | Rejected; ratio/endpoint charges apply | Account-specific permitted usage and sustainable cost |
| Tiqets requires full commercial booking integration | Superseded by Essential documentation | Verify actual affiliate token/tier |
| Skyscanner/Aviasales/GetYourGuide immediately available | Deferred; audience gates | Existing entitlement or written exception |
| Expedia Redirect open to new applicants | Deferred; paused | Vendor reopens or existing entitlement |
| Duffel/Amadeus fare implies airline-direct same-price checkout | Rejected | Documented and tested exact handoff |
| LiteAPI rail/coach/ferry | Rejected; no verified capability | Published capability and live evaluation |
| Unofficial scraped mirrors | Rejected under mainstream policy | Accountable, documented licensed replacement |
| Same name means same product | Rejected | Exact identity and material terms match |
| Multiple aggregator brands mean independent comparisons | Rejected | Deduplicated seller/upstream identities |
| Places/event range is an exact quote | Rejected | Exact dated party total and mandatory fees |
| Trainline, Direct Ferries, more OTAs | Not shortlisted; avoid integration sprawl | Specific remaining coverage gap |

## Next evaluation / partner-request package

Priority: LiteAPI entitlement and hotel offer handoff; Tiqets Essential;
existing Viator tier; Booking.com eligibility; Omio referral terms. Flight
Whitelabel enablement is an account prerequisite, not permission to transact.

Questions prepared for account checks or an explicitly authorized enquiry:

1. Is itinerary-building search and cross-source comparison permitted for an
   India-based personal/early-stage product? Which market/point-of-sale applies?
2. Which production tiers/endpoints are enabled? What are minimum volume,
   request/ratio charges, quotas and certification requirements?
3. Can an exact offer/variant/date/party redirect to hosted checkout? Which
   fields survive, and who owns merchant, support and refund responsibilities?
4. How are expiry, mandatory/local charges, FX and cancellation represented?
   Does recheck mutate inventory or create a session?
5. What retention, derived-comparison, attribution, image and deletion rules apply?
6. Which sanctioned fixtures/read-only live examples may we use, and do hosted
   completions count toward look-to-book requirements?

No partner messages were sent. Credentials belong in secret configuration,
never documents or source control.

### Proving sample and release gate

Use synthetic travelers and fixed future dates: India domestic, India–Europe,
India–Japan; adults/children with explicit ages; multi-room stays; return and
multi-city flights; required bags; refundable/non-refundable rates; admission
versus guided tour; expired quote; unavailable slot; and missing route coverage.
One successful route never establishes country-wide coverage.

Record comparable seller count, complete-price coverage, latency, request/cost
totals, source/freshness, failure behavior and handoff field continuity. Preserve
sanitized fixtures only where terms allow. Authenticated connectivity, live
price accuracy and handoff fidelity remain **not tested** until this evaluation
runs under approved access and cost controls.
