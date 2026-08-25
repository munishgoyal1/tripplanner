# Expected Behaviors

This is the authoritative source for externally observable product behavior.
`PRODUCT.md` owns intent and taste, `REQUIREMENTS.md` owns implementation status,
and this document owns what a user action must do. Tests are executable proof of
these rules; they do not replace or silently redefine them.

Report a regression with the behavior ID and only the facts that differ. For
example: `EB-FOCUS-001: Day 2, Jag Mandir, Stop 1; Map and Details did not update.`
That is enough to identify the full expected outcome below.

Change an expected behavior only with owner approval. A behavior change must
update this file and its linked tests in the same commit.

## Assistant planning

### EB-PLAN-001 - Complete a bounded new-trip planning turn

**Trigger:** Start a new trip, with the travel-profile smart-defaults checkbox
either enabled (the default) or disabled.

**Expected:**

- With smart defaults enabled, the Assistant builds from the request, saved
  preferences, trip history, and sensible inferences without an up-front confirmation
  gate except when the new-trip request omits who is travelling. Party composition
  is trip-specific, so that one compact review always includes editable Adults (13+),
  Children (0-12), and Trip group controls; saved family data may prefill but never
  silently enrolls everyone. Solo and family may be derived only when counts make
  them unambiguous; two adults are not assumed to be a couple. With smart defaults
  disabled, the same review may include other facts when an
  unresolved fact would materially improve the trip. Explicit prompt values and
  configured preferences are not asked again, while a destination-only trip never
  invents an origin. Any review preserves prefilled values and a skip/default path.
- Submitted party counts and relationship are persisted with the trip, used for
  whole-party budgets and provider occupancy, and shape lodging, pace, transport,
  meal timing, accessibility, and age-appropriate experiences.
- Asking to plan a destination other than the active trip runs the kickoff before the
  replacement trip is created, without requiring the words "new" or "another". A
  follow-up naming the active destination, and a day trip elsewhere, still skip the
  kickoff and leave the active trip in place.
- The Assistant batches hotel research for every overnight city in one parallel
  tool phase and accepts usable results when another city-specific query fails.
- While planning is active, the top command bar beside the trip selector shows
  the same friendly current phase and overall elapsed time as Assistant, including
  the typical 2–4 minute full-build expectation. It remains visible while answer
  text streams, then reports loading, authoritative completion, or failure. Stop,
  unmount, and active-trip changes clear in-flight status.
- Research is followed by one enriched full-plan persistence pass rather than
  repeated full-itinerary rewrites.
- A planning turn normally uses at most ten tool phases. A first planning turn
  that reaches that semantic budget continues until it has concrete lodging,
  complete journey edges, named meal coverage on substantial days, and positive
  cost evidence when the traveller requested a budget. Weather and other
  enrichment may remain deferred. Later turns stop at the budget and summarize
  the best persisted itinerary and any unresolved details honestly.
- Unexpected graph recursion exhaustion returns the persisted best-effort plan
  instead of discarding useful side effects behind a generic retry error.
- If a failed turn also cannot persist its interrupted transcript, the client
  warns that trip changes may still have applied instead of hiding the partial-save failure.

**Executable proof:**

- [`tests/test_parallel_tools.py`](../tests/test_parallel_tools.py) - `test_hotel_fallback_uses_successful_result_from_parallel_batch`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `keeps timely build progress in the top bar until the refreshed itinerary is ready`
- [`frontend/src/components/ChatPanel.test.tsx`](../frontend/src/components/ChatPanel.test.tsx) - `shows immediate and friendly progress while a turn is running`
- [`frontend/src/components/ChatPanel.test.tsx`](../frontend/src/components/ChatPanel.test.tsx) - `keeps progress visible while answer text streams`
- [`tests/test_parallel_tools.py`](../tests/test_parallel_tools.py) - `test_new_trip_does_not_rewrite_incomplete_researched_plan_twice`
- [`tests/test_parallel_tools.py`](../tests/test_parallel_tools.py) - `test_trip_agent_ends_with_summary_at_tool_phase_budget`
- [`tests/test_graph_policy.py`](../tests/test_graph_policy.py) - `test_first_turn_cannot_end_incomplete_before_phase_budget`
- [`tests/test_graph_policy.py`](../tests/test_graph_policy.py) - `test_weather_can_remain_deferred_when_first_turn_core_plan_is_complete`
- [`tests/test_sse_tool_summary.py`](../tests/test_sse_tool_summary.py) - `test_best_effort_plan_reply_reports_saved_plan_gaps`
- [`tests/test_usage.py`](../tests/test_usage.py) - `test_stream_surfaces_partial_turn_save_failure`

### EB-PLAN-002 - Recommend a fitting trip shape

**Trigger:** Start a new trip with or without an explicit duration.

**Expected:**

