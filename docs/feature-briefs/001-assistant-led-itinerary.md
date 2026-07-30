# Assistant-Led Itinerary Feature Brief

## Document control

| Field | Value |
| --- | --- |
| Brief ID | `001-assistant-led-itinerary` |
| Status | Stage 1 implemented; production UX pending Lab selection |
| Owner | Munish Goyal |
| Created | 2026-07-30 |
| Related capabilities | CORE-01, PLAN-01, MEM-01, WEB-01, MOBILE-01, REL-01 |

## Outcome

Build the smartest personalized itinerary in the shortest time with minimal user
input. The Assistant is the primary planning surface: it starts from durable
preferences and trip history, asks only for unresolved high-impact trip facts,
and then owns a complete practical first itinerary. Details and Map refine that
plan after the main conversational work, and the user can return to Assistant at
any time.

## Product rules

1. Apply known preferences before asking anything; say concisely what was applied.
2. Distinguish durable preferences from trip-specific exceptions. A one-trip
   answer must not silently overwrite long-term memory.
3. Ask at most one consolidated upfront question, only when the missing fact can
   materially change dates, feasibility, party fit, accessibility, or budget.
4. Every structured field has a sensible prefilled value and a skip/default path.
5. When origin, destination, and rough timing are sufficient, build immediately.
6. The first plan chooses one concrete stay, popular and preference-matched places,
   named meals, practical chronological routes, and honest booking readiness.
7. Assistant replies are tight: decision first, brief rationale, next choice only
   when one is useful. Do not restate the whole itinerary in chat when the pane owns it.
8. Rich controls are typed data, never model-authored HTML or parsed Markdown.

## Scenarios

1. **Bare request:** "Plan Paris from Delhi for five days in October." The planner
   uses saved defaults and either builds immediately or asks one compact prompt
   containing only material trip-specific choices.
2. **Detailed request:** user includes dates, party, pace, and a special interest.
   The planner acknowledges the constraints and builds without another question.
3. **Unknown critical constraint:** interactive mode cannot infer party mobility or
   a genuinely binding date/budget. It shows prefilled controls plus a text fallback.
4. **Unsupported client:** the additive event is ignored and the user still receives
   the normal concise text question.
5. **Provider gap:** the planner completes the strongest honest best-effort plan and
   labels unavailable live data instead of entering a clarification loop.

## Acceptance criteria

- **AC-01:** An active UX Lab compares three assistant-overlay footprints with a
   realistic, interactive preference-aware kickoff and a full-viewport trip workspace
   for judging each option before production implementation.
- **AC-02:** The backend validates a versioned structured request with one to four
  fields, bounded options, and a prefilled value for every field.
- **AC-03:** Streaming chat emits `input_request` additively while retaining the
  normal text reply and terminal `done` event.
- **AC-04:** Shared web/native transport retains the event without requiring either
  production UI to render it yet.
- **AC-05:** Direct mode keeps complete-by-default behavior; structured upfront input
  is restricted to genuinely critical interactive-mode gaps in stage 1.
- **AC-06:** The production overlay and control renderer require the owner-selected
  Lab direction and are not implied by this foundation.
- **AC-07:** Future production rendering must support keyboard, focus, screen reader,
  narrow desktop, and native mobile presentation without changing the payload.
- **AC-08:** Planning quality must later be measured against practical routing,
  popularity/review evidence, durable preference fit, trip-specific fit, completeness,
  response tightness, and clarification count.

## Delivery stages

| Stage | Behavior | Status |
| --- | --- | --- |
| 1 | Interactive Lab, validated backend contract, additive SSE event, shared client type | Implemented |
| 2 | Owner-selected production web overlay, structured control renderer, answer submission and recovery | Pending explicit owner selection after full-size Lab evaluation |
| 3 | Native rendering plus repeatable planning-quality evaluation set and tuning | Pending evidence from stage 2 |

## Open decisions

| ID | Decision | Recommendation | Status |
| --- | --- | --- | --- |
| D-01 | Desktop Assistant footprint | B - Focus modal; A is the current provisional trial | Open in full-size UX Lab preview |
| D-02 | Default planning policy after stage 1 | Build immediately when origin, destination, and rough timing exist; ask once only for material blockers | Recommended |
| D-03 | Native presentation | Native bottom sheet using the same payload after web validation | Deferred |

## Validation

- Focused Python tests for payload validation, stable replay identity, and bounds.
- Existing tool-selection and prompt tests cover agent availability and policy.
- Frontend stream parser test covers additive event dispatch.
- UX Lab TypeScript/build validation covers the selectable prototype.
- No dev server, canary, production deployment, or mobile submission in this stage.
