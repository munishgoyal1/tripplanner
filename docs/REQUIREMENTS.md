# Tripplanner Requirements

## Document control

| Field | Value |
| --- | --- |
| Baseline date | 2026-07-28 |
| Baseline commit | `f4f4392` |
| Status | Current implemented baseline; roadmap items require owner approval |
| Owner | Munish Goyal |
| Product | tripplanner |

This document is the concise, current product baseline. It answers **what the
product can do now**, what behavior must be preserved, and which directions are
proposed next. It replaces the need to reconstruct current scope from the
chronological `docs/reference/history/requirements-log.txt` log.

Source-of-truth boundaries:

- `docs/README.md`: documentation index, ownership, and structure policy.
- `docs/REQUIREMENTS.md`: current capabilities, gaps, and roadmap.
- `docs/PRODUCT.md`: product intent, interaction rules, and design taste.
- `docs/CODEMAP.md`: implementation ownership, contracts, and commands.
- `docs/reference/history/requirements-log.txt`: chronological decision history; old entries may be obsolete.
- `docs/ENGINEERING_LEARNINGS.md`: durable lessons from observed failures.
- `docs/roadmap/FUTURE_FEATURES.md`: consolidated future feature candidates.
- `docs/feature-briefs/NEXT_INCREMENT.md`: editable scope for the next milestone.

When a shipped feature changes the capability baseline, update this document in
the same commit. A roadmap entry is not implementation approval by itself.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| Implemented | Available in the current repository and supported by tests or runbooks. |
| Partially implemented | A compatible foundation exists, but the user-facing workflow is not complete. |
| Guarded | Implemented, but intentionally constrained by approval, configuration, or environment. |
| Observing | Current behavior remains in place while usage evidence is gathered. |
| Proposed | Candidate work; not approved merely because it appears here. |
| Out of scope | Explicitly excluded from the current product. |

## Product contract

Tripplanner is a preference-aware AI trip planner that turns a conversation into
a concrete, editable, and exportable trip. It uses real travel and place data,
persists the plan and the user's preferences, and keeps Itinerary, Map, Details,
and Assistant behavior synchronized across web, iPhone, and Android.

The planning target is a near-final plan within 30 minutes and few clarification
rounds. "Bookable" currently means concrete choices, prices when providers return
them, itinerary details, and verified handoff material. The product does **not**
currently complete provider-side purchases or charge a payment method.

Two goals rank above every other requirement, in this order. First, produce the
most intelligent itinerary available inside the user's preferences, tastes,
budget, pace, and constraints. Second, get that same trip at the best achievable
total cost and hand the user into booking with verified, pre-filled material.
The second goal may later use consent-gated payment context, such as which cards
or loyalty programs a user holds, to compare offers before the handoff; it stores
program and card identity only, never card numbers, and never charges a payment
method. Neither goal may make the product slow: price and offer work is
background and time-boxed, and the planner always renders the plan it already has.

## Capability index

Future feature briefs should reference these stable capability IDs rather than
re-describing the whole product.

| ID | Capability | Status |
| --- | --- | --- |
| CORE-01 | Single trip-planning agent with phase-selected tools | Implemented |
| CHAT-01 | Structured minimal-input Assistant interactions | Observing |
| PLAN-01 | Preference-aware conversational trip creation | Implemented |
| PLAN-02 | Source-grounded flight, stay, place, meal, route, weather, visa, and event research | Implemented |
| PLAN-03 | Structured, chronological, hotel-anchored daily itineraries | Implemented |
| PLAN-04 | Deterministic itinerary reflow and optional planner review | Implemented |
| MEM-01 | Persistent profile, family, preference, history, and passive learning | Implemented |
| LIFE-01 | Draft, finalized, and recorded-booked trip lifecycle | Implemented |
| LIFE-02 | Saved trips, resume/switch/delete, and per-trip chat history | Implemented |
| WEB-01 | Responsive four-pane planning workspace | Implemented |
| ITIN-01 | Authoritative trip snapshot and occurrence-aware itinerary | Implemented |
| MAP-01 | Day circuits, all-days overview, exact-stop focus, and POI discovery | Implemented |
| PLACE-01 | Contextual Details and consistent Map/Details place actions | Implemented |
| MUT-01 | Add, remove, move-day, stay, and booking-state mutations | Implemented |
| EXPORT-01 | Preview, print, PDF, email, share link, and calendar exports | Implemented |
| MOBILE-01 | Native Expo client for iPhone and Android | Implemented |
| ID-01 | Guest identity plus shared web/mobile Google identity | Implemented |
| DATA-01 | Local JSON/emulator and hosted Cosmos persistence | Implemented |
| REL-01 | Stale-request protection, serialized mutations, recovery, and caching | Implemented; all runtime cache families share one owner-controlled TTL policy, with environment-wide scaling and precise provider overrides supplied through checked-in local/sandbox, canary, and production non-secret profiles plus ignored secret overlays; disposable and durable regions retain storage appropriate to their recovery contract |
| SAFE-01 | Usage limits, grounding critic, secrets, and data isolation | Implemented; paid Google Places is fail-closed behind a production-only runtime switch, owner emergency Service Usage control, observation-scale provider quotas, configurable request ceilings, shared discovery evidence, focused reviews, and one-photo enrichment defaults |
| TRUST-01 | Itinerary verification certificate and ownership-aware repair | Implemented; per-check passed/failed/unverified state, weekday and holiday closure, explicit place-fact rechecks with before/after changes and source-linked unusual-closure advisories, place-identity gate, and a rebalance that never moves a stop the traveller chose |
| OPS-01 | Reproducible setup, canary promotion, smoke, production approval, and rollback | Implemented |
| OPS-02 | Production failure email alerting and non-production error analysis | Implemented |
| OPS-03 | Owner-only Business and System Health operations dashboard | Implemented; hidden route, server-side verified-email guard, consented funnel/activity aggregates, chat/tool/provider/cache health, and explicit data-window labels |
| PUBLIC-01 | Public custom-domain MVP with traction feedback loop | Implemented; `/` public entry, `/planner` workspace, privacy-safe analytics, and regional last-known-good demo pipeline |
| FEEDBACK-01 | Lightweight repeatable trip feedback | Implemented; toolbar thumbs, optional stars/comment, append-only submissions, and trip-level sent rollup |
| QUALITY-01 | Offline scenario-fidelity and experiential-quality audit | Implemented; every audit writes an immutable dated JSON report, readable summary, compact history index, comparable-run movement, scenario/preference and budget hard gates, and six non-gating experiential dimensions; the unified harness also correlates scenario/action evidence and reports measured usage, catalog-estimated cost, cache effectiveness, request amplification, performance, and deterministic plan quality while keeping subjective evaluation optional and separately costed; generated and persisted findings require a preventive executable fix plus a focused regression test while preserving the failing evidence, genuine fixture corrections require evidence-contract validation, integrated fixes record deterministic post-fix replay, and fresh generation remains an explicit paid corpus refresh |
| DEAL-01 | Best-total-cost comparison, offer and card-benefit optimization | Implemented for persisted provider evidence; exact products compare only with complete mandatory costs and published FX, consented public benefit terms apply without card numbers, and finalized unbooked expired flight/stay quotes can be explicitly rechecked without replacing selections |
| MONEY-01 | Minimally intrusive monetization after traction | Proposed |
| BOOK-01 | Real provider-side booking and payment | Out of scope |