- Preferences load first, then the duration advisor runs before the one-step kickoff.
- Explicit dates or duration remain authoritative. Otherwise the kickoff uses an
  auditable recommendation derived from destination scope, likely matching places,
  daily capacity, desired free time, and learned pace outcomes.
- The recommendation is persisted with the trip. Accidentally sparse full days
  must be rebalanced with meaningful choices or labeled as intentional leisure;
  the planner does not add filler or silently shorten fixed dates.
- Cross-user aggregate insight is ignored unless its cohort and confidence pass
  deterministic privacy gates.

**Executable proof:**

- [`tests/test_planning_intelligence.py`](../tests/test_planning_intelligence.py)
- [`tests/test_trip_kickoff.py`](../tests/test_trip_kickoff.py) - `test_new_paris_trip_forces_prefilled_kickoff_after_duration_advice`
- [`tests/test_trip.py`](../tests/test_trip.py) - `test_create_trip_persists_planning_recommendation`

### EB-PLAN-003 - Keep long planning turns visibly active

**Trigger:** Submit a new-trip build, itinerary modification, or planner review.

**Expected:**

- Chat immediately shows a friendly phase, one overall elapsed clock, and a typical
  2–4 minute expectation for full builds. Real tool events produce timely flight,
  hotel, attraction, routing, review, and save updates without exposing tool names.
- The common command bar mirrors current work even when the Assistant pane is hidden.
  After two minutes it still shows the expected range and says not to refresh.
- Planning completion first reports that the refreshed itinerary is loading. A new
  itinerary is declared ready only after the trip view loads and invites inspection.
- Existing-trip changes summarize the refreshed authoritative mutation. Proposal-only
  reviews say the itinerary is unchanged; failed reloads retain the prior view and
  never claim that the new itinerary is ready. A rejected trip mutation receives one
  bounded correction attempt and is never narrated as successfully saved.

**Executable proof:**

- [`frontend/src/components/ChatPanel.test.tsx`](../frontend/src/components/ChatPanel.test.tsx) - `shows immediate and friendly progress while a turn is running`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `keeps timely build progress in the top bar until the refreshed itinerary is ready`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `summarizes an itinerary modification after its refreshed view loads`

## Public entry

### EB-PUBLIC-001 - Open the public landing route

**Trigger:** Navigate directly to `/`, including after entering the planner workspace.

**Expected:** The public landing experience opens regardless of authentication or
prior visits. Choosing Plan mine or Skip to the app changes the address to
`/planner` while preserving `/` in browser history. Back returns to the landing
experience, and Plan mine carries its request into the Assistant as before. The
legacy `/welcome` and `/welcome/` addresses replace themselves with `/`.

**Executable proof:**

- [`frontend/src/publicEntry/Root.test.tsx`](../frontend/src/publicEntry/Root.test.tsx)

### EB-PUBLIC-002 - Render one internally consistent regional demo

**Trigger:** Open the public entry with a supported display country/region and
currency, or change the display country while the public entry is visible.

**Expected:** The page renders a bundled regional artifact immediately, then may
replace it only with one complete, schema-valid artifact from `/public/demo-run`.
Trip and decisions always come from the same version. Cosmos failure, a missing
manifest, or invalid remote content leaves the bundled artifact visible. Routes,
entities, hotels, and money remain compatible with the selected market; India
starts in Mumbai and contains no London or Portuguese-route entities. A supported
country/region takes precedence over a stale currency during preference changes,
and the matching bundled artifact replaces the prior one immediately. Country
selects the market; the display currency only re-prices that market's money, so
India with USD still shows the Rajasthan run with dollar amounts. Every
regional artifact stores four to six complete days with matching completion
receipts.

**Executable proof:**

- [`tests/test_public_demo.py`](../tests/test_public_demo.py)
- [`frontend/src/publicEntry/PublicEntry.test.tsx`](../frontend/src/publicEntry/PublicEntry.test.tsx)

### EB-PUBLIC-003 - Keep profile and workspace entry actions separate

**Trigger:** Select the profile chip in the public-entry masthead.

**Expected:** The profile chip opens the complete shared Account settings hub
without leaving `/`. Choosing any settings destination, including Travel
Profile, stays on `/`. Entering the planner happens only through Plan mine
or the separate Skip to the app action.

**Executable proof:**

- [`frontend/src/publicEntry/PublicEntry.test.tsx`](../frontend/src/publicEntry/PublicEntry.test.tsx)
- [`frontend/src/components/AccountSettingsController.test.tsx`](../frontend/src/components/AccountSettingsController.test.tsx)

### EB-PUBLIC-004 - Open the planner workspace directly

**Trigger:** Navigate directly to `/planner`, the permanent address of the main
app workspace.

