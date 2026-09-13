# Trip reliability: complete routes, grounded stays, recoverable model calls

## Document control

- Owner: Munish Goyal
- Authorized: 2026-09-12, “go ahead and do these actions” following the Kashmir investigation.
- Baseline: ea5841e9
- Status: Validated; publication through the named branch PR
- Capabilities: PLAN-02, PLAN-03, WEB-01

## User problem and evidence

Kashmir day 3 contains outbound and return drives with earlier stops missing
from its local circuit. Hotel TBD remains despite research of real properties
elsewhere in the region. A September 11 flight edit failed during a model call
with RemoteProtocolError; the saved conversation says interrupted. A separate
September 12 edit repeatedly repaired unrelated gaps (addressed by PR #304).

## Desired outcome

Preserve grounded route segments, distinguish a recommended property from a
verified room offer, recover transient model stream failures without repeating
tools, and measure completed requests separately from failed/recovered attempts.

## Scope

- Preserve local travel before, between and after explicit transfers.
- Never bridge an unresolved flight/rail gap with a fabricated ground edge.
- Keep hotel research bounded, including one Places fallback per hotel search.
- Return structured research status, candidates and reasons when no property
  can be recommended. One suitable grounded property is sufficient.
- Persist city-specific research evidence with the next itinerary save; expose
  unresolved reasons in the existing itinerary concern and completion gaps.
- Unknown rate/availability alone does not erase a named recommendation.
- Retry the failed model invocation only, at most once, for transient read or
  protocol failures. Completed tool calls are never replayed by this recovery.
- Publish only completed model responses to SSE, retaining tool/progress events
  while the model runs. Discard text/tool fragments from a failed attempt.
- Record recovery outcomes and explicit request completion rates, with sample
  counts and no claim of production reliability from deterministic tests.

## Boundaries

Preserve the single graph agent, existing flight-only scope, versioned trip
persistence and frontend contracts. No provider purchases, production deployment,
automatic rewrite of the owner's saved Kashmir trip, or invented inventory.
Invalid historical chronology remains visible; route rendering does not validate
or repair that chronology. This milestone is general application behavior.

## Acceptance criteria and validation matrix

| Case | Required result | Proof |
| --- | --- | --- |
| Outbound and return road transfers | All grounded local sections retained | Focused map/itinerary tests |
| Unresolved air leg between local sections | Both local sections visible without a ground bridge | Journey regression |
| One grounded hotel, no live offers | Recommend property; rate and availability remain unverified | Hotel fallback tests |
| Empty/failed hotel and fallback research | Structured city-specific reason, visible after save | Persistence/view tests |
| One city fails in a batch | Preserve successful city candidates | Policy regression |
| Model emits fragments then disconnects | One bounded model retry; fragments discarded | Fake-model and SSE regression |
| Persistent failure or non-transient error | Bounded failure, no tool replay | Fault injection |
| Recovery succeeds | Request completion and attempt recovery measured independently | Metrics tests |

## Release and measurement

Run focused pytest checks and the repository Ruff floor. CI owns typecheck and
build; complete suites remain suspended from lane gates. Commit, push and publish
through a normal PR, then update clean primary master through the shared workflow.
Report measured sample sizes and rates; local process metrics reset on restart,
while attributed events retain durable investigation evidence.

## Validation evidence

- Targeted recovery, hotel research, route continuity and callback isolation:
  23 passed after the final test-isolation fix.
- Existing journey/flight/policy/chat/usage batch: 200 passed; the four initial
  failures were the new lodging-gap classification and three synthetic SSE
  fixtures, corrected and verified by a 28-test follow-up.
- Additional projection/graph/telemetry/SSE/selector batch: 144 passed; its one
  context-leak failure was corrected and included in the final 23-test run.
- Focused hotel/lodging/view checks: 33 passed.
- Required Ruff E9,F63,F7,F82 floor and changed production-file strict lint pass.
  The full configured repository lint profile retains unrelated existing errors.
- No paid providers, production deployment, saved-owner-trip mutation or live
  error-rate measurement was performed. Windows host validation only; the Python
  changes use shared APIs, but macOS execution was not verified.