## 1. Planning intelligence

### CORE-01 - Single authoritative trip agent

- One LangGraph agent owns planning; removed personal-assistant agents are not
  part of the current product.
- Tool schemas are selected by conversation phase so greetings and preference
  turns do not pay the context cost of every search provider.
- Daily effort and whole-trip reserve account for grounded forecast heat and rain
  as advisory exposure only. Coherence notes name source-backed weather pressure
  and structured place/activity-provider duration mismatches without inventing
  evidence or blocking itinerary completion.
- The agent presents progress as friendly thinking, search, review, and save
  phases while keeping internal tool names and raw arguments out of the UI. The
  chat and common command bar show one overall elapsed clock, a typical 2–4 minute
  full-build expectation, and continuing-work reassurance rather than appearing stuck.
- GPT-4.1 is the measured default planning model. A slower or costlier model
  requires evidence that it improves a relevant quality failure.

### CHAT-01 - Structured minimal-input Assistant interactions

- Every new trip loads durable preferences before planning. Smart defaults are on by
  default, so the agent proceeds autonomously when the request establishes its party.
  Otherwise one bounded `request_trip_input` review collects Adults (13+), Children
  (0-12), and Trip group; saved family details only prefill these trip-specific facts.
  A traveller can opt to include other material fields in that same review when an
  answer would materially improve the trip. Every field carries a sensible prefilled
  value; known context enumerates the relevant saved preferences and past-trip signals
  already applied.
- The backend emits the validated versioned payload as an additive `input_request`
  SSE event while retaining a concise text fallback for older clients.
- Shared web/native TypeScript transport retains the event contract.
- The main web app renders all validated field kinds as compact inline chips and controls
  inside the selected lower-right Assistant conversation sheet. The visible
  workspace remains usable while the sheet is open; explicit close, Escape, and
  command-bar reopen preserve the mounted conversation. Submission and default-skip responses continue
  through the normal retry-safe chat path.
- While a web response is running, the Send control becomes Stop and aborts the
  active SSE request without presenting a failure or same-request retry. Useful
  partial text remains visibly marked as stopped and the composer recovers.
- Completed user and Assistant messages can be copied. A prior user instruction
  can be loaded into the composer, revised, and sent as a fresh corrective turn;
  existing transcript and itinerary side effects are not falsely presented as undone.
- Real SSE milestones such as preference review, flight/hotel/place research,
  routing, review, and persistence update both chat progress and the common command
  bar. New-trip completion is announced only after every trip pane reloads; existing
  itinerary changes use the refreshed authoritative mutation summary, and proposal-only
  reviews explicitly say that the itinerary remains unchanged.
- The inline chip/control surface appears when party composition is missing or the
  traveller opts into a useful review. Explicit party details preserve autonomous
  planning without another confirmation gate.
  A new hosted deployment remains pending explicit approval.

### PLAN-01 - Preference-aware planning flow

- The agent loads known preferences before the one-step new-trip kickoff. Direct
  mode uses that review and then builds without further questions; interactive
  mode may include unresolved critical facts in the same review.
- Explicit requests for a new, separate, another, or different trip start the
  new-trip kickoff even when another trip's chat is active. After the user submits
  or skips that kickoff, the graph requires `create_trip_plan`; the prior trip and
  its transcript remain separate.
- Trip dates, travelers, origin, destination, budget, pace, food, mobility, and
  lodging needs shape the plan.
- Every new trip runs an explainable duration advisor before the structured
  kickoff. Explicit user duration remains authoritative; otherwise destination
  scope, likely preference-matched places, visit/travel workload, arrival and
  departure capacity, desired free time, and major-attractions-per-day determine
  a fitting recommendation instead of a universal seven-day fallback.
- The complete recommendation and its evidence are persisted with the trip.
  Advisor-enabled plans deterministically flag accidentally sparse full days;
  transfer, partial, and explicitly intentional leisure days are handled
  separately, and legacy plans are not retroactively gated.
- Post-trip pace feedback (`too_rushed`, `just_right`, or `too_sparse`) and
  observed active minutes may tune later daily capacity. Platform-wide insight
  enters only as a versioned aggregate cohort prior that meets minimum sample
  and confidence thresholds and may adjust the evidence estimate by at most one day.