**Expected:** The workspace opens immediately for every visitor without consulting
the saved-trip list. Plan mine and Skip to the app navigate to `/planner`, and
`/planner/` behaves the same as `/planner`. A local audit inspection link also
targets `/planner` and opens its exact record-backed representative trip. If the
record cannot be resolved, the link remains intact for diagnosis instead of
canonicalizing to an empty workspace. When both record and saved-trip IDs are
present, the immutable audit record wins so a stale local copy cannot replace
the evidence that produced the finding.

**Executable proof:**

- [`frontend/src/publicEntry/Root.test.tsx`](../frontend/src/publicEntry/Root.test.tsx)
- [`frontend/inspector/src/report.test.ts`](../frontend/inspector/src/report.test.ts)
- [`tests/test_request_security.py`](../tests/test_request_security.py)

## Planner workspace

### EB-DEAL-001 - Compare and recheck exact finalized-trip offers

**Trigger:** Open a trip whose persisted decisions contain equivalent provider
offers, or a finalized unbooked trip whose recorded quote has expired.

**Expected:**

- Offers compare only when provider-neutral room/rate or flight-itinerary identity
  matches and all mandatory costs are known. Unknown fees suppress savings claims.
- A consented portal benefit applies only from numeric public terms and returns
  program/card labels plus the terms link; card numbers are never consumed or shown.
- Expired quotes for finalized unbooked items appear as explicit recheck work.
  Rendering performs no provider request. Selecting Recheck prices verifies an
  exact flight offer or re-searches a stay only with its original occupancy,
  nationality, dates, property, room, board, and refundability context.
- Recheck results report movement or unavailability, refresh quote provenance,
  and never replace the selected item. A stale client revision is rejected.
- Grounded forecast heat/rain and structured place or activity-provider duration
  evidence may add advisory effort notes. Missing evidence remains silent and
  effort never blocks.

**Executable proof:**

- [`tests/test_trip_cost_ledger.py`](../tests/test_trip_cost_ledger.py)
- [`tests/test_price_recheck.py`](../tests/test_price_recheck.py)
- [`tests/test_trip_guard.py`](../tests/test_trip_guard.py)
- [`tests/test_trip_view.py`](../tests/test_trip_view.py)
- [`frontend/src/components/TripSnapshot.test.tsx`](../frontend/src/components/TripSnapshot.test.tsx)

### EB-VERIFY-001 - Recheck itinerary place facts

**Trigger:** Expand Plan checks and select Recheck place facts.

**Expected:**

- The planner force-refreshes each unique hotel, attraction, and meal through the
  configured structured place provider, with bounded parallelism, and rebuilds
  the verification certificate from the refreshed cache.
- A successful check stores only stable place identity, operating status, and
  regular weekly hours. It reports material differences from the prior check;
  ratings, reviews, photos, and transient open-now state never appear as changes.
- One unavailable place does not abort the trip check or erase previously known
  facts. The certificate names places it could not refresh and says the last
  known facts were retained.
- When fresh web search is configured, the same explicit action performs one
  bounded search for seasonal, renovation, rehabilitation, or unusual closure
  notices. A result is shown only when it names an itinerary place and includes
  closure language. It remains a source-linked advisory and never becomes a
  deterministic contradiction or silently changes the itinerary.
- No provider refresh runs merely because the certificate rendered. Older trips
  without freshness snapshots remain readable and show no fabricated checked time.

**Executable proof:**

- [`tests/test_trip_freshness.py`](../tests/test_trip_freshness.py)
- [`tests/test_places_cache.py`](../tests/test_places_cache.py) - `test_refresh_details_preserves_known_facts_when_lookup_fails`
- [`frontend/src/components/TripVerificationCard.test.tsx`](../frontend/src/components/TripVerificationCard.test.tsx)

### EB-FEEDBACK-001 - Record lightweight trip feedback

**Trigger:** With an active trip, select the toolbar thumbs-up or thumbs-down action,
or open Rate and add optional stars or a comment.

**Expected:** One thumb tap is a complete saved submission. Stars and a comment may
amend that submission while its popover remains open. A later thumb tap creates another
append-only submission, and the quiet sent count never blocks repeat feedback. Desktop
keeps the compact control in the workspace toolbar; mobile keeps the thumbs pair directly
reachable without covering trip content. Deleting a trip deletes its feedback.

**Executable proof:**

- [`tests/test_trip_feedback.py`](../tests/test_trip_feedback.py)
- [`frontend/src/components/TripFeedbackControl.test.tsx`](../frontend/src/components/TripFeedbackControl.test.tsx)

### EB-WORKSPACE-001 - Arrange visible desktop panes freely

**Trigger:** Toggle Itinerary, Map, Details, or Assistant from the desktop
command bar, use a pane-local Hide action, or resize a separator.

**Expected:** Every pane is independently visible or hidden, including an
all-hidden workspace. The command bar remains available to restore any pane, and
the chosen combination persists locally across reloads. Visible docked panes may
grow to all space not reserved for the minimum usable widths of visible siblings;
there is no separate maximum-width cap. Separators appear only between panes that
are currently shown and expose their actual adjustable range to assistive input.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `lets panes use available width and allows every pane to be hidden and restored`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `supports every desktop pane visibility combination`

