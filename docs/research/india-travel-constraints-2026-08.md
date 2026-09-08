# India-Origin Travel Constraints Register

**Verified:** 2026-08-24
**Scope:** Hard and weighted constraints that materially change India-domestic or
India-outbound itineraries.

This is a research register, not a live rules engine. Every operational rule must
be re-verified against its official source near the travel date.

## Decision classes

- **Mandatory:** missing compliance makes the itinerary invalid or unsafe.
- **Conditional mandatory:** becomes mandatory for a region, route, traveler, or
  date window.
- **Weighted:** affects ranking, pace, or risk but does not normally block a plan.
- **Promote to mandatory:** a weighted condition becomes a blocker when an
  authority announces closure, suspension, or a severe warning.

## Domestic constraints

| ID | Rule | Mode | Stability | Official source | Planner action |
| --- | --- | --- | --- | --- | --- |
| `IN-LADAKH-ACCLIMATISE` | Visitors arriving in Leh should acclimatise for at least 48 hours before traveling to higher-altitude areas. | Conditional mandatory | Stable health guidance; re-check annually | [Leh District Tourist Management System](https://www.lahdclehpermit.in/) | Reserve the first two days for low-exertion Leh activity; never send a new arrival directly to a higher pass or remote valley. |
| `IN-LADAKH-FEES` | Leh publishes environmental, Red Cross, and wildlife fee workflows through its tourist portal. | Conditional mandatory | Process and fee are volatile | [Leh District Tourist Management System](https://www.lahdclehpermit.in/) | Verify the current portal, route permissions, fees, and required documents before booking restricted legs. |
| `IN-AR-ILP` | Arunachal Pradesh uses an Inner Line Permit entry process. | Mandatory for affected travelers | Legal requirement stable; process volatile | [Arunachal Pradesh eILP](https://eilp.arunachal.gov.in/) | Add permit lead time and prevent a Tawang/Arunachal plan from appearing ready without verification. |
| `IN-LD-ENTRY-PERMIT` | Entry to Lakshadweep is restricted and requires an administration-issued permit. | Mandatory | Requirement stable; procedure volatile | [UT Administration of Lakshadweep](https://lakshadweep.gov.in/), [ePermit portal](https://epermit.utl.gov.in/) | Add permit status as a booking gate and preserve buffers around constrained air/sea transfers. |
| `IN-UK-YATRA-REG` | Char Dham and Hemkund Sahib travelers and vehicles must be registered; pilgrims are verified at destinations. | Mandatory in season | Seasonal process | [Uttarakhand Tourist Care](https://registrationandtouristcare.uk.gov.in/) | Include registration letter/QR, shrine dates, verification, queue tokens, and current weather checks. |
| `IN-JK-AMARNATH` | Annual Amarnath access, medical certification, transport, and route notices are season-specific. | Mandatory in season | Highly volatile | [Shri Amarnathji Shrine Board](https://jksasb.nic.in/) | Use the current season's registration, compulsory health certificate, route, and mode notices; do not reuse last year's assumptions. |
| `IN-WEATHER-IMD` | IMD publishes national and district warnings, nowcasts, monsoon, and rainfall information. | Weighted, promoted on severe warning or closure | Intraday | [India Meteorological Department](https://mausam.imd.gov.in/) | Re-rank or replan exposed mountain, coast, island, and monsoon routes. Block legs under authoritative closure or unsafe warnings. |

Andaman ferry schedules and AAI airport/traffic data are high-value official
targets, but their contents were not reliably extracted in this pass. Do not turn
their URLs into hard facts until ingestion succeeds.

## Outbound constraints

| ID | Rule | Mode | Stability | Official source | Planner action |
| --- | --- | --- | --- | --- | --- |
| `OUT-PASSPORT` | International travel requires a valid passport and destination-specific document validity. | Mandatory | Passport platform stable; notices volatile | [Passport Seva](https://www.passportindia.gov.in/) | Establish passport nationality and validity before presenting an outbound plan as bookable. |
| `OUT-MEA-ADVISORY` | MEA publishes country and region advisories for Indian nationals. | Weighted, promoted by advisory severity | Volatile | [MEA travel advisories](https://www.mea.gov.in/travel-advisories.htm) | Check before recommendation and again before travel; reroute or stop when official advice warrants it. |
| `OUT-SG-VISA` | Indian travel documents require a Singapore entry visa; VFTF is conditional. The SG Arrival Card is not a visa. | Mandatory | Volatile | [Singapore ICA](https://www.ica.gov.sg/enter-transit-depart/entering-singapore/visa_requirements) | Use the ordinary visa path unless the traveler demonstrably meets current transit conditions. |
| `OUT-UAE-ENTRY` | UAE visa services are exposed through the official ICP channel; eligibility varies by traveler and status. | Mandatory | Volatile | [UAE ICP Smart Services](https://smartservices.icp.gov.ae/echannels/web/client/default.html#/login) | Verify current eligibility and channel; never infer visa-on-arrival from destination popularity. |
| `OUT-SCHENGEN` | Schengen short stays are generally limited to 90 days in a rolling 180-day period under common rules. | Mandatory | Legal framework stable; appointments and procedures volatile | [European Commission](https://home-affairs.ec.europa.eu/policies/schengen-borders-and-visa/visa-policy_en) | Check visa requirement, appointment lead time, main destination, insurance, documents, and cumulative stay. |
| `OUT-JAPAN-VISA` | Japan short-stay visas are issued before arrival; general processing guidance is not a guarantee. | Mandatory when visa-required | Volatile process | [Japan MOFA](https://www.mofa.go.jp/j_info/visit/visa/index.html) | Build preparation lead time and direct the traveler to the mission with jurisdiction over residence. |
| `OUT-AU-VISITOR` | Australia's visitor visa has separate tourist and sponsored-family streams; published processing times are guides. | Mandatory | Volatile | [Australian Home Affairs](https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/visitor-600) | Select the correct purpose and avoid promising cost, duration, or decision time from cached data. |
| `OUT-SA-NUSUK` | Nusuk supports Hajj, Umrah, and Rawdah permit and booking workflows; health and seasonal requirements apply. | Mandatory for relevant pilgrimage | Seasonal and volatile | [Nusuk](https://www.nusuk.sa/), [Saudi Ministry of Hajj and Umrah](https://haj.gov.sa/) | Treat pilgrimage as a regulated workflow with approved providers, permits, health rules, and ritual dates. |
| `OUT-SL-ETA` | Sri Lanka's ETA/eVisa channel has changed operationally in recent years. | Mandatory | Highly volatile | [Sri Lanka immigration ETA](https://eta.gov.lk/), [Sri Lanka Tourism Development Authority](https://www.sltda.gov.lk/) | Resolve the current official application channel immediately before advising the traveler. |

## Constraint object shape

When these rules become executable data, keep evidence and refresh behavior beside
the rule:

```json
{
  "constraint_id": "IN-LD-ENTRY-PERMIT",
  "constraint_type": "permit",
  "jurisdiction": "IN-LD",
  "rule_mode": "mandatory",
  "rule_text": "Visitors require an entry permit for Lakshadweep",
  "volatility": "stable_requirement_volatile_process",
  "evidence": [
    {
      "url": "https://lakshadweep.gov.in/",
      "publisher": "UT Administration of Lakshadweep",
      "captured_at": "2026-08-24",
      "confidence": 0.95,
      "extraction_status": "parsed"
    }
  ],
  "refresh_policy": {
    "reverify_days": 30,
    "on_stale_action": "block_claim_and_link_to_source"
  }
}
```

Minimum executable fields are `constraint_id`, `rule_mode`, `rule_text`,
`volatility`, evidence URL and capture date, confidence, and re-verification days.

## Planner policy

1. Never silently turn a static research note into a current eligibility claim.
2. A mandatory rule with stale evidence blocks the claim, not necessarily the
   destination: say what must be verified and link the official source.
3. Weather, connectivity, price, appointment availability, and seasonal access
   need date-specific checks.
4. Health constraints should create time and pacing changes, not merely a warning
   paragraph after an impossible itinerary has already been generated.
5. Permit and registration steps belong before non-refundable booking handoffs.
6. Keep measured demand separate from eligibility. A popular destination can
   still be temporarily inaccessible to a particular traveler.

## Refresh schedule

- **At request time:** destination entry eligibility, MEA advisories, closures,
  severe weather, air/ferry operation, and pilgrimage notices.
- **Every 30 days:** visa/ETA portals, permit workflows, fees, health forms, and
  registration systems.
- **Every 180 days:** stable legal framework and official source ownership.
- **Every season:** Char Dham, Amarnath, Hajj, monsoon, high-altitude, and island
  operating assumptions.