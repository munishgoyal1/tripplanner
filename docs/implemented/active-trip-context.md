# Active-trip context and explicit departure notice

## Owner request (summary)
Treat the selected trip as the context for Assistant requests generally. The Goa
flight request was an example, not a destination-specific requirement. Deprioritize
starting a different trip inside an existing one; notify the traveller before
moving away when a new whole-trip request is clearly detected.

## Document control
- Status: Shipped
- Owner: Munish Goyal
- Date: 2026-09-12
- Baseline: 16795299
- Capabilities: CORE-01, PLAN-01, LIFE-02

## Problem and evidence
The graph now injects active-trip facts, but its prompt uses a flight-specific
example. Creation remains exposed during ordinary follow-ups. The whole-trip
regex permits arbitrary text between planning, trip and destination words, so
component changes can be mistaken for a destination switch.

## Desired outcome
Follow-ups about transport, lodging, meals, schedule, budget and preferences are
interpreted against the selected trip. Explicit current instructions win over
saved facts, and missing information is requested only when necessary. Clear
whole-trip requests get a visible departure notice before model work starts.

## Scope
- Generalize current-trip instructions and include compact route and lodging facts.
- Tighten new-trip detection and hide creation during existing-trip follow-ups.
- Emit one deterministic departure notice for clear new-trip requests, stream it
  before model/tool execution and retain it in JSON replies and saved chat.
- Preserve current trip persistence and existing fresh-trip entry points.
- Proposal-only analysis must neither announce departure nor expose creation.

## Interaction decision
Use the owner's offered notification option, not an additional confirmation gate.
The notice states that the current trip remains saved and the assistant is moving
to a separate plan. Ambiguous wording stays in context and can be clarified by the
assistant; merely naming another city is insufficient to announce departure.

## Acceptance criteria
1. Existing-trip flight, hotel, restaurant, budget, day-trip and schedule requests
   receive saved trip facts without any destination-specific production example.
2. These requests do not expose create_trip_plan or trigger a new-trip notice.
3. Explicit new/separate-trip requests and direct whole-trip destination requests
   retain the creation workflow and emit the notice once before streaming work.
4. Negated/hypothetical requests and component edits do not trigger departure.
5. The next model round receives updated trip facts; no saved history is required.
6. JSON and SSE final replies retain the notice; replay does not execute a new turn.
7. Empty workspace and proposal-only requests do not announce departure.

## Validation matrix
| Boundary | Proof |
| --- | --- |
| Intent detection | Parameterized current-trip/new-trip/negative request tests |
| Model contract | Captured prompt and tool bindings over multiple destinations |
| Transport | JSON and SSE departure notice and persistence tests |
| Regression | Focused graph, chat and input/stream tests |
| Gates | Configured Ruff floor and PR CI |

## Non-goals and risks
No new agent, provider purchases, full itinerary redesign, or production deployment.
Conservative detection may ask for clarification on unusual whole-trip phrasing.
Tests prove context delivery and control flow, not complete live-model compliance.

## Validation result
267 selected backend tests passed, including context/tool binding, whole-trip intent,
JSON/SSE notice persistence, security and kickoff regressions. Configured Ruff floor
passed. Live model compliance remains unverified. No production deployment.