### EB-TRIPS-001 - Delete selected saved trips

**Trigger:** Open the saved-trip menu, choose Delete trips, select one or more
trips, and confirm deletion.

**Expected:** Delete mode shows one checkbox per saved trip, Select all/Clear all,
the selected count, Cancel, and a count-aware delete action. Selecting one trip
deletes only that trip; selecting every trip offers Delete all. One confirmation
covers the selected set, each deleted trip also loses its related chat history,
and the workspace refreshes after the operation. Outside delete mode, selecting
a trip continues to switch to it.

**Executable proof:**

- [`frontend/src/components/TripSwitcher.test.tsx`](../frontend/src/components/TripSwitcher.test.tsx) - `deletes only the checked trip`
- [`frontend/src/components/TripSwitcher.test.tsx`](../frontend/src/components/TripSwitcher.test.tsx) - `selects and deletes all saved trips`

### EB-FOCUS-001 - Focus one itinerary occurrence

**Trigger:** Select a place stop in Itinerary, or invoke its Map action. The
identity is kind, place name, day, and stop position. For example, selecting
Jag Mandir at Day 2, Stop 1 identifies that occurrence rather than merely every
place named Jag Mandir. Transport terminal rows and markers invoke exact focus
and open the terminal as an inspectable place.

**Expected:**

- Map opens, selects the marker for that exact occurrence, and zooms to level 15.
- Details opens and shows that place, including itinerary-only places not already
  in the selected-place collection.
- Airport, railway-station, bus-stand, and other enriched terminal focus pans and
  zooms to the requested day occurrence at level 15 and opens Details with
  available Places photos, rating, reviews, address, summary, and website. The
  itinerary alias remains the focus identity when it differs from the
  provider-canonical terminal name.
- Timed train and bus journeys expose departure terminal, travel leg, and arrival
  terminal rows. Departure rows include configurable boarding buffers; terminal
  rows remain operational and non-bookable. Their timing labels identify railway
  stations and bus stands rather than describing every departure as an airport arrival.
- Itinerary, Map, and Details retain the same day and stop after the view refresh.
- Repeating the same action reapplies focus after manual map movement or filtering.
- A failed refresh leaves the previous usable view in place and reports the error.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `keeps an itinerary-only stop focused in its map occurrence and details after refresh`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `preserves the itinerary day when focusing a repeated hotel`
- [`frontend/src/api.test.ts`](../frontend/src/api.test.ts) - `sends the exact itinerary occurrence with place focus`
- [`tests/test_trip_view_api.py`](../tests/test_trip_view_api.py) - `test_trip_view_preserves_exact_itinerary_occurrence`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `uses the requested occurrence day for a repeated hotel`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `zooms an airport like any exact itinerary stop`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `opens rich inspection for rail and bus terminal markers`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `opens airport details and keeps its exact map occurrence focused`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_airport_focus_exposes_place_details_and_terminal_occurrence`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_map_view_connects_flight_airports_to_destination_stay`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_timed_surface_transport_adds_terminal_buffer_stops`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_focus_zooms_single_item`

### EB-FOCUS-002 - Focus a day or the whole trip

**Trigger:** Select a day scope from Itinerary or Map, or select All days.

**Expected:** Day focus clears exact-place focus and aligns Itinerary to that day
summary. The map details tile changes from any previously selected place to the
day title/destination with schedule and route context. Ordinary days fit their complete circuit. Transfer days keep the full
ordered inter-city geometry visible but fit the useful destination-local circuit,
or the origin-local circuit when no substantive destination stop remains. All
road-transfer days retain the full origin-to-destination drive in day focus so
the starting city or saved home area, on-route scenic or meal waypoints, and
destination stay remain visible. Every waypoint connector retains the same
dotted Drive treatment rather than reverting to a local taxi leg. Drive, car,
private-car, road-journey, and road-transfer labels with directional
endpoints all normalize to the same clickable route action; display wording
must not determine whether the route works. Grounded `distance_km` and
`duration_min` values are persisted on the transfer stop and remain authoritative
in Itinerary and Map; a waypoint route allocates those exact totals across its
ordered drive legs instead of replacing them with straight-line estimates. All
days clears exact-place and day focus, fits all circuits and dotted flight arcs
between every airport pair, aligns Itinerary to the trip summary, and marks Trip
Snapshot as selected. The selected day summary receives the same exclusive
aggregate-selection treatment. Trip Snapshot itself invokes All days. Neither
action requests place Details. A newly created or selected trip always starts in
All days even when its day numbers overlap the previously viewed trip. Ordinary
content refreshes preserve a deliberate day selection. Focus controls paint
before map overlays are reconstructed, and rapid focus changes discard
superseded queued redraws so the latest requested item, day, route, or All days
scope wins.