- One sticky display currency is used throughout a trip. Domestic travel defaults
  to the user's home currency; international plans may use destination currency
  or USD with a home-currency equivalent.
- A completed planning turn persists the authoritative trip and refreshes every
  dependent pane together.
- An explicit whole-trip request for a destination different from the active trip
  creates or resumes that destination-specific trip before any itinerary update.
  Prose fallback persistence may repair only a trip created in that same turn, so
  it cannot overwrite an unrelated active trip.
- A turn that creates a trip cannot finish with an empty itinerary: the graph
  requires the initial structured `update_trip_plan` call before the final
  response, and SSE tool timing cannot interfere with the terminal completion
  event that triggers the shared pane refresh.
- New-trip planning is complete-by-default: after research, the graph requires
  an enriched persistence pass with the strongest concrete hotel and a full
  best-effort itinerary. Research is batched across overnight cities and is
  followed by one full-plan persistence pass. A ten-tool-phase semantic budget
  remains binding for later turns and optional enrichment. A first planning turn
  continues past it until concrete lodging, complete journey edges, named meal
  coverage on substantial days, and positive cost evidence for an explicit trip
  budget are persisted. Weather may remain deferred enrichment.

### PLAN-02 - Grounded providers and enrichment

- Travel inventory routes through a provider-neutral capability registry. The
  active MVP registry auto-enables only configured providers with credible
  sandbox/free access; partner-gated candidates such as Kiwi, Omio,
  Travelpayouts, and Tiqets are catalogued but inactive until current approved
  API access and terms are confirmed.
- Flight, hotel, and activity searches use a cache-first provider chain with
  ordered fallback on timeout, throttling, unavailable credentials, provider
  errors, or no availability. Returned evidence includes provider, cache hit,
  checked time, expiry, and quote status.
- LiteAPI is the preferred read-only active source for date/party-specific hotel
  rates, flight rates, and selected-flight verification when configured.
  Normalized hotel results retain the searched destination as query context, not
  physical locality proof; all results retain opaque provider references, quote
  time/expiry, total provider currency, and explicit evidence.
- The stable flight and hotel tools route through separate capability contracts;
  future providers can implement either capability without changing the agent.
- Viator is the preferred read-only activity provider when configured. The stable
  activity tool returns date-filtered product discovery, operating-schedule evidence,
  ratings, duration, cancellation/confirmation metadata, and the provider's unchanged
  affiliate URL. Prices are explicitly `from` prices, not exact party totals or holds.
- Amadeus remains available only as a legacy fallback where still configured;
  new MVP work should not assume Amadeus self-service access.
- Google hotel results are property metadata only and are labeled `estimated`;
  they never establish room availability or a live rate.
- Explicit inventory refresh bypasses shared cache. MVP cache TTLs are
  configurable by capability and intentionally favor low cost over exact
  real-time behavior.
- Google Places supplies place search, ratings, reviews, photos, restaurants,
  addresses, coordinates, and opening hours. Agent discovery seeds the durable
  structured Places cache so Map and Details reuse the same paid result. Routine
  metadata omits atmosphere fields; reviews load only for exact focus, photos
  default to one per place, and owner-controlled TTL and request ceilings bound
  cold planning/view amplification.
- Google Routes supplies measured route distance/time and route optimization.
  Map circuit drawings and fallback estimates avoid unnecessary Directions calls.
- OpenRouteService is an optional free-tier fallback for coordinate-based
  driving, walking, and cycling routes. Google remains primary for place-ID or
  address routing, traffic-aware driving, transit, and waypoint optimization.
  Both the fallback source and route freshness remain visible to callers.
- `GET /providers/status` exposes non-secret configured/active readiness,
  capabilities, access classification, and notes so the owner can review MVP
  provider costs and gated candidates before enabling anything new.
- Open-Meteo supplies no-key daily forecasts and same-season archive context.
  Forecast failures fall back to the archive; total provider failure may use an
  explicitly labeled agent monthly-climate estimate. Normalized weather persists
  with the trip, drives per-day and trip-summary icons, and produces practical
  clothing, rain, umbrella, and footwear guidance.
- Tavily supplies fresh travel research, official-source-biased visa/entry
  research, and overlapping local events.
- Missing provider keys degrade to an explicit not-configured result rather than
  breaking the planning loop.

### PLAN-03 - Complete structured itinerary

- Days contain structured stops with name, type, time, duration, notes, selected
  state, and booked state.
- Ordinary days form a circuit from the applicable hotel, through concrete
  attractions and named restaurants, and back to the hotel. Genuine overnight
  flight, train, bus, or transfer days are exempt from the return-to-hotel rule.
- When origin and destination differ, the itinerary includes both inter-city
  edges: a flight or named road, bus, or train journey before destination
  check-in on arrival day, and the return journey after checkout on departure
  day. A local taxi does not satisfy either edge.
- Placeholder hotels and generic `TBD` meals do not satisfy completion gates.
- When one concrete hotel is selected, any remaining placeholder hotel anchors in
  the persisted itinerary are replaced with that hotel while retaining day timing.
- A selected hotel's explicit city, destination, or address evidence must match
  the active trip destination. A mismatch rejects the whole plan update before
  persistence rather than surfacing only as a finalization warning.
- An unambiguous one-for-one selected hotel replacement updates every matching
  itinerary stay anchor in the same persistence operation, so Itinerary and Map
  cannot continue showing the removed property.
- Substantial days require concrete restaurant research and persisted meal stops.
- Visit times must progress chronologically and leave room for stated duration
  and travel. Duplicate or backwards model-authored times are rejected before
  persistence.
