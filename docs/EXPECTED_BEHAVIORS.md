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

**Trigger:** Submit or skip the structured kickoff for a new trip and let the
Assistant build its first proposal.

**Expected:**

- The Assistant batches hotel research for every overnight city in one parallel
  tool phase and accepts usable results when another city-specific query fails.
- Research is followed by one enriched full-plan persistence pass rather than
  repeated full-itinerary rewrites.
- A planning turn uses at most ten tool phases. Reaching that semantic budget
  disables further tools and produces an honest summary of the best persisted
  itinerary and any unresolved details.
- Unexpected graph recursion exhaustion returns the persisted best-effort plan
  instead of discarding useful side effects behind a generic retry error.

**Executable proof:**

- [`tests/test_parallel_tools.py`](../tests/test_parallel_tools.py) - `test_hotel_fallback_uses_successful_result_from_parallel_batch`
- [`tests/test_parallel_tools.py`](../tests/test_parallel_tools.py) - `test_new_trip_does_not_rewrite_incomplete_researched_plan_twice`
- [`tests/test_parallel_tools.py`](../tests/test_parallel_tools.py) - `test_trip_agent_ends_with_summary_at_tool_phase_budget`
- [`tests/test_sse_tool_summary.py`](../tests/test_sse_tool_summary.py) - `test_best_effort_plan_reply_reports_saved_plan_gaps`

## Planner workspace

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
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_focus_zooms_single_item`

### EB-FOCUS-002 - Focus a day or the whole trip

**Trigger:** Select a day scope from Itinerary or Map, or select All days.

**Expected:** Day focus clears exact-place focus and aligns Itinerary to that day
summary. Ordinary days fit their complete circuit. Transfer days keep the full
ordered inter-city geometry visible but fit the useful destination-local circuit,
or the origin-local circuit when no substantive destination stop remains. All
days clears exact-place and day focus, fits all circuits and dotted flight arcs
between every airport pair, aligns Itinerary to the trip summary, and marks Trip
Snapshot as selected. The selected day summary receives the same exclusive
aggregate-selection treatment. Trip Snapshot itself invokes All days. Neither
action requests place Details.

Selecting an inter-city flight or transport row is a route action rather than
place focus: Map opens and frames the full ordered day route so both source and
destination and their connector remain visible. It does not open place Details
or replace destination-local framing for ordinary day-header focus.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `gives a map day chip the same aggregate circuit focus as an itinerary day header`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `shows all circuits and returns itinerary focus to the trip summary`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `maps a Trip Snapshot click to the shared All days focus`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `restores All days after an externally focused day`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `marks the focused day circuit as selected`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `uses Trip Snapshot as the selected All days map control`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `frames an itinerary day circuit without converting it into place focus`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `frames the complete inter-city route without opening place details`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `fits every endpoint in the requested inter-city route`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `draws all flight arcs and focuses a repeated airport alias on its requested day`

### EB-ITIN-001 - Read a multi-city transition day chronologically

**Trigger:** View an itinerary day that checks out from one hotel, travels to
another city, and checks in at a different hotel.

**Expected:** Check out, every journey stop, destination check-in, and remaining
destination plans appear once in one ordered transition spine. The two hotels
remain distinct `H1` and `H2` endpoints. A repeated return to the destination
hotel appears after the final plan as a compact chronological endpoint carrying
its incoming travel and return time, without duplicating stay controls or hotel
details. The itinerary does not pair the hotels as cards or split the day into
Journey and After check-in sections.

**Executable proof:**

- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `shows a multi-city transfer as one chronological spine without changing stop identity`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `keeps the hotel return endpoint independently addressable`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_timed_road_transfer_estimates_destination_hotel_check_in`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_road_transfer_estimates_duration_arrival_and_hotel_check_in`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_road_transfer_without_checkout_estimates_duration_but_not_check_in`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_untimed_road_transfer_does_not_invent_hotel_check_in`

### EB-ITIN-002 - Use conservative local transfer modes

**Trigger:** Estimate a local route from straight-line distance without verified
public-transit evidence.

**Expected:** Legs up to 1.5 km may be shown as Walk. A 3 km leg is shown as Taxi,
and Metro is never inferred from distance alone.

**Executable proof:**

- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_local_route_uses_taxi_for_three_kilometres`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_local_route_keeps_short_walks_walkable`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_local_route_does_not_invent_unverified_metro_service`

### EB-ITIN-003 - Include complete round-trip transport

**Trigger:** Create or enrich a trip whose origin differs from its destination,
including a nearby trip such as Bangalore to Mysore.

**Expected:** The arrival day includes a flight or explicit road, bus, or train
journey from origin to destination before check-in. The departure day includes
the corresponding journey back to origin after checkout. The itinerary names
the mode and endpoints; destination-local taxi travel does not count as either
inter-city edge. Saving an incomplete plan returns an actionable correction.

**Executable proof:**