Selecting an inter-city flight or transport row is a route action rather than
place focus. A first-class Drive or Bus journey opens Map on its own stable road circuit and
frames only that circuit's ordered source, intermediate stops, destination,
legs, and authoritative route metrics. Scenic and meal waypoints receive distinct
route markers, and the selected-route context summarizes those breaks plus total
time and distance. Destination-local activities after arrival/check-in and other
unrelated stops or legs from the same
day remain outside the focused circuit. Legacy transport rows without a circuit
identity continue to frame the full ordered day route. Neither action opens
place Details or replaces destination-local framing for ordinary day-header
focus.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `gives a map day chip the same aggregate circuit focus as an itinerary day header`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `shows all circuits and returns itinerary focus to the trip summary`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `maps a Trip Snapshot click to the shared All days focus`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `restores All days after an externally focused day`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `defers and cancels superseded overlay redraws`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `defaults a newly selected trip to All days even when its day numbers overlap`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `marks the focused day circuit as selected`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `uses Trip Snapshot as the selected All days map control`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `frames an itinerary day circuit without converting it into place focus`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `frames the complete inter-city route without opening place details`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `fits every endpoint in the requested inter-city route`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `fits only the ordered points in the requested drive circuit`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `summarizes a focused road circuit and its useful breaks`
- [`frontend/src/components/map/overlaySync.test.ts`](../frontend/src/components/map/overlaySync.test.ts) - `renders only the selected drive circuit pins, legs, and labels`
- [`frontend/src/components/map/overlaySync.test.ts`](../frontend/src/components/map/overlaySync.test.ts) - `renders a selected bus road circuit from its own ordered breaks`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `derives aggregate day context instead of a stale place selection`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `draws all flight arcs and focuses a repeated airport alias on its requested day`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `routes legacy drive and toy-train rows to the complete day route`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `forwards a first-class drive circuit when its travel row is clicked`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_drive_labels_share_transport_normalization_and_route_endpoints`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_northeast_drives_keep_waypoints_and_hotels_in_map_circuits`

### EB-ITIN-001 - Read a multi-city transition day chronologically

**Trigger:** View an itinerary day that checks out from one hotel, travels to
another city, and checks in at a different hotel.

**Expected:** Check out, every journey stop, destination check-in, and remaining
destination plans appear once in one ordered transition spine. The two hotels
remain distinct `H1` and `H2` endpoints. A repeated return to the destination
hotel, including harmless locality spelling, abbreviated property names, and
generic Hotel/Resort variants,
shares one `H`
identity and appears after the final plan as a compact chronological endpoint carrying
its incoming travel and return time, without duplicating stay controls or hotel
details. When a persisted transfer day omits its origin stay, the prior day's
active hotel is its first endpoint. Mode metadata such as `car` normalizes the
saved leg into a clickable inter-city route even without a model-authored `Drive:`
prefix. Hotel identity resolution precedes fuzzy partial-name matching, so an
aliased stay remains both endpoints of an ordinary day's map circuit even when
other selected hotels share generic name fragments. The itinerary does not pair the hotels as cards or split the day into
Journey and After check-in sections.

**Executable proof:**

- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `shows a multi-city transfer as one chronological spine without changing stop identity`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `keeps the hotel return endpoint independently addressable`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `treats a trailing hotel locality as the same stay`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_timed_road_transfer_estimates_destination_hotel_check_in`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_road_transfer_estimates_duration_arrival_and_hotel_check_in`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_road_transfer_without_checkout_estimates_duration_but_not_check_in`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_untimed_road_transfer_does_not_invent_hotel_check_in`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_transfer_day_starts_from_prior_rameswaram_hotel`

### EB-ITIN-002 - Use conservative local transfer modes

**Trigger:** Estimate a local route from straight-line distance without verified
public-transit evidence.

**Expected:** Legs up to 1.5 km may be shown as Walk. A 3 km leg is shown as Taxi,
and Metro is never inferred from distance alone.

**Executable proof:**

- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_local_route_uses_taxi_for_three_kilometres`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_local_route_keeps_short_walks_walkable`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_local_route_does_not_invent_unverified_metro_service`

### EB-ITIN-003 - Do not invent a hotel return without an outing

**Trigger:** View an itinerary day whose only planned stop is the hotel.

**Expected:** The hotel appears once as a `Stay` row. The day does not show a
separate departure or return endpoint because the traveler has no planned outing.

**Executable proof:**

- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_structured_hotel_only_day_does_not_add_return_endpoint`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `shows one stay row without a return for a hotel-only day`

### EB-ITIN-004 - Return after an arrival-day outing

**Trigger:** Arrive by inter-city transport, check in to the destination hotel,
then visit one or more local places that day.

**Expected:** When the return route can be grounded, the local plan ends with a
separate return to the destination hotel, including its incoming travel and
estimated return time. A bare arrival/check-in does not add a return, and neither
an ungrounded route nor inter-city travel after the hotel invents one. The
destination check-in time is estimated from any grounded arrival terminal -
airport, railway station, or bus stand - plus its exit buffer and the timed
transfer to the hotel, so a mid-day check-in is not left blank.

**Executable proof:**

- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_arrival_day_local_outing_returns_to_destination_hotel`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_arrival_day_does_not_invent_return_without_route_coordinates`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_structured_itinerary_preserves_arrival_and_departure_flights`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_arrival_hotel_time_requires_airport_transfer_evidence`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_train_arrival_estimates_destination_hotel_check_in`

### EB-ITIN-005 - Keep daily hotels synchronized across views

**Trigger:** View a non-transfer day whose itinerary carries forward the active
hotel while its prose mentions other selected hotels as alternatives, or replace
a city-specific hotel through Assistant in a multi-city or regional trip.

**Expected:** Itinerary and Map use the same rendered hotel for that day's route.
Prose-only hotel alternatives do not replace or join the active stay. A genuine
multi-hotel transfer day keeps its distinct hotel endpoints. A replacement hotel
is valid when its city is evidenced by the itinerary even if the trip destination
is a broader region, and a successful save updates selected hotels and itinerary
hotel anchors together.

**Executable proof:**

- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_map_view_uses_rendered_stay_over_prose_hotel_alternatives`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_map_view_carries_forward_hotel_after_transition`
- [`tests/test_trip.py`](../tests/test_trip.py) - `test_update_trip_plan_accepts_hotel_in_evidenced_itinerary_city`

### EB-ITIN-006 - Include complete round-trip transport

**Trigger:** Create or enrich a trip whose origin differs from its destination,
including a nearby trip such as Bangalore to Mysore.

**Expected:** The arrival day includes a flight or explicit road, bus, or train
journey from origin to destination before check-in. The departure day includes
the corresponding journey back to origin after checkout. The itinerary names
the mode and endpoints; destination-local taxi travel does not count as either
inter-city edge. A road journey that starts the day renders the saved home area
or origin city as a separate `O` endpoint, labels the drive as departing from
that origin, formats long durations in hours and minutes, and includes planned
snack/rest breaks using saved or inferred driving preferences. Its insight says
that the same taxi or self-drive vehicle continues through authored waypoints,
calls out scenic breaks, and prompts a meal stop on a long drive when none is
authored. An explicit meal remains a separately focusable itinerary waypoint.
For Drive and Bus transfers, worthwhile researched scenic and named meal breaks
are explicit ordered stops before the destination terminal/check-in. A fixed bus
service includes only real scheduled or feasible breaks and never implies a
private detour. The itinerary and Map use the same order, while destination-local
sightseeing begins after arrival and remains outside the road circuit.
Natural labels such as `Bagdogra to Gangtok drive` and `Drive to Darjeeling`
remain clickable route actions without requiring a `Drive:` prefix. Saving an
incomplete plan returns an actionable correction.

**Executable proof:**

- [`tests/test_trip.py`](../tests/test_trip.py) - `test_planning_completion_requires_round_trip_intercity_transport`
- [`tests/test_trip.py`](../tests/test_trip.py) - `test_create_trip_plan_defaults_origin_from_saved_home_area`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_city_origin_drive_includes_origin_and_rest_break`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_northeast_drives_keep_waypoints_and_hotels_in_map_circuits`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_bus_transfer_builds_separate_road_circuit_with_route_breaks`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_mode_tagged_gangtok_flights_expand_with_both_airports`
- [`tests/test_trip.py`](../tests/test_trip.py) - `test_prompt_requires_grounded_ordered_road_breaks`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `shows a road-trip city origin as a non-bookable O marker`

### EB-ITIN-007 - Filter itinerary structure across panes

**Trigger:** Toggle Flights, Inter-city Road, Inter-city Train, or Hotels beside
the Itinerary pane title.

**Expected:** Itinerary and Map immediately show the union of all selected
categories. An empty selection shows the complete trip. Unmatched itinerary days
disappear without renumbering days or stop identities, and Trip Snapshot remains
visible. Map results retain complete selected journey endpoints, connectors, and
road waypoints while excluding unrelated places, suggestions, local taxis, and
synthetic hotel connectors. Flight mode is sufficient to retain mapped arrival
and departure days when a legacy leg omits its optional inter-city marker. A
filter change clears stale place/route focus and returns Map to All days.
Selecting another trip clears the filters.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `shares unioned itinerary filters with the map`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `filters by union while preserving the original stop position`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `keeps both airport endpoints when filtering to flights`
- [`frontend/src/lib/itineraryFilters.test.ts`](../frontend/src/lib/itineraryFilters.test.ts) - `keeps selected transport endpoints and complete drive waypoints on the map`
- [`frontend/src/lib/itineraryFilters.test.ts`](../frontend/src/lib/itineraryFilters.test.ts) - `keeps arrival and departure flight days when legacy legs omit intercity`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `shows arrival and departure days for legacy flight legs`
- [`frontend/src/components/map/overlaySync.test.ts`](../frontend/src/components/map/overlaySync.test.ts) - `does not invent fallback connectors for an explicitly filtered day`

