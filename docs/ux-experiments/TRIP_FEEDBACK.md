# Experiment: Trip itinerary feedback

## Meta

- Lab: #29 (`trip-feedback`)
- Page: `frontend/labs/lab-29-trip-feedback.html`
- Branch: `sandbox/6-lab-factory`
- Owner: `munish`
- Date started: `2026-08-18`
- Date ended: `2026-08-24`
- Status: `implemented`

## Hypothesis

A traveller who has read their itinerary has an opinion about it, and that opinion is
only worth collecting if giving it costs almost nothing. The inputs are not in
question: a thumbs pair, an optional five-star rating, and an optional comment, where
one tap already counts as a complete submission.

What is genuinely uncertain is placement. The workspace already spends its width on the
itinerary, map, details, and assistant, so a feedback surface must be permanently
available without permanently occupying the plan. This Lab compares five homes for the
identical control and measures each by what it occupies while nobody is using it.

## Scope

Changed files:

- `frontend/labs/lab-29-trip-feedback.html`
- `frontend/labs/src/trip-feedback/main.tsx`
- `frontend/labs/src/trip-feedback/options.ts`
- `frontend/labs/src/trip-feedback/styles.css`
- `frontend/labs/src/trip-feedback/main.test.tsx`
- `frontend/labs/src/shared/labRecords.ts`
- `frontend/labs/src/shared/LabScope.tsx`
- `frontend/labs/src/shared/OptionContrast.tsx`
- `frontend/labs/vite.config.ts`

Non-goals:

- No production UI change until an option is selected and handed off.
- No change to how the planner reasons about or reacts to a rating.
- No moderation, analytics dashboard, or reply-to-feedback workflow.
- No new sign-in requirement; feedback never demands an account.

## Options

Ranked by the Lab's contrast scores; the page letters them from the same scores.

| Letter | Option | Rests as | Reachable from |
| --- | --- | --- | --- |
| A | Toolbar rating pill | One small toolbar control | Every pane |
| B | Itinerary footer card | One card below the last day | Itinerary |
| C | Assistant-led ask | One message in the transcript | Assistant |
| D | Per-day thumbs | One control per day header | Itinerary |
| E | Floating feedback tab | A floating pill over the plan | Every pane |

A is the recommended starting point because it is the only placement that is equally
close to every pane while costing almost no resting space. B is a natural companion
rather than a rival, because the end of the itinerary is the most honest moment to ask.

## Interaction Intent

- Primary workflow: tap thumbs up or down once. That submission is complete and stored.
- Secondary workflow: optionally add stars, optionally add a comment. Within the same
  visit these amend that submission instead of creating another one.
- Repeat: feedback can be given again at any time. Later submissions append.
- Already-sent signal: a quiet marker with a count. It never blocks a new submission and
  never becomes a prompt to rate again.
- Mobile behavior: the same control and same inputs; the popover and sheet become full
  width, and the toolbar keeps only the thumbs pair.

## Proposed Storage

Feedback is append-only, unbounded per trip, and not part of the plan itself, so it does
not belong inside the trip document. A trip document is read on every workspace load and
replaced under an ETag, so embedding submissions would make every read pay for feedback
and would put feedback writes in conflict with ordinary itinerary edits.

New container `trip_feedback`, partition key `/user_id`, consistent with every existing
container. One document per submission:

```json
{
  "id": "fb_01JD9...",
  "user_id": "google-101851654028336975901",
  "identified": true,
  "trip_id": "lisbon-2027-03-12",
  "trip_revision": 14,
  "sentiment": "up",
  "rating": 4,
  "comment": "Day 3 is too long.",
  "day": null,
  "surface": "toolbar-pill",
  "client": "web",
  "created_at": "2026-08-18T09:14:22Z"
}
```

The trip document carries only a rollup, so the already-sent marker renders without a
second query:

```json
"feedback": {
  "count": 2,
  "last_at": "2026-08-18T09:14:22Z",
  "last_rating": 4,
  "last_sentiment": "up"
}
```

Rules this Lab assumes:

- `user_id` is whichever principal already exists: a signed-in account or a guest
  capability id. Feedback never asks anyone to sign in first, and a caller-claimed id is
  never trusted.
- `trip_revision` records the plan version actually read, so a later itinerary change
  cannot silently reattribute a complaint.
- `comment` is user content: trimmed, length-capped, never fed back into a prompt, and
  covered by the existing erasure path.
- `sentiment` and `rating` are independently optional; neither gates the other.
- Deleting a trip deletes its feedback, since both live under the same partition key.
- Local JSON persistence keeps the same shape so the emulator and file backends agree.

## Test Scenarios

1. Read the itinerary to the end, then give feedback with a single thumb tap.
2. Give a rating without a comment, and a comment without a rating.
3. Submit once, then submit again later; confirm both are kept and the marker counts.
4. Confirm the already-sent marker never blocks or replaces a new submission.
5. Switch to mobile and confirm the control is still reachable and does not cover a stop.
6. Confirm no option interrupts, gates, or modally blocks reading the plan.

## Scorecard (1-5)

- Completion speed:
- Clarity:
- Cognitive load (higher is better/easier):
- Mobile usability:
- Delight:
- Confidence while editing:

## Findings

- What worked:
- What failed:
- Surprises:

## Decision

- Decision: Option A, `toolbar-pill`.
- Rationale: It remains equally reachable from every desktop pane while adding only a
  compact toolbar control; mobile retains the direct thumbs pair.
- Next action: Observe real use before adding another placement or changing how planning
  intelligence consumes feedback.
