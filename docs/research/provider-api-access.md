# Provider API Access — Cost and Prerequisites

Verified 2026-08-10 against vendor documentation and partner pages. Prices move
and partner terms change, so re-verify before acting on anything here.

**Headline: no rail, coach or ferry provider publishes pricing.** Every one
requires a commercial conversation, so this category cannot be costed from
public information. That is the finding, not a gap in the research.

## Ground transport — the uncovered categories

| Provider | Covers | Access | Cost | Prerequisites |
| --- | --- | --- | --- | --- |
| Distribusion | Train, coach, tram, ferry | Contact / request demo. No self-serve | Not published; commercials negotiated per partner | Company entity, demo→production QA sign-off, settlement and invoicing relationship |
| Trainline Partner Solutions | Rail (Europe-wide), "Global API" | "Get in touch". No self-serve | Not published | B2B partner agreement |
| Ferryhopper | Ferry — 360 operators, 63 countries, 4,000+ routes | Partner portal, no public API docs | Not published | Partner application |
| Omio | Rail, coach | Partner-gated, no public developer docs | Not published | Partner approval |
| Direct Ferries | Ferry | No accessible API page at time of check | Unknown | Unknown |

**Distribusion is the recommendation.** It is the only source covering all three
missing categories under one contract and one integration, it exposes a demo
environment with API-key auth and a documented QA path to production, and its
own retailer list is the credibility check: Google, Booking.com, Expedia, Kayak,
Trainline, Rome2rio, Busbud, GetYourGuide and Tiqets all buy ground transport
through it. One negotiation instead of four also fits the "two or three sources,
not a sprawling matrix" rule in [PRODUCT.md](../PRODUCT.md).

## Zero-cost option available today

**Travelpayouts** — 100% free, no sign-up fee, no ongoing cost. Paid by the
brands, so the partner keeps the full commission. Carries a Trains & Buses
category plus Booking.com, Viator and GetYourGuide. Prerequisite is a public
channel (website or blog).

This yields **booking deep links, not live fares**, so rail stays unpriced in the
itinerary. That matches the product rule already in force: booking is a verified
handoff, and an unpriced hop shows time and day impact with no number.

## Already integrated, with published per-request pricing

LiteAPI is the only provider in use that publishes per-request costs:

- Places lookup and place detail — $0.01 per request
- Price index, city or hotels — $0.05 per request, 10 requests/minute
- Hotel highlights — 10 requests/minute

LiteAPI flights are real (`POST /flights/rates`, `POST /flights/verify`) but sit
behind a "Getting Access to Flights" enablement step, and the flexible-date
matrix requires contacting their support. Confirm the account has flights
enabled before relying on that path. LiteAPI publishes **no** rail, coach or
ferry API; see [ENGINEERING_LEARNINGS.md](../ENGINEERING_LEARNINGS.md) for the
unverified adapter that was removed because of it.

## Suggested sequence

1. **Free, now** — join Travelpayouts and add rail, coach and ferry booking deep
   links. Restores the handoff for legs like Lisbon→Porto at no cost and without
   claiming a live fare.
2. **Then** — one enquiry to Distribusion asking specifically about minimum
   volume commitment and whether a pre-revenue product can reach the demo
   environment. That single answer decides whether real rail pricing is
   reachable now or is a post-traction item.

Hold off on Trainline, Omio and Direct Ferries: each is strictly narrower than
Distribusion and would cost a separate integration and contract.