### EB-MAP-001 - Distinguish multiple hotels in one day

**Trigger:** View a day whose ordered map route contains two or more distinct
hotels.

**Expected:** The unique hotels are labeled `H1`, `H2`, and so on in route order
in both Itinerary and Map. A repeated return to the same hotel does not create
another number. A direct hotel-to-hotel leg is dotted in the day's circuit
color. A day with one unique hotel retains the plain `H` marker. Equivalent
hotel spellings share one geocoded pin and all of its day/stop occurrences;
selecting the hotel zooms to that pin for the requested occurrence.

**Executable proof:**

- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `numbers two hotels in their same-day route order`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `matches an abbreviated hotel alias only at its requested occurrence`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `keeps different hotel endpoints as explicit checkout and checkin rows`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `distinguishes local, road, bus, rail, and flight route geometry`

### EB-MAP-002 - Distinguish inter-city transport on the map

**Trigger:** View a mapped inter-city flight, road transfer, bus, or train leg.

**Expected:** Its connector is dotted and carries a small transport glyph at its
midpoint in All days, selected-day, and individual-route focus. Selected-day route
labels remain offset from that midpoint so they do not cover the glyph. Flight
connectors are blue with an airplane, road connectors are black with a car or bus
as applicable, and train connectors are gray with a train. Local route legs retain
their day color and do not gain an inter-city transport glyph. A road trip that
starts from a city/home-area point connects that `O` endpoint to the first
destination place; both endpoints remain in the day circuit and route focus.
Clicking a route-shaped drive or toy-train itinerary row frames the complete
dotted day route, including for legacy rows persisted with a generic kind.

**Executable proof:**

- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `distinguishes local, road, bus, rail, and flight route geometry`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `draws all flight arcs and focuses a repeated airport alias on its requested day`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `routes legacy drive and toy-train rows to the complete day route`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_map_view_connects_city_origin_to_hotel_for_road_trip`

### EB-STATE-001 - Keep planner surfaces synchronized

**Trigger:** A focus, selection, trip mutation, identity change, or overlapping
refresh updates shared planner state.

**Expected:** Itinerary, Map, Details, and Assistant use one current trip revision
and focus owner. A stale or aborted response cannot overwrite a newer trip,
identity, mutation, or focus state. Focus-only navigation does not reload or
rebuild unrelated itinerary data. An intercity route exposes the same ordered
terminals and connections in Itinerary and Map in both directions; an all-days
map separates outbound and return paths that reuse the same terminal pair.
Destination Guide remains scoped to the current trip destination rather than
inventing guide content for the home city or a connection airport.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `keeps the removed place focused when an older refresh resolves later`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `does not reload itinerary data for focus-only navigation`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `shows an already-loaded focused place before its refresh completes`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_connecting_round_trip_keeps_itinerary_and_map_terminals_in_sync`
- [`frontend/src/components/map/routeDerivations.test.ts`](../frontend/src/components/map/routeDerivations.test.ts) - `separates outbound and return while keeping both attached to the terminals`

## Account settings

### EB-ACCOUNT-001 - Keep account destinations in one hub

**Trigger:** Open Account settings from the welcome page, workspace, or another
application page and choose Profile and sign-in, Travel Profile, Travel documents,
Analytics preferences, or Privacy and data.

**Expected:** Every entry point opens the same Root-owned Account settings hub
without navigating away from the current page. The destination opens inside the
hub rather than as a detached settings surface. Travel Profile and Analytics
remain editable there. When analytics is configured and no choice exists,
first-run consent still appears separately; revisiting Analytics in Account does
not recreate that prompt.

**Executable proof:**

- [`frontend/src/components/AccountSettingsController.test.tsx`](../frontend/src/components/AccountSettingsController.test.tsx)
- [`frontend/src/components/AccountSettingsHub.test.tsx`](../frontend/src/components/AccountSettingsHub.test.tsx) - `presents the five shared account destinations`
- [`frontend/src/components/AccountSettingsHub.test.tsx`](../frontend/src/components/AccountSettingsHub.test.tsx) - `keeps travel profile and analytics inside the account settings hub`
- [`frontend/src/components/AnalyticsConsent.test.tsx`](../frontend/src/components/AnalyticsConsent.test.tsx) - `shows the bottom prompt only for first-run consent when analytics is configured`

### EB-ACCOUNT-002 - Apply supported display currencies to itinerary costs

