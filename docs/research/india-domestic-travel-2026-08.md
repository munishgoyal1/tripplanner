# India Domestic Travel Corpus Priors

**Evidence cut-off:** 2026-08-24
**Purpose:** Define defensible destination and scenario priors for India-origin,
India-domestic trip-planning validation.

## Method and evidence labels

This register separates what public sources actually measure from product
synthesis:

- **Measured:** a number or rule directly present in an official source.
- **Supported inference:** an itinerary shape inferred from measured demand,
  geography, transport, or an official operational requirement.
- **Catalog prior:** a deliberate validation weight. It controls test ordering;
  it is not a claim about market share.

Domestic tourist visits (DTVs) are visits recorded by states and districts, not
unique leisure travelers. They may include repeated visits, pilgrimage, visits to
friends and relatives, and other purposes. A high DTV count therefore supports
including a destination family, but does not by itself prove party type, trip
duration, or leisure intent.

## Official demand anchors

| Finding | Evidence | Confidence | Catalog consequence |
| --- | --- | --- | --- |
| Andhra Pradesh recorded 237,051,508 DTVs in 2019, 70,828,590 in 2020, and 93,277,569 in 2021. | [Data.gov.in state/UT visualization](https://visualize.data.gov.in/?inst=be45f80d-344b-4a5f-a7df-400df5297dba) | High, measured | Give Tirupati and South temple-family travel high coverage. Do not interpret the state total as Tirupati-only demand. |
| Varanasi recorded 101,647,159 DTVs in 2023, up from 71,612,127 in 2022. | [Data.gov.in Uttar Pradesh district visualization](https://visualize.data.gov.in/?inst=f47a4827-9faa-43f2-9e09-acb0cab24997) | High, measured | Varanasi and East-UP spiritual circuits belong in the first domestic scenarios. |
| Agra recorded 11,138,316 DTVs and 970,901 foreign tourist visits in 2023. | [Data.gov.in Uttar Pradesh district visualization](https://visualize.data.gov.in/?inst=f47a4827-9faa-43f2-9e09-acb0cab24997) | High, measured | Preserve Agra both as a short destination and as a Golden Triangle anchor. |
| Bihar recorded 33,990,038 DTVs in 2019. | [Data.gov.in state/UT visualization](https://visualize.data.gov.in/?inst=be45f80d-344b-4a5f-a7df-400df5297dba) | High for the state count; medium for circuit allocation | Add a distinct Bodh Gaya-Nalanda-Rajgir family, while labeling its shape as inference. |
| Delhi recorded 36,467,598 DTVs in 2019. | [Data.gov.in state/UT visualization](https://visualize.data.gov.in/?inst=be45f80d-344b-4a5f-a7df-400df5297dba) | High, measured | Include Delhi city breaks and Delhi as the gateway for Golden Triangle and North India circuits. |
| Assam recorded 5,447,805 DTVs in 2019. | [Data.gov.in state/UT visualization](https://visualize.data.gov.in/?inst=be45f80d-344b-4a5f-a7df-400df5297dba) | High, measured | Keep Assam and Northeast extensions despite lower volume because their routing and weather behavior is distinct. |
| India had 6,592,801 km of roads as of 31 March 2022; rural roads were 69.92% of the network. | [MoRTH Basic Road Statistics 2020-21 and 2021-22](http://morth.gov.in/backend/documents/uploaded/1781850176_EDsilQvsKL.pdf) | High, measured | Model road-linked circuits and realistic transfer days rather than only fly-in city stays. |

The Ministry of Tourism's [market research and statistics
hub](https://tourism.gov.in/market-research-and-statistics) and the
[state/UT DTV resource](https://www.data.gov.in/resource/stateuts-wise-domestic-tourist-visits-dtvs-and-foreign-tourist-visits-ftvs-2019-2021)
are canonical discovery points. Newer editions should replace these figures when
their tables can be reliably extracted.

## Weighted destination families

The tiers below are corpus priorities, not market-share estimates. Within a tier,
ordering is not a factual ranking.

### Tier A: mainstream and repeated first

| Destination family | Suggested durations | High-value audiences | Why it belongs here |
| --- | --- | --- | --- |
| Varanasi, Ayodhya, Prayagraj and East UP | 2, 3, 4, 5, 6 days | Multi-generational family, senior-inclusive family, couple | Very high measured district demand; short pilgrimages and combined spiritual circuits need different pacing. |
| Delhi-Agra-Jaipur Golden Triangle | 4, 5, 6, 7 days | Family, couple, first-time friends | Agra and Delhi have measured demand; the multi-city shape exercises transfer and attraction trade-offs. |
| Goa | 3, 4, 5, 6 days | Couple, friends, family | Established leisure archetype retained as a catalog prior; party-specific expectations differ materially. |
| Kashmir | 5, 6, 7, 8 days | Couple, family | Distinct seasonal, road, and weather planning behavior. Demand rank is a catalog prior pending newer extractable official tables. |
| Kerala | 5, 6, 7, 8 days | Couple, family, multi-generational family | Multi-stop coast-backwater-hill itineraries test transfer realism and pace. |
| Rajasthan circuits | 5, 6, 7, 8, 9 days | Family, couple, friends | Multi-city heritage circuit with large distance and pacing choices. |
| Himachal Pradesh | 4, 5, 6, 7, 8 days | Couple, friends, family | Common hill-trip archetype with road-time and seasonal constraints. |
| Tirupati with optional Chennai | 2, 3, 4 days | Family, multi-generational family | High Andhra Pradesh DTV supports strong temple-family coverage without attributing all state demand to one site. |

### Tier B: important breadth and distinct planning shapes

| Destination family | Suggested durations | High-value audiences | Distinct behavior |
| --- | --- | --- | --- |
| Ladakh | 6, 7, 8, 9, 10 days | Couple, friends, family with older children | Mandatory acclimatisation buffer and high-altitude route sequencing. |
| Uttarakhand Char Dham and Haridwar-Rishikesh | 4, 6, 8, 10, 12 days | Senior-inclusive family, pilgrimage group | Registration, verification, weather, health, and route constraints. |
| Bodh Gaya-Nalanda-Rajgir | 3, 4, 5 days | Family, seniors, culture-focused couple | Explicit Bihar religious-heritage circuit, supported at state level. |
| Amritsar | 2, 3, 4 days | Family, couple, friends | Compact pilgrimage, food, and history city break. |
| Sikkim and Darjeeling | 5, 6, 7, 8 days | Couple, family | Mountain permits, weather sensitivity, and gateway transfers. |
| Meghalaya and Assam | 5, 6, 7, 8 days | Friends, couple, family | Assam gateway plus weather-sensitive Northeast road circuit. |
| Arunachal and Tawang | 7, 8, 9, 10 days | Friends, couple, experienced family | Inner Line Permit and long mountain transfers. |
| Andaman | 5, 6, 7 days | Couple, family | Flight-ferry coordination and weather-sensitive island transfers. |
| Lakshadweep | 5, 6, 7 days | Couple, family | Entry permit and constrained island logistics. |

### Tier C: deliberate regional and behavioral coverage

Hyderabad, Bengaluru-Mysuru-Coorg, Mumbai, Kolkata-Sundarbans, Odisha temple and
coast, Gujarat heritage and wildlife, Madhya Pradesh heritage and wildlife, and
national-park-focused trips belong in the long-run catalog. Their exact relative
weights remain product priors until stronger comparable destination-level evidence
is ingested.

## Scenario-shape rules

These are supported inferences for validation generation, not measured traveler
statistics:

1. A duration range is destination-specific guidance, never a global 3-7 day cap.
2. Short city and pilgrimage breaks should appear before implausibly long stays,
   while long circuits, islands, and remote mountains should receive enough days
   for transfers and recovery.
3. Family is not one audience. Include young-child, multi-generational, and
   senior-inclusive variants where pace, rooming, transport, and accessibility
   materially change the answer.
4. Couple, friends, solo, pilgrimage group, and interest-led travel should be
   assigned only where they create a realistic itinerary difference.
5. Origins are itinerary-shaping hints, not demand claims. Use gateways such as
   Delhi, Mumbai, Bengaluru, Chennai, Kochi, Kolkata, Hyderabad, Guwahati, and
   Srinagar when they materially change transfer logic.
6. Prefer circuits travelers can execute. Avoid mechanically crossing every
   destination with every party, duration, and emphasis.

## Known evidence gaps

- Comparable recent destination-level DTV tables across all states were not
  machine-extractable in this research pass.
- Public official data did not directly establish party composition, stay length,
  origin city, or purpose for most destinations.
- AAI and DGCA traffic publications should later be ingested to improve gateway
  and direct-connectivity priors.
- Accommodation searches, package searches, and booking conversions could improve
  duration and audience priors, but must be labeled as commercial behavioral data
  rather than official tourism counts.

## Refresh policy

- Re-check Ministry of Tourism and data.gov.in annual releases every 180 days.
- Re-check seasonal registrations, permits, weather, and closures separately under
  the constraints register; they must not be inferred from this demand document.
- Revise weights when newer comparable evidence changes destination ordering.
- Keep prior revisions in Git history rather than presenting stale numbers as
  current facts.