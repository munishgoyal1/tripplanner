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
place named Jag Mandir.

**Expected:**

- Map opens, selects the marker for that exact occurrence, and zooms to level 15.
- Details opens and shows that place, including itinerary-only places not already
  in the selected-place collection.
- Itinerary, Map, and Details retain the same day and stop after the view refresh.
- Repeating the same action reapplies focus after manual map movement or filtering.
- A failed refresh leaves the previous usable view in place and reports the error.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `keeps an itinerary-only stop focused in its map occurrence and details after refresh`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `preserves the itinerary day when focusing a repeated hotel`
- [`frontend/src/api.test.ts`](../frontend/src/api.test.ts) - `sends the exact itinerary occurrence with place focus`
- [`tests/test_trip_view_api.py`](../tests/test_trip_view_api.py) - `test_trip_view_preserves_exact_itinerary_occurrence`
- [`frontend/src/components/MapPanel.test.ts`](../frontend/src/components/MapPanel.test.ts) - `uses the requested occurrence day for a repeated hotel`
- [`tests/test_trip_view.py`](../tests/test_trip_view.py) - `test_focus_zooms_single_item`

### EB-FOCUS-002 - Focus a day or the whole trip

**Trigger:** Select a day scope from Itinerary or Map, or select All days.

**Expected:** Day focus clears exact-place focus, fits the complete day circuit,
and aligns Itinerary to that day summary. All days clears exact-place and day
focus, fits all circuits, and aligns Itinerary to the trip summary. Neither
action requests place Details.

**Executable proof:**

- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `gives a map day chip the same aggregate circuit focus as an itinerary day header`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `shows all circuits and returns itinerary focus to the trip summary`
- [`frontend/src/App.test.tsx`](../frontend/src/App.test.tsx) - `frames an itinerary day circuit without converting it into place focus`

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