- Itinerary rows make timing auditable: hotel endpoints show estimated times
  when needed; visits show departure; transfer rows show estimated arrival,
  endpoint guidance, and any free buffer or schedule conflict. A direct Drive
  between geocoded stays may estimate duration from the same coarse inter-city
  model used by Map. A known checkout anchors its estimated departure, arrival,
  and destination check-in; without a departure anchor, duration remains visible
  but clock times are not invented.
- Timed train and bus journeys expand into departure terminal, travel, and arrival
  terminal rows. Configurable rail buffers default to 45/15 minutes and bus
  buffers to 30/15 minutes. Terminal rows are inspectable operational context,
  not bookable itinerary stops, and their timing labels remain specific to the
  actual terminal type.
- Displayed durations use minutes below 60 and hours plus remaining minutes at
  60 minutes or more across visits, transfers, routes, and schedules.
- Route summaries and legs use one Walk and Taxi fallback vocabulary. Straight-line
  fallback uses Walk only through 1.5 km and Taxi for longer legs. Metro is shown
  only when route evidence establishes service; distance alone never implies that
  a city has a metro. Place rows show Google rating/review evidence
  and may show a clearly labeled estimated must-visit score, never a fabricated
  itinerary-inclusion percentage.
- Route ordering, displayed times, itinerary markers, and map circuit ordering
  are treated as one schedule contract.
- Each persisted drive is exposed as a stable map circuit with its ordered pins,
  legs, and authoritative route metrics. Selecting that drive frames only its
  circuit; transport data without a circuit identity retains full-day route
  compatibility.

### PLAN-04 - Reflow and planner review

- Direct structural changes apply immediately and return the final authoritative
  day after reflow.
- Unbooked place stops may rebalance by geographic proximity and day load;
  booked stops, hotels, flights, transport, and explicit constraints stay fixed.
- A deterministic impact gate remains quiet for routine edits and flags material
  crowding, excessive travel, empty days, or missing meals.
- A flagged result offers `Review with planner` or `Keep as is`. Planner review
  is proposal-only: it binds read-only tools, disables fallback persistence and
  passive learning, and cannot mutate until the user approves later.

## 2. Personalization and memory

### MEM-01 - Persistent user understanding

- Profile: display name, home city/country, age band, and occupation.
- Family/travel party: relationship, name, age, dietary needs, mobility needs,
  interests, and notes.
- Travel style, budget level, hotel/room preferences, transport preferences,
  food preferences, accessibility needs, interests, and dislikes.
- Past planned trips, structured postmortems, ratings, casual past-trip mentions,
  and free-form learned notes.
- An `About me` textbox extracts structured facts and merges additively without
  overwriting existing information.
- Passive learning enriches preferences from normal conversation.
- Local BM25-style recall retrieves relevant user and trip memories without an
  external API call.

## 3. Trip lifecycle, identity, and persistence

### LIFE-01 - Lifecycle semantics

- `draft`: mutable planning state.
- `finalized`: completion checks run and the plan is ready for user booking.
- `booked`: the current `execute_bookings` tool records a completion state,
  archives the trip, and exposes handoff links where available.
- No current provider adapter purchases a flight, hotel, or activity. Messages
  suggesting a real confirmation or provider transaction are legacy wording,
  not a production guarantee.
- Individual itinerary stops can independently record booked/unbooked state.

### LIFE-02 - Remembered trips and conversations

- Stable trip IDs distinguish destination/date combinations and allow same-trip
  resume without discarding prior selections.
- Users can list, switch, and resume saved trips. The saved-trip menu supports
  confirmed deletion of one checked trip, multiple checked trips, or all trips.
- The active trip is mirrored into saved trips on each authoritative save.
- Chat history is stored per trip, survives refresh, and follows trip switches.
- New-trip creation clears the active pointer without deleting saved history.

### ID-01 - Identity

- Web guests receive a persistent browser-local `web-<uuid>` identity backed by
  a server-signed guest capability in hosted environments; raw request account
  IDs are never authoritative principals.
- Google OAuth resolves to a stable `google-<sub>` identity and uses a signed,
  HttpOnly session cookie.
- Native iOS and Android use browser OAuth and adopt the same Google identity as
  web, preserving trips, chat, and preferences across devices.
- Native identity material is stored through secure platform storage.
- Guest-to-account migration proves ownership of both the source guest session
  and destination account session before moving data.

### DATA-01 - Storage modes

- Unconfigured CLI usage persists to atomic local JSON files.
- Local SPA development defaults to the persisted Cosmos DB Emulator and does
  not silently fall back to hosted data.
- Hosted canary and production use separate databases in one shared Azure Cosmos
  account. Environment data must never be cross-wired.
- Local and hosted writes have concurrency protections; Cosmos supports opt-in
  versioned reads and conditional replacement.

## 4. Web planning workspace

### WEB-01 - Responsive workspace

- Desktop is a fixed-height workspace with Itinerary, a dominant persistent Map,
  and a right dock containing independently visible Details and Assistant.
- Panes stay mounted through hide, restore, and maximize transitions so map and
  chat state survive.
- Keyboard-accessible separators resize itinerary/map, map/inspector, and
  Details/Assistant splits; sizes persist locally.
- A common command bar owns trip switching, New trip, visibility controls,
  global trip actions, one labeled Account settings trigger, and the latest
  mutation result. Account settings owns Profile and sign-in, Travel Profile,
  Analytics preferences, and Privacy and data in one right-side sheet.
- At wide desktop sizes, pane visibility controls pair semantic icons with the
  short labels Itinerary, Map, Details, and Assistant. Compact desktop widths
  retain the icons without introducing header overflow.
- New trip is a labeled, softly tinted command rather than a solid high-contrast
  block. The four pane controls remain directly available without a submenu and
  use quiet neutral active states; utility icons are visually subordinate to the
  itinerary and map. Hide and Maximize remain local pane-header actions.
