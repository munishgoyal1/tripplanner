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

## Planner workspace

### EB-FOCUS-001 - Focus one itinerary occurrence

**Trigger:** Select a place stop in Itinerary, or invoke its Map action. The
identity is kind, place name, day, and stop position. For example, selecting
Jag Mandir at Day 2, Stop 1 identifies that occurrence rather than merely every
place named Jag Mandir. Airport terminal rows and markers invoke map-only exact
focus because they are not inspectable places.

**Expected:**

- Map opens, selects the marker for that exact occurrence, and zooms to level 15.
- Details opens and shows that place, including itinerary-only places not already
  in the selected-place collection.
- Airport terminal focus pans and zooms to the requested day occurrence at level
  15 without requesting Details, including when the itinerary alias differs from
  the provider-canonical airport name.
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
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `zooms an itinerary airport without requesting place details`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_map_view_connects_flight_airports_to_destination_stay`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_focus_zooms_single_item`

### EB-FOCUS-002 - Focus a day or the whole trip

**Trigger:** Select a day scope from Itinerary or Map, or select All days.

**Expected:** Day focus clears exact-place focus and aligns Itinerary to that day
summary. Ordinary days fit their complete circuit. Transfer days keep the full
ordered inter-city geometry visible but fit the useful destination-local circuit,
or the origin-local circuit when no substantive destination stop remains. All
days clears exact-place and day focus, fits all circuits and dotted flight arcs
between every airport pair, and aligns Itinerary to the trip summary. Neither
action requests place Details.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `gives a map day chip the same aggregate circuit focus as an itinerary day header`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `shows all circuits and returns itinerary focus to the trip summary`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `frames an itinerary day circuit without converting it into place focus`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `draws all flight arcs and focuses a repeated airport alias on its requested day`

### EB-MAP-001 - Distinguish multiple hotels in one day

**Trigger:** View a day whose ordered map route contains two or more distinct
hotels.

**Expected:** The unique hotels are labeled `H1`, `H2`, and so on in route order.
A repeated return to the same hotel does not create another number. A direct
hotel-to-hotel leg is dotted in the day's circuit color. A day with one unique
hotel retains the plain `H` marker.

**Executable proof:**

- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `numbers two hotels in their same-day route order`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `distinguishes local, road, bus, rail, and flight route geometry`

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