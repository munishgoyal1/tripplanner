# Experiment: Destination guide depth and context

## Meta

- Owner: Munish Goyal
- Date started: 2026-08-01
- Status: testing
- Lab: `http://127.0.0.1:5175/lab-13-destination-guide.html`

## Problem

Whole-trip Details receives at most ten place items. The view model collects
selected hotels, selected activities, and itinerary stops first, then fills any
remaining capacity with two hotels and destination attractions. A complete trip
can therefore consume the whole limit before alternative choices appear.

Focused Details moves the selected place to the front but labels every remaining
kind as `More places`. A hotel can be followed by attractions or restaurants,
which does not support the user's immediate comparison task. Raising the limit
alone would preload more summaries, photos, and reviews without improving this
information architecture.

## Scope

- Compare city and place-type navigation for a single- or multi-city trip.
- Compare mixed top-level highlights with category-specific browsing.
- Compare how a focused hotel, attraction, or restaurant exposes alternatives.
- Compare progressive batches with city sections and a searchable directory.
- Preserve itinerary, Map, selection mutations, provider ranking, and place-data
  semantics as context only.

## Variants

- **A - Contextual explorer:** start with mixed highlights balanced across the
  trip route. City and category controls refine the list. Focusing a place keeps
  its rich inspector and follows it with same-type alternatives in that city.
  Additional results appear in explicit six-item batches.
- **B - City chapters:** select one destination, then scan compact Hotels,
  Attractions, and Food sections with local `See all` actions.
- **C - Filtered directory:** search all grounded trip places and combine city
  and category filters in one denser result list.

## Current recommendation

Start with **A - Contextual explorer**. It keeps the useful mixed overview at the
whole-trip level, answers the active comparison task in focused mode, and scales
to multi-city trips without forcing the user into a directory first.

For a single-city trip, omit the city scope. For a multi-city trip, `All cities`
balances highlights across every itinerary city rather than allowing the largest
city or the selected itinerary collection to consume the first page.

## Production implementation boundary

Do not replace the ten-item constant with one larger eager payload. After an
option is selected, introduce a paged place-discovery contract with:

- `city`, `kind`, `query`, `cursor`, and a small `limit` such as six;
- total or remaining counts for each available city and kind;
- lightweight row metadata in browse results;
- rich photos, reviews, website, and occurrence actions loaded for the focused
  place only;
- a balanced top-level ranking across itinerary cities and place kinds;
- explicit restaurant support rather than collapsing every non-hotel into an
  attraction.

City identity must come from structured itinerary/place evidence, not parsing a
free-form destination label such as `Rajasthan`.

## Decision

- Decision: pending owner evaluation
- Production implementation status: not implemented
- Next action: compare all three interactions and save one implementation handoff