- Narrow desktop uses an inspector overlay. Mobile web uses Assistant plus an
  on-demand trip-details sheet rather than compressing the desktop layout.
- Only panes scroll; the page itself remains spatially stable.

### ITIN-01 - Itinerary and trip snapshot

- One authoritative trip snapshot owns destination, dates, travelers, lifecycle,
  counts, booking progress, budget/cost, family/preference context, and constraints.
- The snapshot uses the Decision brief hierarchy: traveler context stays with trip
  identity, a trip-level narrative follows it, readiness is explicit, and
  Days/Stay/Places/Flights share one compact facts row. Weather remains visible with
  real persisted evidence or a truthful unavailable state. No generic Trip fit line
  is repeated below Budget.
- Compact day briefs expose non-hotel planned-stop count, explicit `Schedule
  duration`, a separate `Day's travel` route distance/time/mode row, confirmed
  and remaining booking counts, Travel rhythm guidance, and a Maps handoff before
  stop details. A shared backend contract gives Itinerary and Map the same
  endpoint-to-endpoint schedule and separate route-only travel subtotal. Missing
  hotel endpoint times are estimated from timed visits and known route legs and
  visibly marked as estimates.
- Compact agenda rows lead with explicit Depart/Return or Arrive/Stay timing,
  keep time, place, status, and actions densely left-aligned, place each travel
  estimate above its destination, and use explicit Confirmed or Needs booking
  actions instead of checkbox presentation.
- Place stops use day-colored markers matching map circuits: `H` for a single
  hotel, route-ordered `H1`, `H2`, and so on for distinct hotel endpoints, and
  sequential numbers for attractions and named meals.
- Flight transitions expose separate departure and arrival airport rows marked
  `A`. Persisted local flight times and durations remain authoritative. Missing
  arrival or duration fields use visibly estimated static fallbacks; departure
  airport arrival includes configurable check-in/security time, arrival airport
  handling includes configurable baggage/exit time, and destination-stay arrival
  is estimated only from airport handling plus known transfer timing.
- Rows show quiet travel distance/time from the previous mapped stop.
- Generated hotel circuit anchors have no visit duration, In trip badge, or
  single-occurrence removal. Hotel changes use authoritative stay-range actions.
  Identical departure and return hotels share one stay identity and one set of
  controls while preserving route endpoints, return-leg evidence, and exact
  focus. The return is a compact chronological endpoint after the final plan,
  without duplicate stay controls or hotel details. Different endpoint hotels
  remain separate Check out and Check in rows. A multi-city transition day
  renders checkout, the complete journey, destination check-in, remaining plans,
  and return in one spine.
- Harmless locality spelling, abbreviated property names, generic Hotel/Resort
  words, and trailing address variants share the same stay identity; genuinely
  different properties remain distinct `H1`, `H2` endpoints.
- A transfer day omitted origin stay is carried forward from the prior day's
  active hotel in both Itinerary and Map. Saved car/train/bus mode metadata is
  normalized into a clickable inter-city leg without requiring a name prefix.
- Natural drive wording also normalizes into a clickable route. Drive and Bus
  transfers own first-class road circuits with ordered endpoints, worthwhile
  scenic stops, named meal breaks, legs, and authoritative totals. Bus breaks
  must be scheduled or feasible for the actual service. The focused Map gives
  scenic and meal stops distinct route markers and excludes destination-local
  activities after arrival/check-in. Long-drive insight explains same-vehicle
  continuation, useful breaks, and the option to add a preferred meal as a
  separate stop.
- Exact occurrence identity controls scroll, selection, booking state, and
  removal for repeated places.
- Flights, Inter-city Road, Inter-city Train, and Hotels are independent pane-header
  filters. Active filters union across Itinerary and Map; no active filters show
  the complete trip. Filtering preserves authoritative day/stop identity, full
  selected journey geometry, and Trip Snapshot while hiding unmatched days.
  Flight mode remains authoritative filter evidence for legacy map legs that
  omit the optional inter-city marker.

### MAP-01 - Map behavior

The authoritative action-by-action regression contract is
[`EXPECTED_BEHAVIORS.md`](EXPECTED_BEHAVIORS.md). This section records the
implemented capability baseline.

- Day-colored pins and route bands represent complete hotel-anchored circuits.
- Single-hotel days use `H`; days with distinct hotel endpoints use route-ordered
  `H1`, `H2`, and so on, with a dotted day-colored direct hotel connector.
- Genuine transfer days instead render one open endpoint-to-endpoint journey in
  itinerary order. Road waypoints and the destination stay retain the same Drive
  edge mode across the full journey. The full journey remains visible, while day focus frames the
  useful destination-local circuit or, on departure-only days, the origin-local
  circuit. Local legs retain the day color. Inter-city connectors are dotted:
  flights are blue, road and bus travel are black, and rail is gray, with a small
  airplane, car, bus, or train glyph at the line midpoint. `A` airport pins and
  other terminal pins remain visible.
- Exact-stop focus selects one itinerary occurrence, one map marker, its Details,
  and zoom 15. Repeating the action reapplies focus after manual filtering.
- Airport, railway-station, bus-stand, and other enriched terminal focus uses the
  same zoom 15 map behavior and opens contextual place Details with available
  photos, rating, reviews, address, summary, and website. It resolves the
  itinerary alias and requested occurrence even when the provider returns a
  different canonical terminal name.
- Selecting an inter-city flight or transport row frames the complete ordered
  source-to-destination route and connector without opening place Details or
  changing the destination-local framing used by aggregate day focus.
- Aggregate day focus clears exact-place focus, applies the framing rule above,
  aligns the itinerary at the day's summary, visibly selects that day card, and
  replaces any stale place tile with day title/destination, schedule, and route context.
