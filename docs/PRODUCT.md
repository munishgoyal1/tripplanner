# PRODUCT — tripplanner trip planner

> The "what & why" companion to [CODEMAP.md](./CODEMAP.md) (the "where").
> Keep this short, opinionated, and current. If a feature lands that
> changes the vision/taste/scope, update this file in the same commit.

## 1) Product

A personal AI trip planner that produces a **complete, booking-ready** trip —
not a list of suggestions. It combines grounded flight, stay, activity,
transport, place, review, weather, and travel-content sources through a
provider-neutral layer. A single LangGraph agent uses a phase-selected tool set.
It learns from preferences and past trips and remembers them across devices.

The product also serves as an end-to-end multi-form-factor proof of concept:
the same planner capabilities should feel native on web, iPhone, and Android
without duplicating the agent, travel logic, or persistence model.

**Target user**: the owner (Munish). One-person product. Optimize for *his*
flow, not a generic SaaS. If it isn't useful to him today, it doesn't ship.

**North star — two goals, in this order:**

1. **The best possible itinerary.** The most intelligent trip the user could have
   planned for themselves, inside their preferences, tastes, budget, pace, and
   hard constraints — decided by the agent, explained, and editable.
2. **The best possible price for that trip, then a bridge into booking.** Once the
   plan is right, find the strongest real prices and offers for it and hand the
   user into booking with verified, pre-filled material. Later this may include the
   user's own payment context — for example which cards they hold — so card and
   portal offers are compared before the handoff. That context is consent-gated
   preference data: the product stores program and card identity, never card
   numbers, and never charges a payment method itself.

Neither goal may cost the third property: the planner stays fast and breezy.
Price and offer work is background and time-boxed, and the product always shows
the plan it already has rather than blocking on a better one.

New-trip planning is automation-first. Once the user supplies an origin,
destination, and rough timing, the agent owns the first complete proposal: it
chooses sensible defaults, researches and selects the strongest verified hotel,
fills every day with concrete places and meals, and persists the enriched plan.
The user refines a useful plan through chat instead of designing one from a blank
canvas or resolving avoidable `TBD` decisions.

Trip duration is part of the recommendation, not a universal default. When the
user leaves duration flexible, an explainable planning layer estimates the
shortest useful stay from preference-matched anchor experiences, visit and travel
time, destination scope, arrival/departure capacity, desired free time, daily
attraction tolerance, and relevant past-trip pace outcomes. Explicit dates or
duration always win. Sparse fixed trips gain meaningful nearby experiences or
clearly intentional leisure rather than filler or silent shortening. Future
cross-user learning may influence this estimate only through privacy-safe,
versioned cohort aggregates with minimum sample and confidence gates; another
traveler's itinerary is never exposed or copied.

The Assistant is the primary itinerary-building surface. It starts from saved
preferences and trip history, distinguishes durable defaults from one-trip
exceptions, and asks at most one consolidated question when an unresolved fact
would materially change the plan. Capable clients should render that question as
prefilled structured controls with a skip/default path; typed data, not model-authored
markup, owns those interactions. After the first complete plan, Details and Map
support visual refinement while Assistant remains available for broader changes.

## 2) Non-goals (resist scope creep)

- ❌ Multi-tenant features (orgs, teams, sharing) until explicitly asked.
- ❌ Automated purchasing or card charging. Booking remains a verified handoff; a
  future booking bridge deep-links into the provider with the choice already
  verified and pre-filled, and still does not transact inside the product.
- ❌ Provider commissions or affiliate payouts influencing recommendations. The
  user gets the best fit and most cost-effective practical choice regardless of
  how much the product may earn from the eventual handoff.
- ❌ Treating an activity from-price or operating schedule as a held quote or booking.
- ❌ Background email/SMS/push notifications (removed Session 1).
- ❌ Calendar/Gmail/Keep integrations (removed Session 1).
- ❌ Generic chatbot vibes. This is a planner, not a friend-bot.

