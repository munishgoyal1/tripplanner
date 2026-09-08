# Feature 01 — One-Line Trip Starter & Smart Intake

- **Pillars:** A (breezy start), E (insightful outcome)
- **Status:** Proposed (new front-door; sharpens `CHAT-01` / `PLAN-01`)
- **Size:** M · **Risk:** low · **Suggested lane:** Agent 2 (parse) + Agent 1 (front-door UI)

## The pain

The hardest moment in any planner is the empty start. Users abandon at a blank chat
or a form. tripplanner is already automation-first, but the very first interaction
still leans on the structured kickoff card — there is no single "just tell me in one
sentence" doorway that immediately produces a real plan.

## Outcome

The user types (or later speaks) one natural line —
"long weekend in Goa from Bangalore next month, 2 adults, beach + seafood" — and
immediately sees the structured intake **fully prefilled**, then an automation-first
complete plan builds with no further questions in direct mode.

## Bounded v1

- A prominent single-line "Plan a trip" input on the empty workspace and in the command bar.
- Backend parses origin, destination, rough dates/duration, party, and 1–2 vibe tags
  from the sentence, merged with saved preferences, into the existing
  `request_trip_input` payload.
- Renders the existing `TripInputCard` prefilled; **Build** proceeds through the normal
  `create_trip_plan` path. Skip/submit semantics unchanged.
- Ambiguity (e.g. missing destination) asks exactly **one** consolidated question,
  consistent with `CHAT-01`.
- Voice input (Web Speech API) is explicitly deferred.

## UX

- Empty state: one large input + a few example chips ("Weekend in Goa", "10 days Japan in spring").
- On submit: 300ms thinking state → prefilled intake slides in → user confirms/edits → build.
- Never auto-build a guessed destination; the prefilled card is always confirmable first.

## Implementation notes

- **Frontend:** front-door input in `frontend/src/App.tsx` empty state +
  `frontend/src/components/DesktopToolbar.tsx`; reuse
  `frontend/src/components/TripInputCard.tsx` and `frontend/src/hooks/useChatStream.ts`.
  No new pane.
- **Backend:** extend the new-trip kickoff in `src/tripplanner/graph.py` to accept a
  free-text seed; add a light structured parse that fills `request_trip_input` fields,
  then reuse the existing preference merge. **No new agent.**
- **Contract:** add an optional `raw_text` seed to `request_trip_input`; keep the concise
  text fallback for older clients in `packages/tripplanner-client`.

## Perf / privacy / cost

One short structured parse per new trip; negligible cost, no new provider calls. Raw text
stays in the trip's chat context and is not sent to analytics.

## Risks & mitigations

- **Misparse** → always show the prefilled card for confirmation before building. Low risk.

## Acceptance

- One-line input yields a correctly prefilled intake for realistic sentences.
- Ambiguous input asks exactly one consolidated question.
- Direct mode builds with no extra questions; wrong destination is never auto-built.