- Itinerary stop names remain the map identity. Provider metadata may enrich a
  pin only when the returned place name plausibly matches; a clearly mismatched
  result must not supply coordinates or relabel the stop.
- All-days focus clears exact and single-day focus, fits all circuits and complete
  dotted flight connections, aligns the itinerary at the trip summary, and
  visibly selects the clickable Trip Snapshot.
- Newly created or selected trips default to All days; content-only refreshes keep
  the user's current day scope.
- Provider-expanded or differently punctuated place names still resolve to the
  authoritative itinerary occurrence.
- Viewport-biased autocomplete and labeled native map POI clicks create a
  temporary real-coordinate inspection tile. Inspection does not mutate the trip.
- Temporary places offer `Best day` or an exact authoritative day beside Add.
- Add stop type is optional for manual text. A Google-selected place visibly
  marks its inferred Attraction, Hotel, or Restaurant type as auto-filled and
  lets the user correct it before adding.
- Map day scope remains directly available beside the Map pane title. The Add stop
  form stays visible below the header, and one compact context line distinguishes
  the selected day's schedule span from route-only duration, distance, and mode.
- Itinerary, Map, and Details group pane-local Hide and Maximize/Restore icons in
  a restrained pair. Existing behavior, disabled states, and recovery remain unchanged.
- Itinerary filters are shared with Map. Filter changes return Map to All days and
  remove stale exact/route focus; trip changes clear the presentation-only filters.

### PLACE-01 and MUT-01 - Details and coherent mutations

- Whole-trip Details is a destination guide plus a compact authoritative place
  collection; it does not duplicate the trip snapshot or map.
- Focused Details includes gallery, reviews, address, website, and shared trip
  actions.
- Map and Details use one selected-place control. A normal non-hotel occurrence
  shows its current day, can move day, and removes directly.
- Rare repeated places expose exact occurrence actions and `Remove everywhere`.
  An occurrence cannot move to a day already containing the same place.
- Hotels retain stay-range semantics instead of attraction-style single-day moves.
- Add, move, remove, stay, and booking mutations refresh every dependent surface.
- Duplicate removals coalesce, pending actions disable, and authoritative mutation
  responses supersede older reads.
- The changed place remains focused so the inverse action is immediately visible.

### EXPORT-01 - Trip handoffs

- Preview and print-friendly HTML with minimal, detailed, and family templates.
- Print/save PDF and direct PDF download, with a print fallback when the direct
  renderer is unavailable.
- Optional place photos and embedded day maps/circuit diagrams are consistent
  across preview, print, PDF, and email.
- Email uses configured server delivery or a prefilled local mail-app fallback.
  Each explicit send carries a stable client request ID. ACS receives a stable
  provider operation ID and completed requests replay without another send;
  ambiguous ACS outcomes never fall through to SMTP. SMTP is claimed at most
  once and reports uncertain delivery rather than risking a duplicate retry.
- Signed, sanitized, read-only public share links.
- RFC 5545 calendar export.

## 5. Native mobile clients

### MOBILE-01 - iPhone and Android parity

- One Expo/React Native application provides native Trips, Plan, Map, Assistant,
  Details, and Account experiences on iOS and Android.
- Shared dependency-free client code owns contracts, HTTP/SSE transport,
  mutations, and workspace revisions for web and native clients.
- Platform adapters own navigation, sheets, secure storage, maps, deep links,
  sharing, and lifecycle behavior.
- Native mutations and completed Assistant turns refresh every dependent trip
  surface, matching web ownership semantics.
- Account supports Google sign-in/out, preferences, refresh, and API diagnostics.
- Expo Go, EAS preview, TestFlight, and Play testing have maintained runbooks;
  production store submission remains an explicit owner approval gate.

## 6. Reliability, performance, safety, and operations

### REL-01 - Reliability and performance

- One workspace revision/focus owner prevents older trip, itinerary, map, or
  Details responses from overwriting current state.
- Requests abort on trip switches and superseding changes while prior content
  remains visible with retry state.
- Native refreshes share one abortable generation across Trip, Itinerary, Map,
  saved trips, and chat so any superseded result is discarded consistently.
- Native rendered stop indexes are converted to the backend's one-based
  occurrence contract before exact repeated-place actions are sent.
- Interrupted SSE exits busy state and preserves recoverable conversation state.
- Blocking backend trip operations run in worker threads rather than blocking
  the asynchronous API loop.
- Local JSON writes are atomic with bounded Windows lock retry; same-user trip
  mutations serialize.
- Persisted local Cosmos startup repairs stale runtime locks only after proving
  no database process exists and never resets the named data volume.
- Place metadata uses a synchronized durable cache with long metadata TTL,
  shorter signed-photo URL TTL, request coalescing, and parallel prefetch.
- Read-only agent tools use a per-user read-through cache where safe.
- Every outbound dependency shares one pooled HTTP runtime that reuses
  connections and TLS, applies a per-endpoint latency budget derived from the
  request host, and opens a per-endpoint circuit breaker so a failing dependency
  fails fast instead of charging its full timeout to every later caller. Open
  circuits are visible through `GET /providers/status`.
- The model client is reused across the tool phases of a turn so each round does
  not pay a fresh TLS handshake; usage accounting is keyed per model run.
- Independent remote work in one response is fanned out concurrently, with a
  failed branch degrading rather than failing the response. Ordered provider
  fallback within a single capability stays sequential.
- A deterministic FastAPI regression gate measures p50/p95 and HTTP errors for
  representative trip reads plus a workspace mutation while retaining identity,
  thread-offload, and admission behavior. It rejects p95 above 750 ms and proves
  the hermetic run records zero LLM calls or cost; production capacity remains
  governed by hosted telemetry rather than local timing.

### SAFE-01 - Cost, grounding, and security

- Per-user monthly LLM cost accounting can stop new chat turns at a configured
  cap.