- [`tests/test_trip.py`](../tests/test_trip.py) - `test_planning_completion_requires_round_trip_intercity_transport`

### EB-MAP-001 - Distinguish multiple hotels in one day

**Trigger:** View a day whose ordered map route contains two or more distinct
hotels.

**Expected:** The unique hotels are labeled `H1`, `H2`, and so on in route order
in both Itinerary and Map. A repeated return to the same hotel does not create
another number. A direct hotel-to-hotel leg is dotted in the day's circuit
color. A day with one unique hotel retains the plain `H` marker.

**Executable proof:**

- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `numbers two hotels in their same-day route order`
- [`frontend/src/components/ItineraryPanel.test.tsx`](../frontend/src/components/ItineraryPanel.test.tsx) - `keeps different hotel endpoints as explicit checkout and checkin rows`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `distinguishes local, road, bus, rail, and flight route geometry`

### EB-MAP-002 - Distinguish inter-city transport on the map

**Trigger:** View a mapped inter-city flight, road transfer, bus, or train leg.

**Expected:** Its connector is dotted and carries a small transport glyph at its
midpoint in All days, selected-day, and individual-route focus. Selected-day route
labels remain offset from that midpoint so they do not cover the glyph. Flight
connectors are blue with an airplane, road connectors are black with a car or bus
as applicable, and train connectors are gray with a train. Local route legs retain
their day color and do not gain an inter-city transport glyph.

**Executable proof:**

- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `distinguishes local, road, bus, rail, and flight route geometry`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `draws all flight arcs and focuses a repeated airport alias on its requested day`

### EB-STATE-001 - Keep planner surfaces synchronized

**Trigger:** A focus, selection, trip mutation, identity change, or overlapping
refresh updates shared planner state.

**Expected:** Itinerary, Map, Details, and Assistant use one current trip revision
and focus owner. A stale or aborted response cannot overwrite a newer trip,
identity, mutation, or focus state. Focus-only navigation does not reload or
rebuild unrelated itinerary data.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `keeps the removed place focused when an older refresh resolves later`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `does not reload itinerary data for focus-only navigation`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `shows an already-loaded focused place before its refresh completes`

## Account settings

### EB-ACCOUNT-001 - Keep account destinations in one hub

**Trigger:** Open Account settings and choose Profile and sign-in, Travel Profile,
Analytics preferences, or Privacy and data.

**Expected:** The destination opens inside the Account settings hub rather than
as a detached settings surface. Travel Profile and Analytics remain editable
there. When analytics is configured and no choice exists, first-run consent still
appears separately; revisiting Analytics in Account does not recreate that prompt.

**Executable proof:**

- [`frontend/src/components/AccountSettingsHub.test.tsx`](../frontend/src/components/AccountSettingsHub.test.tsx) - `presents the four selected account destinations`
- [`frontend/src/components/AccountSettingsHub.test.tsx`](../frontend/src/components/AccountSettingsHub.test.tsx) - `keeps travel profile and analytics inside the account settings hub`
- [`frontend/src/components/AnalyticsConsent.test.tsx`](../frontend/src/components/AnalyticsConsent.test.tsx) - `shows the bottom prompt only for first-run consent when analytics is configured`

## UX Labs

### EB-LAB-001 - Revisit and re-implement any Lab

**Trigger:** Open an implemented or completed Lab, inspect another option, revise
its handoff notes, and save it for implementation.

**Expected:** Every option remains selectable in every lifecycle state. The new
option and notes become a Ready handoff for another implementation cycle, while
every implemented version remains visible under What was implemented with its
selected option, exact saved notes, version number, and recorded time. One final
summary lists every implemented option and its notes. Saving shows an explicit
confirmation naming the selected option and next version; the re-implementation
action is visually distinct and cannot remain indefinitely in a Saving state.
The permanent Lab number appears on the detail page and in its HTML filename. The
top area explicitly shows the authoritative lifecycle status, includes its state
date when recorded, updates after a save, and reports unavailable state rather
than guessing.

**Executable proof:**

- [`frontend/labs/src/shared/DecisionCapture.test.tsx`](../frontend/labs/src/shared/DecisionCapture.test.tsx) - `keeps every option browsable after loading an implemented choice`
- [`frontend/labs/src/shared/DecisionCapture.test.tsx`](../frontend/labs/src/shared/DecisionCapture.test.tsx) - `starts a re-implementation handoff without losing the completed direction`
- [`frontend/labs/src/shared/DecisionCapture.test.tsx`](../frontend/labs/src/shared/DecisionCapture.test.tsx) - `shows exact notes and a final summary for every implementation version`
- [`frontend/labs/feedback-plugin.test.ts`](../frontend/labs/feedback-plugin.test.ts) - `appends the next implementation version after a reopened Lab`
- [`frontend/labs/src/shared/LabScope.test.tsx`](../frontend/labs/src/shared/LabScope.test.tsx) - `shows authoritative status in the top area and updates after a save`