## 2a) MVP provider and economics rules

- **Free or near-free first.** During MVP, prefer provider sandboxes, free
  developer tiers, public/open feeds, affiliate discovery access, and low-cost
  services. Do not add a paid provider merely because it has broader inventory;
  first measure usage, throttling, accuracy, latency, and cost. A paid service
  needs an explicit must-have justification after that evidence exists.
- **Two or three sources are enough.** Each important category should have a
  primary source and one or two practical fallbacks, not a sprawling provider
  matrix. Candidates may include Duffel, Kiwi.com, Omio, Travelpayouts, Viator,
  Tiqets, Nuitee/LiteAPI, Google Places/Routes, GTFS/OpenTripPlanner, and
  regional operator feeds, subject to their current terms and access.
- **Fallback is a default behavior.** Provider timeout, throttling, outage,
  malformed data, missing coverage, or an unavailable key should move to the
  next eligible source. A fallback must retain its source, freshness, currency,
  inclusions, and confidence rather than silently looking like primary data.
- **Cache before fan-out.** Every provider capability has a configurable,
  persisted TTL cache appropriate to the data type. Cache reads first, then
  query the preferred source, then fallbacks. Explicit refresh remains possible.
  Cache age must be visible whenever it materially affects price or availability.
- **MVP does not require exact real-time data.** The product should remain
  practically accurate and useful with recently checked, cached, indicative, or
  provider-deep-linked data when exact live verification is unavailable. Every
  price and availability claim is labeled with its evidence level and checked
  time; no stale or approximate value is presented as a held quote.
- **Real-time is an evolution path.** After MVP usage and cost patterns are
  understood, increase refresh frequency, add stronger revalidation and
  provider coverage, and introduce paid live services only where they improve a
  must-have experience enough to justify their cost.
- **Optimize for the traveler, not the provider.** Ranking may optimize total
  practical trip cost, time, comfort, reliability, preference fit, and risk.
  Affiliate relationships are disclosed and never change the ranking objective.
- **Booking stays external.** The future booking bridge sends the user to the
  selected provider or affiliate, preserves verified handoff details, and
  ingests booking confirmations. Tripplanner does not take booking payment or
  become the merchant of record.

The durable promise is a surprising amount of time and effort saved: a smooth,
preference-aware, realistic, intelligent itinerary that is more practical and
cost-effective than most users could assemble themselves, even while the MVP
uses carefully labeled cached and partially verified sources.

## 3) Run modes

- **LOCAL**: CLI or React SPA/API; isolated Cosmos Emulator by default, with
  Azure `tripplanner-local` as an explicit config option and JSON fallback for
  an unconfigured CLI.
- **HOSTED**: React SPA via FastAPI on Container Apps; shared free-tier Cosmos
  account with isolated environment databases.
- **MOBILE**: one Expo/React Native client for iPhone and Android using the
  hosted FastAPI contracts; native tabs, sheets, secure identity, and platform
  maps own phone ergonomics.

One codebase, dispatcher in `storage_cosmos.is_enabled()`.

The React SPA is the app shell, not the whole architecture. A planner is a
logged-in, stateful workspace, and an SPA is the normal shape for that; scale
comes from what sits behind it — API, agent, provider fan-out, cache, and data
tier — not from replacing the client. What a public product does need is a
credible public edge: server-rendered or prerendered landing, destination, and
shared-trip pages that are fast on first paint, indexable, and link-previewable,
with the SPA taking over the moment planning starts. "SPA for the workspace,
rendered HTML for the public edge" is the intended shape.

Cross-form-factor rules live in `packages/tripplanner-client`: JSON contracts,
trip mutations, SSE parsing, and workspace revisions are shared. Platform code
must stay limited to presentation and device adapters. iPhone and Android reuse
this mobile shell rather than forking product logic. Native Google sign-in must
resolve to the same stable `google-<sub>` identity as the web app so saved trips,
preferences, and chat history remain continuous across devices.

