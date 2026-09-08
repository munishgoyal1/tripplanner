# Feature 06 — "Why This?" Provenance & Insight Layer

- **Pillars:** E (insightful outcome), C (chat trust)
- **Status:** Proposed (sharpens the itinerary outcome; relates to backlog #10 but focused on the plan, not preference editing)
- **Size:** M · **Risk:** low · **Suggested lane:** Agent 2 (view-model rationale) + Agent 1 (render)

## The pain

A plan you don't understand is a plan you don't trust or act on. Users ask "why this
hotel? why this order? is this actually any good?" Generic planners hand back opaque lists,
so users second-guess and re-research everything themselves.

## Outcome

Every recommended place, hotel, restaurant, time, and route carries a compact **why**:
the matched preference (stated or inferred) + the verified fact (rating, reviews, distance,
hours, price), with an inspectable provenance popover. Personal insights name the saved
preference and the travel fact behind them (already required by taste).

## Bounded v1 (no agent change)

- Derive "why" from signals **already in the view model**: matched interest / food / pace
  preferences ∩ place type, Google rating + review count, must-visit score, proximity to
  the hotel and neighboring stops, and opening-hours fit.
- Render a one-line rationale + expandable evidence on place rows and the hotel.
- Label source and confidence (verified fact vs. estimate); never a fabricated
  "% of itineraries" inclusion figure.

## v2 (later)

The agent emits an explicit selection rationale during planning for higher-fidelity "why."

## UX

- Each row shows a subtle "Why" affordance → popover:
  "Matches your love of forts · 4.6★ (12k) · 10 min from hotel · open 9–6."

## Implementation notes

- **Backend:** extend `build_view` in `src/tripplanner/web/trip_view.py` to attach a derived
  rationale object per stop (pure function over existing preference + place signals); new
  `src/tripplanner/web/insight.py` helper. **No new provider calls.**
- **Frontend:** render in `frontend/src/components/ItineraryStopRow.tsx`,
  `DetailsPaneShell.tsx`, and `TripSnapshot.tsx`; reuse existing rating / score fields.

## Perf / privacy / cost

Pure computation over already-loaded data; no extra calls. Uses stored preferences already
in context.

## Risks & mitigations

- **Overclaiming** is forbidden → only truthful derived signals with honest labels. Low risk.

## Acceptance

- Every substantive stop shows a truthful, sourced rationale.
- The hotel shows why it was selected.
- Labels distinguish verified fact from estimate; no fabricated inclusion percentages.