**Trigger:** Change Display currency to a supported currency such as CNY while an
itinerary is visible in the workspace.

**Expected:** Visible itinerary and trip-summary costs immediately re-render in
the selected currency using the shared display conversion table. The selector
offers only currencies that table can convert, so a selection never silently
falls back to the source currency.

**Executable proof:**

- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `updates itinerary costs when the display currency changes to CNY`
- [`frontend/src/lib/displayPreferences.test.ts`](../frontend/src/lib/displayPreferences.test.ts)

### EB-ACCOUNT-003 - Choose country, language, and currency from fixed lists

**Trigger:** Open Account settings and set Country or region, Language, or
Display currency.

**Expected:** Country and language are chosen from fixed standard lists rather
than typed as free text, and currency offers only convertible currencies. A
previously typed country such as `India` maps onto its standard entry instead of
being lost. Country and language decide the regional example trip, dates, and
distance/temperature units; currency independently decides money, so either can
change without disturbing the other. Interface text remains English.

**Executable proof:**

- [`frontend/src/lib/displayPreferences.test.ts`](../frontend/src/lib/displayPreferences.test.ts)
- [`frontend/src/publicEntry/PublicEntry.test.tsx`](../frontend/src/publicEntry/PublicEntry.test.tsx) - `keeps the country trip while pricing it in the chosen currency`

## UX Labs

### EB-LAB-001 - Preserve every Lab review and implementation

**Trigger:** Open any Lab, inspect an option, revise its handoff notes, choose any
lifecycle state, and save or re-save the handoff.

**Expected:** Every option and lifecycle state remains selectable through visible
state buttons at any time;
choosing an option does not silently change state. Every save appends an immutable
handoff version containing the selected option, exact notes, state, version number,
and recorded time. Existing single-record selections migrate to handoff version 1,
including Lab 20's saved Option B. Discarding changes state without deleting review
history. Agent-side implementation, park, discard, completion, and reopen actions
append the same choice, exact notes, resulting state, version number, and time. When
an agent implementation is saved as Implemented - To be reviewed, a
separate immutable implementation record links to its handoff version and preserves
the agent's implementation evidence. Every implemented version remains visible under
What was implemented with its selected option, exact saved notes, version number,
recorded time, and implementation summary. Handoff and implementation versions are
shown newest first. One final summary lists every implemented
option and its notes. Saving shows an explicit confirmation naming the selected option
and saved handoff version and cannot remain indefinitely in a Saving state.
Lab implementation sandboxes retain an explicit Lab ID. Ambiguous handoff notes or
scope are resolved with the owner in that sandbox chat before implementation.
After each coherent changed iteration reaches a healthy sandbox run, its concrete
change and validation summary append another Implemented review version; startup
alone does not create history. Verified promotion requires the exact sandbox commit
to have a healthy recorded iteration, then appends a Completed version before the
sandbox is discarded.
The permanent Lab number appears explicitly in the detail page's top header area
and in its HTML filename. The top area shows the authoritative lifecycle status, includes its state
date when recorded, updates after a save, and reports unavailable state rather
than guessing.

**Executable proof:**

- [`frontend/labs/src/shared/DecisionCapture.test.tsx`](../frontend/labs/src/shared/DecisionCapture.test.tsx) - `keeps every option browsable after loading an implemented choice`
- [`frontend/labs/src/shared/DecisionCapture.test.tsx`](../frontend/labs/src/shared/DecisionCapture.test.tsx) - `starts a re-implementation handoff without losing the completed direction`
- [`frontend/labs/src/shared/DecisionCapture.test.tsx`](../frontend/labs/src/shared/DecisionCapture.test.tsx) - `shows exact notes and a final summary for every implementation version`
- [`frontend/labs/src/shared/DecisionCapture.test.tsx`](../frontend/labs/src/shared/DecisionCapture.test.tsx) - `allows any state without requiring owner-entered implementation evidence`
- [`frontend/labs/feedback-plugin.test.ts`](../frontend/labs/feedback-plugin.test.ts) - `turns an existing Lab 20 choice into auditable version one`
- [`tests/test_record_lab_implementation.py`](../tests/test_record_lab_implementation.py) - `records implementation against latest handoff`
- [`tests/test_record_lab_implementation.py`](../tests/test_record_lab_implementation.py) - `records each successful implementation iteration`
- [`tests/test_record_lab_implementation.py`](../tests/test_record_lab_implementation.py) - `sandbox records linked iterations and both promotion paths`
- [`frontend/labs/src/shared/LabNavigation.test.tsx`](../frontend/labs/src/shared/LabNavigation.test.tsx) - `shows the permanent Lab number in detail-page navigation`
- [`frontend/labs/src/shared/LabScope.test.tsx`](../frontend/labs/src/shared/LabScope.test.tsx) - `shows authoritative status in the top area and updates after a save`