## 4) Owner taste — the look & feel

Reference points: **Airbnb** and **TripAdvisor** (magazine-style travel
browsing). NOT a corporate dashboard, NOT a chat-toy, NOT generic Bootstrap.

- **Layout**: desktop is a fixed-height spatial planner: itinerary left, a
  persistent dominant map center, and a contextual details inspector right.
  A compact top command bar owns saved-trip selection, global workspace
  controls (including account/preferences), and the latest mutation outcome.
  Itinerary, Map, Details, and Assistant use semantic icons with short labels on
  wide desktops, collapsing to icon-only controls when desktop width is tighter;
  all four remain direct one-click visibility controls. New trip uses a restrained
  coral tint rather than a solid fill; active pane controls use quiet neutral fills,
  while trip actions remain a lighter compact icon and Account settings uses one
  short identity label. This
  keeps itinerary, map, and trip decisions visually dominant.
  The itinerary begins with the one authoritative trip snapshot: destination,
  dates, travelers, lifecycle, unique counts, booking progress, cost/budget,
  family/preference context, constraints, compact daily weather, and practical
  packing guidance. Its Decision brief hierarchy keeps booking readiness explicit,
  renders Days/Stay/Places/Flights as one compact facts row, and does not repeat a
  generic Trip fit summary below Budget. A trip-level narrative follows identity;
  older trips without authored notes receive a factual summary. Weather remains a
  stable section and labels missing persisted forecast data instead of disappearing.
  Weather must identify live forecasts versus seasonal/monthly estimates, and
  every itinerary day with weather evidence shows its condition and temperature.
  Its saved-trip menu must overlay
  every planner pane. Itinerary, Map, Details, and Assistant have obvious
  show/hide controls. Assistant opens as a compact lower-right conversation sheet
  over the still-usable workspace and stays mounted while hidden so its conversation
  state survives. Only panes scroll; the page never does.
  Map commands sit below the map so the pane reads as a map first: a resting search
  field that reveals stop type, target day and Add once a place is named or tapped,
  then All days/day scope beside an optional stop-sequence strip, then one compact
  line separating schedule span from route-only travel. This hierarchy does not
  change map focus, placement, pin, route, or mutation behavior. Itinerary, Map,
  and Details group their pane-local Hide and Maximize/Restore icons in a quiet
  restrained pair without changing behavior, disabled states, or recovery.
  Accessible drag/keyboard
  separators resize itinerary, map, inspector, and the details/chat split, and
  sizes persist locally. The Assistant closes explicitly or with Escape and
  reopens from the command bar; Details remains an independent dock. Itinerary,
  Map, and Details can each be maximized and restored. On narrower desktops
  the inspector overlays the map on demand. Mobile mounts chat plus an on-demand
  trip-details sheet.
  Desktop pane visibility is fully independent: any combination, including all
  panes hidden, is valid and persists locally; the command bar always remains as
  the recovery surface. A visible docked pane has no arbitrary maximum width and
  may use all space not required by the minimum usable widths of visible siblings.
