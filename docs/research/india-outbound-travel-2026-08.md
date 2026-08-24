# India Outbound Travel Corpus Priors

**Evidence cut-off:** 2026-08-24
**Purpose:** Define a comprehensive, reviewable catalog of trips originating in
India and traveling abroad.

## Method and evidence labels

- **Measured:** directly reported by an official tourism or immigration source.
- **Official constraint:** a rule or workflow published by the responsible
  government authority.
- **Supported inference:** a plausible trip shape derived from distance,
  connectivity, destination structure, or constraints.
- **Catalog prior:** a synthetic validation weight, not claimed market share.

No single official source found in this pass provided a complete, current ranking
of every destination used by Indian travelers together with duration, party,
origin, and purpose. The catalog therefore uses official destination evidence and
entry complexity as anchors, then makes itinerary-shape assumptions explicit.

## Measured and official anchors

| Finding | Evidence | Confidence | Catalog consequence |
| --- | --- | --- | --- |
| Dubai welcomed 19.59 million international overnight visitors in 2025, up 5% from 18.72 million in 2024. | [Dubai DET 2025 performance report](https://www.dubaidet.gov.ae/en/research-and-insights/tourism-performance-report-december-2025), published 2026-01-07 | High, measured for total Dubai demand; not India-specific in the extracted page | Keep UAE at the front of short-haul scenarios, while avoiding an unsupported Indian market-share claim. |
| Sri Lanka recorded 2,362,521 tourist arrivals in 2025, up 15.1% from 2,053,465 in 2024. | [Sri Lanka Tourism Development Authority](https://www.sltda.gov.lk/en/monthly-tourist-arrivals-reports-2025) | High, measured total arrivals | Give Sri Lanka durable regional coverage and preserve current source-country files for later India-specific ingestion. |
| Singapore lists India among travel-document countries requiring an entry visa and among nationalities potentially eligible for the Visa-Free Transit Facility. The SG Arrival Card is not a visa. | [Singapore ICA visa requirements](https://www.ica.gov.sg/enter-transit-depart/entering-singapore/visa_requirements), updated 2026-06-25 | High, official constraint | Generate ordinary tourist-visa scenarios; treat transit eligibility as conditional, never as a blanket visa waiver. |
| All 29 Schengen countries apply common short-stay rules, generally up to 90 days in any 180-day period. | [European Commission visa policy](https://home-affairs.ec.europa.eu/policies/schengen-borders-and-visa/visa-policy_en) | High, official constraint | Europe scenarios need visa lead-time and multi-country routing awareness. |
| Japan defines short-term stay as up to 90 days and says visa processing is approximately one week when requirements are met, with longer cases possible. | [Japan Ministry of Foreign Affairs](https://www.mofa.go.jp/j_info/visit/visa/index.html), updated 2026-06-24 | High, official general process | Add visa-preparation expectations without promising a decision date. |
| Australia's subclass 600 tourist stream covers holidays and visiting family or friends; the official processing-time tool is only a guide. | [Australian Department of Home Affairs](https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/visitor-600) | High, official constraint | Preserve separate leisure and VFR scenarios and avoid hardcoded processing times or fees. |
| Nusuk is the official platform supervised by Saudi Arabia's Ministry of Hajj and Umrah and exposes permit workflows for Hajj, Umrah, and Rawdah. | [Nusuk](https://www.nusuk.sa/) | High, official constraint | Saudi pilgrimage is a distinct journey family, not a generic city break. |
| MEA maintains destination advisories for Indian nationals. | [Ministry of External Affairs travel advisories](https://www.mea.gov.in/travel-advisories.htm), updated 2026-06-02 | High, official operational source | Every outbound plan should prompt current advisory and entry-rule verification. |

## Weighted catalog

Weights total 100 and control scenario ordering only. They deliberately balance
mainstream demand with planning complexity and behavioral breadth.

| Destination or circuit | Weight | Suggested duration | Priority audiences | Evidence posture |
| --- | ---: | --- | --- | --- |
| UAE: Dubai with Abu Dhabi option | 10 | 4, 5, 6 days | Family, couple, friends | Official total-volume anchor plus short-haul catalog prior; high confidence in inclusion, medium in weight. |
| Thailand: Bangkok with Phuket/Krabi/Pattaya options | 9 | 5, 6, 7, 8 days | Friends, couple, family | Mainstream catalog prior; visa and entry rules require re-verification. |
| Singapore, optionally with Malaysia | 7 | 4, 5, 6, 7 days | Family, couple | Official Indian visa constraint; duration and weight are supported inference. |
| Bali and Indonesia | 7 | 5, 6, 7, 8 days | Couple, honeymoon, friends | Strong leisure archetype prior; official statistics extraction was blocked. |
| Vietnam | 7 | 5, 6, 7, 8, 9 days | Couple, friends, value-focused family | Growth/value prior pending stronger official India-specific evidence. |
| Maldives | 6 | 4, 5, 6 days | Couple, honeymoon, family | Distinct resort-transfer and budget archetype; official statistics page blocked extraction. |
| Malaysia | 5 | 5, 6, 7 days | Family, friends | Family/city circuit prior with optional Singapore combination. |
| Sri Lanka | 5 | 5, 6, 7, 8 days | Family, couple, culture-focused friends | Official rebound evidence; high confidence in inclusion. |
| Saudi Arabia: Umrah/Hajj | 5 | 7, 9, 12, 16 days | Pilgrimage group, multi-generational family | Official permit platform; duration differs by ritual and season. |
| Nepal | 4 | 4, 5, 6, 7 days | Family, pilgrims, adventure friends | High-relevance regional prior; official page extraction incomplete. |
| Bhutan | 3 | 6, 7, 8 days | Couple, family, culture-focused friends | Distinct regulated-tourism and overland/air gateway shape. |
| Mauritius | 3 | 6, 7, 8 days | Couple, honeymoon, family | Resort-island alternative; weight is a catalog prior. |
| Turkey | 4 | 7, 8, 9 days | Couple, family, history-focused friends | Mid-haul multi-city and entry-planning complexity. |
| Schengen Europe circuits | 7 | 9, 11, 14 days | Family, couple, premium group | Official common visa rules; high planning complexity. |
| United Kingdom | 4 | 7, 10, 14 days | VFR family, leisure family, couple | Official visa workflow should be checked at planning time. |
| United States | 4 | 10, 14, 18 days | VFR family, premium leisure family | Long-haul VFR and visa-interview complexity; canonical source extraction was blocked. |
| Australia and New Zealand | 3 | 10, 12, 14, 18 days | VFR family, couple, nature-focused family | Official Australian visitor framework; New Zealand is lower-weight extension coverage. |
| Japan | 4 | 7, 8, 10 days | Couple, family, interest-led friends | Official visa process and strong seasonal itinerary shape. |
| South Korea | 2 | 6, 7, 9 days | Couple, friends, interest-led traveler | Distinct culture-led scenario; lower-weight prior. |
| Hong Kong and Macau | 2 | 4, 5, 6 days | Family, couple, friends | Compact urban/theme/shopping circuit; entry rules need re-verification. |
| Emerging value and niche set | 5 | 5-10 days by destination | Couple, friends, experienced family | Georgia, Azerbaijan, Kazakhstan, Seychelles, Egypt, Cambodia-Laos, and selected Eastern Europe; intentionally lower confidence and later ordering. |

## Scenario families the catalog must preserve

1. **Short-haul first international trip:** documentation clarity, direct routing,
   simple transfers, and a moderate pace matter more than collecting countries.
2. **Honeymoon and resort:** room/resort quality, privacy, transfers, and budget
   allocation materially alter Maldives, Bali, Mauritius, and Seychelles plans.
3. **Family urban and theme-park:** Singapore, UAE, Malaysia, and Hong Kong need
   child-friendly pacing and age-aware attraction choices.
4. **Friends and nightlife:** Thailand, Bali, Vietnam, and UAE should not reuse the
   family itinerary with only a changed label.
5. **Pilgrimage:** Saudi, Nepal, and Sri Lanka religious circuits need ritual,
   registration, health, accessibility, and group-movement constraints.
6. **VFR plus leisure:** UK, USA, Canada, and Australia require a host-city anchor,
   flexible family time, and selective tourism rather than a pure package circuit.
7. **Premium long-haul circuit:** Schengen Europe, Japan, Australia-New Zealand,
   Turkey, and North America need longer durations and explicit transfer costs.
8. **Emerging/value explorer:** lower-weight scenarios should test uncertainty and
   rule verification rather than assert that emerging destinations are mainstream.

## Common Indian departure gateways

Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kochi, and Kolkata are useful
catalog origins. Lucknow and other North Indian gateways matter for pilgrimage;
Ahmedabad, Pune, and regional airports can be introduced where a real route or
connection changes the plan. These are routing priors, not measured origin shares
from this research pass.

## Rules for generation

- Do not promise visa eligibility, approval, fees, processing time, or visa-free
  entry from static catalog data.
- Name the passport assumption and tell the planner to re-check the destination's
  official immigration source before booking.
- Treat airline connectivity as date-dependent. A gateway hint does not prove a
  nonstop flight exists on the requested dates.
- Use destination-aware durations. A four-day UAE trip and a fourteen-day Europe
  circuit can both be mainstream.
- Keep country combinations geographically and operationally plausible.
- Do not multiply every destination by every audience. Generate variants only when
  party, purpose, duration, or constraints materially change the itinerary.

## Evidence gaps and refresh policy

Official India-specific arrival tables were not extractable for every destination.
Maldives, Nepal, Bhutan, Indonesia, Thailand, and some U.S. sources blocked or
failed automated extraction. Those destinations remain because comprehensive
validation needs their distinct trip shapes, but their relative weights are
explicit product priors.

- Re-check destination tourism statistics every 180 days.
- Re-check visa, ETA, passport, health, and advisory sources every 30 days and at
  trip-planning time.
- Re-check seasonal pilgrimage rules for every operating season.
- Lower or raise weights only with comparable evidence, observed owner usage, or
  validation-failure coverage. Document which layer caused the change.