- Hosted chat bounds input size, per-user/IP request rate, and per-user/global
  concurrency before model execution; usage accounting follows the resolved
  server-derived principal.
- A deterministic critic records ungrounded prices, times, and URLs found in a
  final response without adding noisy warnings to the user experience.
- Provider secrets are configuration, not repository content, and hosted secrets
  are injected into Container Apps.
- User data is partitioned by identity; canary and production use isolated data.
- OAuth callbacks, session signing, and Google Maps keys are owned by the target
  environment. Local, canary, and production use separate Google Cloud
  projects, OAuth clients, and restricted browser/server keys; only the billing
  account is shared.
- Overlapping authenticated HTTP requests verify same-principal chat rejection,
  chat-versus-workspace exclusion, and permit recovery after the active turn.
- Tool latency, failures, cache hits, model-call latency/tokens/prompt size,
  forced completion-gate reasons, structured events, and hosted health are
  observable through API metrics and Azure logs.
- Performance and cost evidence is separated into a hermetic regression gate,
  production SLO/tool telemetry, and Azure billing/Cosmos RU analysis so changes
  are driven by measured bottlenecks rather than synthetic provider traffic.
- Harness reports preserve measured runtime counts, versioned catalog estimates,
  and delayed cloud-billing reconciliation as distinct layers. Google operation
  and field-mask classes and Places memory, durable, miss, refresh, and coalesced
  outcomes are emitted at their owning boundaries for per-scenario attribution.
- All six application containers can be exported to a portable checksummed
  artifact and restored exactly into an empty isolated recovery database.
  Recovery drills reject live, same-coordinate, nonempty, incomplete, or
  partial targets and produce credential-free RPO/RTO evidence. Any real
  production recovery or Azure-native point-in-time restore requires explicit
  owner approval.

### OPS-01 - Development and release

- One Windows setup command verifies tooling, restores locked dependencies, and
  preserves existing secrets.
- One local SPA command starts the persisted emulator/backend/frontend workflow,
  force-clears process trees from enabled API, SPA, and Labs ports, verifies
  release, and cleanly restarts each enabled service.
- Backend, frontend, browser, shared-client, and native validation commands are
  documented in `docs/CODEMAP.md`.
- Canary builds and pushes one immutable Git-SHA image to GHCR, validates IaC,
  blocks deletes, deploys, and runs public read-only smoke.
- The manual GitHub Actions workflow can build and push images only; it has no
  Azure login or deployment authority. Guarded PowerShell scripts exclusively
  own canary and production deployment.
- Deep canary smoke verifies Azure OpenAI through an isolated write.
- Production resolves the current Git SHA by default and verifies that exact
  image is both live in canary and represented in successful smoke history. A
  missing gate automatically runs canary deployment and read-only verification
  before manual validation, bake evidence, and the explicit approval phrase.
- Production smoke, normalized chat outcome/latency telemetry, explicit SLO
  queries, release monitoring, and guarded revision rollback complete the flow.
- Production deployment and mobile store submission are never automatic.

### OPS-02 - Failure detection and response

- The existing PII-safe Container Apps stdout stream and 30-day Log Analytics
  workspace remain the only hosted telemetry pipeline; Application Insights is
  not duplicated.
- Production parameters enable a five-minute Azure Monitor scheduled-query alert
  for application, chat, and tool failures. Its Action Group emails the owner,
  groups bursts, and auto-resolves after the query is clean.
- The alert is guarded because creating it requires the existing explicit
  production deployment approval. Canary and local parameters cannot send email.
- Local development retains a bounded rotating redacted JSON log. One read-only
  analyzer classifies that stream or canary Log Analytics results and writes an
  ignored Markdown report with targeted investigation steps and a scheduler-
  friendly failure exit code.

## 7. Explicit gaps and non-goals

### Current gaps

- Real provider-side booking, payment, ticketing, and confirmation are not
  implemented despite legacy `execute_bookings` naming and output text.
- Embedded feedback capture, ads, broader expensive-endpoint/provider guardrails,
  and a global daily spend circuit breaker are not implemented. Production-only
  GA4 product analytics uses explicit reversible consent, a deliberately small
  event vocabulary, and no chat, itinerary, family, email, exact-date, account,
  or shared-link content. Analytics preferences can be reopened from Account
  even when collection is not configured; the preference is saved without
  enabling collection. The production custom domain and hosted chat admission
  controls are already present.
- Exact-place map focus remains at zoom 15 while real usage is observed.
- Whole-trip Details still receives one eager, flat collection capped at ten
  places. The active Destination Guide Lab compares contextual city/type browsing
  and progressive results before a paged production contract is approved.
- Production mobile-store release still requires owner-approved distribution
  setup and provider keys appropriate to each platform.
- Structured Assistant input is not yet rendered in production web or native UI.
  The selectable overlay/control prototype is active in UX Labs; production wiring
  requires an owner-selected direction.
- The implemented cost-optimization layer (DEAL-01) covers exact-response stay and flight
  comparisons support deterministic selection and reversal. User-owned budget
  targets, evidence-labeled headroom, published FX provenance, explicitly
  requested exact-alternative savings proposals, and atomic coordinated proposal
  acceptance are implemented. Provider-reported taxes, fees, and property-due
  amounts now survive exact-option selection; the strict ledger keeps a live
  quoted subtotal distinct from a confirmed all-in total and names unresolved
  mandatory taxes, fees, and baggage rather than inventing them. Persisted offers
  for the same provider-neutral room/rate or flight itinerary now compare across
  sources only when mandatory costs are complete. Consented program/card identity
  and published portal discount terms may be applied without storing payment data.
  Finalized unbooked expired exact flight and stay quotes can be rechecked through
  an explicit action. Rechecks preserve original occupancy/nationality evidence,
  record price movement, and never replace a selection; older stays without that
  context fail closed. Automated schedules, provider-specific inclusion semantics,
  and broader loyalty/portal terms ingestion remain future extensions.