- **Color**: coral `brand` (#e11d48) as the single accent for primary action +
  active state; teal `accent` for secondary surfaces; ink/muted/surface
  neutrals everywhere else. No rainbow.
- **Type**: Inter for UI; Fraunces for display headings. Fonts loaded via
  `<link>` in `frontend/index.html` (NOT from CSS — PostCSS rejects late `@import`).
- **Shape**: use radii and elevation only where an object is genuinely framed
  or floating. The itinerary snapshot and destination guide are full-width
  bands inside their panes, not decorative cards nested inside cards.
- **UX Labs**: catalog filters belong only on catalog pages and expose All Open Labs,
  In progress, Implemented review, Parked, and Completed views. All Open Labs contains
  every lifecycle state except Completed, including implementations awaiting review.
  An individual Lab has one clear
  return to All Labs. A chosen option carries its modifications,
  additional inputs, and implementation instructions in one handoff. Labs can be
  marked ready, parked with that handoff intact, implemented and awaiting owner
  review, completed after owner sign-off or verified sandbox promotion with the selected decision preserved,
  or discarded from consideration. Production implementation moves a Lab to
  **Implemented - To be reviewed** after each coherent sandbox iteration; explicit
  owner sign-off or verified promotion completes it.
  Lifecycle state never locks a Lab or its alternatives. Every option remains
  browsable, and an implemented or completed Lab can be revisited with another
  option, revised comments, or additional input. Saving that handoff starts a new
  implementation cycle in Ready while preserving a visible record of what was
  implemented previously. What was implemented retains each implementation as an
  ordered version with its selected option, exact saved handoff notes, and recorded
  time, followed by one summary of every implemented option and its notes.
  This review workflow applies to implementations from 2026-08-02 onward;
  implementations completed before that date remain in the Completed archive.
  Every card identifies when the Lab was created and when it entered its current
  lifecycle state. Every Lab also has one permanent integer identifier, displayed
  as `Lab #N` in every catalog state and on its detail page. The top of every Lab
  detail page shows its authoritative, color-coded lifecycle status and its state
  date when recorded, updating immediately after a lifecycle save. Its HTML entry name is
  prefixed with `lab-N-`. New Labs take the next integer; numbers are never changed,
  reused, or derived from filtering or display order. Machine state
  overrides committed historical fallback metadata,
  so one Lab cannot appear in conflicting filters.
  Completed Lab cards live only in the dedicated archive reached from the catalog;
  they do not repeat below active or parked work on the main Labs page.
  Lifecycle records have one machine-level authority shared by all worktrees;
  unavailable state is never inferred as active, and the prior snapshot remains
  recoverable after each write.
  Before its options, every Lab explicitly separates the exact elements being
  changed from realistic surrounding UI that is context only. Selecting an option
  does not implicitly approve changes to other elements visible in its preview.
  Every option is a production-scale, Figma-level mock of the complete proposed
  change: all relevant destinations, expanded states, realistic data, controls,
  and edge or destructive states are inspectable rather than represented by inert
  labels. The surrounding full-app context remains visible wherever it affects
  evaluation.
  Optional Lab-only markers outline those exact varied regions without changing
  preview layout, styling, or interaction and can be hidden for an unannotated view.
- **Density**: information-rich but ordered. The itinerary snapshot should pack
  the trip's decision-making facts into a scan-friendly Decision brief hierarchy.
  Whole-trip
  place browsing uses compact media rows; rich galleries and reviews belong to
  the focused-place view. One clear primary action per item.
- **Motion**: subtle hover-lift, 300ms cross-fades on data switches. NO
  blanking the panel while data loads — keep prior content dimmed (`stale`
  opacity-70) and swap when ready.
- **Reliability**: only the active responsive shell mounts. Focus/view requests
  cancel stale predecessors, interrupted chat streams recover the composer,
  and map/itinerary refreshes retain prior data with visible retry states.
  One workspace reducer owns trip identity/revision and active place state, so
  focus-only navigation never triggers unrelated panel reloads. Stale trip,
  map, itinerary, and Details requests abort during rapid changes and saved-trip
  switches; an old trip response must never overwrite the selected trip.
- **Assistant responsiveness**: a submitted turn immediately shows a concise
  thinking state, then friendly work phases for live searches, reviewing, and
  saving. The Assistant and common command bar share those truthful milestones.
  One overall elapsed clock and a typical 2–4 minute full-build expectation remain
  visible throughout long planning turns; after two minutes the copy explicitly
  reassures the user that work continues and no refresh is needed. Internal tool
  names and raw arguments stay out of the primary experience. A completion message
  appears only after the refreshed itinerary has loaded, invites the user to inspect
  a new plan, and summarizes the authoritative outcome of an existing-plan update.
  Streamed answer text does not hide workspace-level progress. GPT-4.1 remains the planning
  model unless measured quality failures justify a slower or costlier model.
  While streaming, Send becomes Stop; cancellation preserves useful partial text,
  restores the composer, and does not masquerade as a failed retry. Message Copy
  is direct. Editing a prior instruction loads it into the composer and sends any
  revision as a new corrective turn because completed turns may already have
  changed the authoritative itinerary.
- **Assistant input**: show the saved or inferred defaults already being applied,
  then ask only for useful trip-specific changes. Every new trip begins with this
  single compact review after preferences load and before plan creation; direct
  mode proceeds without follow-up questions after submit or skip. Structured prompts
  prefill every field and offer one build/continue action plus a default skip path.
  The selected Option B corner conversation sheet and structured controls are implemented in
  the main web app. No hosted deployment is implied.
- **Itinerary scanning**: each day header shows stop count, `Schedule duration`,
  a separate `Day's travel` row with route distance/time/mode, and a direct Maps
  handoff before the stop details.
  A complete exported Trip Book should remain executable away from the live app:
  contents first, trip and day plans next, then booking confirmations and entry
  documents, with optional place context last. Personal insights must identify
  the saved preference and verified travel fact behind them. Packet structure is
  currently an active UX Lab decision; document ingestion and merged-PDF storage
  are not approved production scope.
  The backend owns one day timing contract consumed by both Itinerary and Map:
  the schedule spans hotel departure through return (or the applicable transfer/
  transit endpoints), while `Day's travel` is the route-only subtotal. If
  endpoint times are incomplete, estimated departure and return are derived from
  timed visits and known route legs, shown on the hotel rows, and labeled as
  estimates. Place rows expose arrival, visit duration, departure, estimated
  transfer arrival, and any free buffer or timing conflict so the day clock adds
  up. Transit uses the consistent Walk, Metro, and Taxi vocabulary; every
  estimated leg names its endpoints and gives a short, non-fabricated transfer
  pointer. Place evidence includes Google rating and review count plus an
  estimated must-visit score derived from those signals. It must never be
  described as the percentage of traveler itineraries containing the place
  because that data is unavailable. Compact agenda
  rows are dense and left-anchored: time, marker, place, booking state, and
  actions read in one direction without drifting toward the center or right.
  Hotel circuit anchors show Depart/Return semantics without a visit duration,
  redundant In trip state, or an individual delete action; stay changes use the
  stay-range controls instead. When a day departs from and returns to the same
  hotel, the first row owns stay details and controls while a compact return
  endpoint remains after the final plan with its incoming travel and return time.
  Different endpoint hotels remain separate and read as Check out and Check in.
  A multi-city transition day keeps those endpoints, the complete journey,
  remaining destination plans, and return in one chronological spine rather than
  pairing hotels as cards or splitting city chapters.
  Place rows carry subtle day-colored sequence markers matching the map circuit:
  `H` for a single hotel, route-ordered `H1`, `H2`, and so on for distinct hotel
  endpoints, and `1, 2, 3...` for attractions and restaurants.
  Flight transitions render both airport endpoints as `A` rows with truthful
  local Depart/Arrive times. The destination stay may show an estimated arrival
  only when the airport-transfer timing supports it.
  Each mapped destination row also shows a quiet estimated distance/time from
  the previous stop. The selected map day labels each route segment at its
  midpoint; all-days mode omits leg labels to keep overlapping circuits legible.
  A day with distinct hotel endpoints numbers its map markers `H1`, `H2`, and so
  on in route order without counting a repeated return twice. A direct line
  between those hotels is dotted in the day's circuit color; single-hotel days
  retain the plain `H` marker.
  Visit times strictly increase in circuit order and leave room for the stated
  duration plus travel. Route optimization/reflow always retimes affected stops;
  duplicate or backwards schedules are invalid source data, not a display concern.
  Clicking a place stop focuses both its map pin and its contextual Details view.
  The exact itinerary `H` or number becomes current, and the matching map marker
  stays at the standard 34x44 circuit geometry and keeps its day color and white
  border; only its center/label contrast inverts and its stacking rises. Changing
  selection immediately restores the previous marker and focuses only the latest
  one. Exact-stop and aggregate circuit focus are mutually exclusive, including
  through map remounts and slow Details enrichment. Already-loaded Details switch
  immediately; fresh Places data fills in afterward. Marker numbers come from
  authoritative itinerary occurrences even if route pin order drifts, and shorter
  itinerary names still match provider-expanded map names. Repeated clicks refocus
  the same stop after manual map-day changes.
  Airport, railway-station, bus-stand, and other enriched terminal markers pan
  to their exact occurrence at zoom 15 and open contextual place Details with
  available photos, rating, reviews, address, summary, and website. Itinerary
  terminal names remain valid focus identities when a map provider returns a
  different canonical name.
  Clicking an inter-city flight or transport row frames its source-to-destination
  route and connector without opening place Details. A saved drive is a separate
  circuit with stable identity, ordered intermediate stops, legs, and route
  metrics; focusing it excludes unrelated same-day map geometry. Legacy transport
  rows without that identity retain complete-day route framing. All-days view
  retains the dotted flight arcs between every airport pair so the complete trip
  connection remains visible in the overall itinerary geography. Inter-city
  connectors are dotted and visually identify their mode: blue with an airplane
  for flights, black with a car or bus for road travel, and gray with a train for rail.
  The complete day header is also clickable: it clears any prior exact-place
  selection and filters the map to that day. Ordinary days fit the complete route
  circuit. Transfer days retain the complete connected geometry but frame the
  useful destination-local circuit, or the origin-local circuit when the day ends
  at the distant arrival terminal. Place-row clicks remain exact-place
  actions: they synchronize the map number, itinerary row, and Details, then
  pan to zoom 15 while that behavior is evaluated through real usage.
  Focus retains the exact itinerary occurrence, so clicking a repeated hotel on
  Day 2 highlights and scrolls to that row and keeps the map on Day 2 rather
  than jumping to its first stay day. Google-
  canonical punctuation differences must not prevent an itinerary restaurant
  from resolving to its existing map pin and inspection tile.
  Selecting a Map day scrolls the itinerary to the start of that day's summary
  and performs the same
  aggregate full-circuit focus as its itinerary day header, without inventing a
  representative Details selection. Restaurants are place stops too: they join day circuits and
  support the same focus behavior. Substantial planning days use concrete,
  preference-matched restaurant names from search results, never generic or
  `TBD` meal placeholders. Ordinary days cannot be hotel-only: each needs a
  concrete attraction or named restaurant, while genuine flight/transport-only
  travel days remain valid. Each day circuit starts at the selected stay,
  includes every geocoded structured stop in itinerary order, and returns to the
  stay at night; repeated places remain part of every day that references them.
  The Map stop picker searches Google Places within the current map context and
  also accepts labeled POIs clicked directly on the map. Selecting any named POI
  first opens a temporary real-coordinate map tile and the contextual Details
  inspector while merely populating Add stop; inspection never mutates the trip.
  Stop type is optional for manually entered names. Google-selected places
  visibly label their inferred Attraction, Hotel, or Restaurant type as
  auto-filled while keeping that value editable before Add.
  A user can then choose the exact itinerary day before adding; that explicit choice takes precedence over
  automatic cross-day rebalancing, including when the place already exists on
  another day. The temporary map place tile exposes its own `Best day` / exact
  day selector beside Add to trip instead of relying on the toolbar's hidden
  selection. A genuinely unavailable day or booked-occurrence conflict leaves
  the trip unchanged and offers available days, Best day, or unbook-and-retry;
  the Map retains the user's place/day inputs. After adding a non-hotel place,
  both Details and Map show its current day and let the user move it to any
  authoritative itinerary day. Restaurant POIs persist as meal stops.
- **Common commands**: trip-wide Export, Share, and Add to calendar actions
  belong in one compact menu in the common command bar, not scattered through
  Details. Export supports photo-rich preview, print/save PDF, direct PDF, and email. Enabled
  exports include embedded day route maps plus place photos, address/rating,
  itinerary notes, time, and booking status; every output path honors the same
  media toggles. The account control visibly distinguishes a signed-in identity
  from a local guest. Hosted account data is authorized by signed sessions, not
  by a client-supplied identifier; anonymous browser/device identities receive a
  signed guest capability, and migration proves ownership of both sides.
- **Authoritative counts**: trip place counts include unique
  structured itinerary attractions and named meal/restaurant stops, even when
  the agent did not mirror them into `selected_activities`. Repeated visits,
  hotel endpoints, flights, and transport do not inflate the place count. The
  itinerary snapshot is their visible owner; other panes consume the same
  `TripOverview` contract only when the context truly requires those facts.
- **Details is contextual**: whole-trip Details is a clean destination guide
  followed by one compact authoritative place collection. It does not repeat
  the trip snapshot, attraction grids, or embedded map. Selecting a place turns
  it into the richer place inspector with gallery, reviews, website, and the
  shared trip actions.
- **Mutation coherence**: adding/removing a place or changing the stay refreshes
  the complete itinerary, not only one card. Unbooked attractions redistribute
  around the current hotel anchors using geographic proximity and balanced day
  load; booked attractions, hotels, and non-place stops stay fixed.
  Successful mutations always supersede older in-flight reads. Repeated clicks
  for the same removal coalesce, and every removal surface shows a disabled
  pending state until the mutation completes. Adding or removing a place keeps
  that changed place focused in Details, with the opposite action immediately
  available so the decision is easy to reverse. Repeated itinerary places are
  occurrence-aware: a row action removes that exact day/stop, while Details and
  Map use the same selected-place control for day moves and removal. The normal
  single occurrence shows its current day, offers Change day, and removes
  directly. Rare repeated places expose each visit separately plus Remove
  everywhere; a visit cannot move onto a day already containing that place.
  Hotels retain stay-range semantics instead of attraction-style single-day
  moves. These choices never depend on Assistant being visible.
- **Mutation status**: the latest update sits near the trip identity in a
  flexible command-bar region. Routine add/remove/reflow messages stay concise;
  the region names the final authoritative day when known and wraps when space
  is tight instead of clipping the update. This is the only global mutation-
  notification surface; Details does not repeat it.
- **Planner review**: structural UI mutations remain immediate and deterministic.
  After each add, move, removal, or stay change, a fast impact gate inspects the
  final persisted itinerary for material crowding, excessive travel, empty
  days, and substantial days without a named meal. Quiet changes require no
  extra interaction. A flagged change stays applied and exposes `Review with
  planner` plus `Keep as is` beside the command-bar outcome. Review starts a
  real Assistant turn with the exact concern and requires proposal-only options;
  that turn binds and executes read-only tools only, disables itinerary auto-
  persistence and passive learning, and cannot mutate the trip until the user
  explicitly approves one in a later turn.
  This gives the user conversational judgment without slowing every edit or
  silently overriding an explicit day choice.

If a redesign violates the above without a stated reason, push back.

## 5) Owner taste — interaction rules

- **Suggestions never disappear** when you pick one. Selected items get a
  green "In trip" pill and stay in the list (Airbnb/TripAdvisor pattern),
  rest of the list still scrollable. No "you picked it, it's gone" UX.
- **Currency is sticky per trip.** Domestic = home currency (INR ₹ default
  via `profile.home_country`). International = USD or local where it makes
  sense, optionally with home-currency equivalent in parens. Prices must
  not flip INR↔USD between sessions.
- **Read-only views render instantly from cache.** Per-destination overview
  uses split caching: backend place details/reviews keep a 1-week TTL while
  signed photo URLs refresh at ~50 minutes (`places_cache.py`), and frontend
  keeps a 30-min response cache in `api.ts` module Map. Background refresh,
  don't block paint.
- **Settings has an "About me" textbox** that runs an LLM extractor and
  **additively** merges into preferences. Never overwrite existing user data.
- **Account settings has one owner.** One labeled identity command opens a
  right-side sheet for Profile and sign-in, Travel Profile, Analytics
  preferences, and Privacy and data. Escape or the explicit close control
  dismisses it; do not restore a separate Travel preferences command-bar gear.

## 6) Owner taste — code & process

- Python 3.11, typed (`from __future__ import annotations`). One file per
  concern, flat layout under `src/tripplanner/`. Tools = `@tool`-decorated
  functions that return strings; the agent interprets.
- No unnecessary comments. No docstrings on code I didn't touch.
- Tests run in ~1.5s; keep them mock-free for pure logic. Run pytest once
  per milestone, not per micro-edit.
- **Always commit AND push** after every coherent change. Never leave
  unpushed work.
- **No major functional changes without explicit consent.** Refactors and
  structural improvements are fine; new features/behaviors require a yes.
- Update `README.md`, [the requirements log](./reference/history/requirements-log.txt), [CODEMAP.md](./CODEMAP.md), and
  [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) in
  the SAME commit as the code change that triggers them.
- Free-tier or near-free everything: Azure ≤ ₹10K/mo, Amadeus test, Google
  Places $200/mo credit, Tavily 1000/mo. Cosmos Free Tier (1000 RU/s + 25 GB).

## 7) Owner taste — agent behavior

- Be terse. 1–3 sentences for simple answers. Skip preamble/conclusion.
- No emojis unless asked.
- MasterAgent owns local server startup, restart, stale-port cleanup, and health checks
  for the owner's manual testing. Workers 1, 2, and 3 must ask before changing the
  local stack lifecycle.
- Don't open `http://localhost:8000` in the integrated browser — the owner
  tests in his external browser. Playwright tools only when explicitly asked.
- When something goes wrong, read the dev terminal output and fix; don't ask
  for screenshots.
- Read in 50–200 line chunks; parallelize independent file reads.
- Validate (tsc + pytest + build) ONCE at end of milestone.

## 8) Product goals and roadmap signals

- **Mobile is now a committed product goal.** Build an iOS-first native POC for
  hands-on iPhone testing, then extend the same mobile application to Android.
  Prefer React Native with Expo so iOS and Android share one TypeScript mobile
  application while the existing FastAPI/LangGraph backend remains authoritative.
  Reuse API contracts, state transitions, mutation semantics, identity, saved
  trips, chat, and view-model data; implement navigation, maps, secure storage,
  sharing, and presentation through platform adapters rather than a WebView.
- Mobile should reinterpret the planner for a phone, not squeeze the desktop
  four-pane workspace into a small screen. Preserve behavioral parity through
  native Plan, Map, Details, Assistant, Trips, and Account experiences. Account
  owns Google sign-in/out, preference editing, data refresh, and API diagnostics;
  network failures must be visible at the action surface rather than silent.
- Continuous learning is the moat. Every chat should leave the
  `learned_notes` / `past_trip_mentions` / `interests` / `dislikes` richer.
- The trip panel is the showroom. Anything that makes it feel more like an
  Airbnb listing page (photos, ratings, reviews, attractions) is on-brand.
- Booking handoffs through verified provider actions are a future direction; the
  current "finalize → manual booking" loop is fine for now.

## 9) When this file goes out of date

Update PRODUCT.md the same commit you change vision/scope/taste. If you
ship a feature that demands a new "Non-goal" entry, add it. If a redesign
changes the type/color/shape vocabulary, update §4. If a new run mode
appears, add it to §3. Stale PRODUCT.md = wasted onboarding time for the
next agent session.