- No server-rendered public edge. One FastAPI process serves the API and the
  client-rendered SPA, so landing, destination-content, and shared-trip URLs are
  not indexable and not first-paint-fast for anonymous visitors.

### Out of scope unless explicitly reopened

- General personal-assistant agents for todo, email, SMS, calls, calendar, Keep,
  WhatsApp, budgeting, or multi-agent routing.
- Automated payment or purchasing without explicit product, provider, legal,
  security, and user-confirmation design.
- Organization, team, and enterprise tenancy features.
- Background email, SMS, or push notifications.
- Generic chatbot behavior unrelated to planning a trip.

## 8. Proposed roadmap

These are ordered candidate outcomes, not an instruction to implement them all.
Each requires a focused feature brief and owner approval. The broader candidate
backlog, including Live Trip Mode, reservation import, disruption-aware
replanning, collaboration, offline mobile essentials, and longer-term verified
booking, lives in [`roadmap/FUTURE_FEATURES.md`](roadmap/FUTURE_FEATURES.md).

### Priority 1 - Public MVP readiness

**Outcome:** safely expose the existing planner to early users and measure
whether they create useful trips and return.

- Keep `aitripplanner.co` and `www.aitripplanner.co` bound to production through
  repository-owned managed certificates and parameters.
- Keep OAuth callback ownership on the apex domain and restrict browser API keys
  to approved origins.
- Add privacy, terms, contact, and user-data deletion surfaces appropriate to a
  public product.
- Extend the existing hosted chat admission boundary to any newly exposed
  expensive paths, add provider quotas/bot controls where needed, and add a
  global daily AI spend circuit breaker.
- Add product analytics with a deliberately small event vocabulary and no chat,
  itinerary, family, email, or exact-date content in telemetry.
- Add contextual feedback after a meaningful planning outcome, not a generic
  always-visible survey.
- Define the activation funnel: visit -> first prompt -> trip created -> complete
  itinerary -> export/share/handoff -> return.
- Give the public edge a server-rendered or prerendered surface (landing,
  destination content, shared trips) with real link previews, while the planner
  workspace stays the SPA.
- Set Azure and provider budget alerts before broad sharing.

### Priority 2 - Evidence-led product improvement

**Outcome:** turn observed friction and user feedback into small, measurable
increments.

- Review activation, completion time, failure points, repeated edits, export/share
  use, return rate, and qualitative feedback on a regular cadence.
- Use one feature brief per coherent outcome and state the expected metric change.
- Prefer improvements to planning completeness, trust, and cross-surface coherence
  over adding disconnected feature breadth.
- Revisit exact-place zoom only when usage or feedback triggers the recorded
  decision in `docs/roadmap/DEFERRED_DECISIONS.md`.

### Priority 3 - Responsible monetization

**Outcome:** test revenue only after the product demonstrates useful traffic.

- Compare verified travel affiliate handoffs with display advertising; prefer
  monetization aligned with a user's booking task.
- If display ads are approved, first meet publisher-content, privacy, consent,
  and `ads.txt` requirements.
- Limit ads to a stable, clearly labeled destination-content placement. Never put
  them in Map controls, Itinerary actions, Assistant, navigation, dialogs, or
  beside mutation buttons.
- Measure revenue against activation, task completion, latency, and retention;
  remove the experiment if product harm exceeds value.

### Priority 4 - Verified booking handoffs

**Outcome:** replace simulated execution wording with trustworthy, measurable
provider actions.

- First make lifecycle language truthful and distinguish planned, finalized,
  handed off, and confirmed externally.
- Add provider adapters only where commercial access, terms, confirmation,
  cancellation, identity, payment, and support responsibilities are explicit.
- Never infer successful booking from a link click or local status change.

### Priority 5 - Trip cost intelligence and deal optimization

**Outcome:** the same approved itinerary costs less, and the user can see why.

- Model total trip cost as one number the user can act on: flights, stay,
  activities, ground travel, and known fees, each carrying its currency, provider,
  and quote time.
- Compare more than one source for the same choice before recommending it, and
  keep provider, price, and fetch time attached to every claim.
- Re-check prices for a finalized-but-unbooked trip through an explicit bounded
  action; never silently mutate the plan because a price moved. Automated
  schedules remain a later extension.
- Treat loyalty programs, card benefits, and portal offers as consent-gated
  preference data. Store program and card identity only, never card numbers, and
  link every offer claim to its terms.
- Report savings honestly: state what was compared and what was not, and never
  present an unverified discount as a held price.
- Keep it fast. Optimization is background and time-boxed; the plan renders from
  what is already known.

### Priority 6 - Mobile distribution maturity

**Outcome:** move from device testing to owner-approved beta and store releases.

- Complete platform keys, privacy declarations, deep links, store metadata,
  crash/usage diagnostics, and beta feedback flow.
- Validate behavioral parity and public API safeguards before each distribution
  stage.

## 9. Quality bar

Every increment must:

1. State the user problem and observable success before implementation details.
2. Identify current behavior and the smallest capability IDs being changed.
3. Preserve one conceptual action across every affected pane and platform.
4. Define empty, loading, stale, partial, error, retry, and conflict behavior.
5. Address privacy, abuse, provider cost, latency, and data migration where relevant.
6. Include focused acceptance criteria and a validation matrix.
7. Update code, tests, canonical docs, and operational runbooks together.
8. Pass the relevant local checks, then use immutable canary promotion and explicit
   production approval for hosted changes.

Use `docs/feature-briefs/FEATURE_BRIEF_TEMPLATE.md` for new work. The owner may
write only the short required section and leave the rest for the agent to
normalize, but unresolved product choices must remain visible rather than being
silently invented.
