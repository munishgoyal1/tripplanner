# Feature Brief Template

Use one copy of this file for one coherent product outcome. A rough mind dump is
welcome; the structure helps the AI agent turn it into an implementable contract
without losing intent.

Recommended filename after the scope is understood:

```text
docs/feature-briefs/NNN-short-outcome-name.md
```

Do not edit this template for a real feature. Copy it, fill the new file, and
keep the template reusable.

## Fast path: the only fields the owner must fill

The owner can stop after these five items. The agent will inspect the current
system, normalize the rest of the brief, identify contradictions, and ask only
questions whose answers materially change product behavior or risk.

### 1. Raw mind dump

Write freely. Include annoyances, examples, half-formed ideas, desired feeling,
and anything that must not be lost.

> OWNER INPUT

### 2. User problem

Who is struggling, what are they trying to accomplish, and why is the current
behavior insufficient?

> OWNER INPUT

### 3. Desired outcome

Describe what becomes easier or reliably possible. Prefer an observable outcome
over a list of controls.

> OWNER INPUT

### 4. Must-have examples

Give two or three concrete scenarios, ideally including one awkward edge case.

> OWNER INPUT

### 5. Boundaries

List anything that must not change, must not be built, or needs approval first.

> OWNER INPUT

---

Everything below may be completed collaboratively with the AI agent.

## Document control

| Field | Value |
|---|---|
| Brief ID | `TBD` |
| Status | Draft / Ready / In progress / Validated / Shipped / Superseded |
| Owner | Munish Goyal |
| Created | YYYY-MM-DD |
| Updated | YYYY-MM-DD |
| Baseline | `docs/REQUIREMENTS_V2.md` version and commit |
| Target milestone | TBD |
| Related capability IDs | TBD |

## One-sentence requirement

As a `<user>`, I need `<behavior>` so that `<outcome>`.

## Why now and evidence

- Trigger: user observation, failure, support feedback, usage data, cost, or risk.
- Evidence: exact trip, screen, request, log, metric, or repeated workflow.
- Frequency and severity: how often and how harmful.
- Expected signal: what should improve if the feature works.

## Current behavior

Describe what happens today and link to the owning capability IDs, UI surface,
API contract, or nearby test. Separate verified behavior from assumptions.

## Scope and priority

### Must ship

- Required behavior.

### Should ship

- Valuable behavior that may be deferred without invalidating the outcome.

### Could ship later

- Follow-up ideas that are explicitly outside this increment.

### Out of scope

- Behaviors the implementation must not add.

## User scenarios

Use plain scenarios or Given/When/Then. Include normal, repeated, stale,
conflicting, offline/provider-failure, and reversal cases when relevant.

1. **Primary path**
   - Given ...
   - When ...
   - Then ...
2. **Edge case**
   - Given ...
   - When ...
   - Then ...
3. **Recovery**
   - Given ...
   - When ...
   - Then ...

## Experience contract

### Entry point and workflow

- Where the user discovers or starts the behavior.
- The shortest normal path.
- How the user reverses, retries, dismisses, or exits.

### Cross-surface behavior

Complete only affected rows. One conceptual action must retain one meaning across
surfaces; platform presentation may differ.

| Surface | Current behavior | Required change | Must stay synchronized with |
|---|---|---|---|
| Web Itinerary | | | |
| Web Map | | | |
| Web Details | | | |
| Web Assistant | | | |
| Mobile Plan | | | |
| Mobile Map | | | |
| Mobile Details | | | |
| Mobile Assistant | | | |
| Export/share | | | |

### UI states

| State | Expected behavior |
|---|---|
| Empty | |
| Loading | |
| Existing data while refreshing | |
| Partial provider data | |
| Success | |
| Validation conflict | |
| Network/provider error | |
| Retry | |
| Permission or quota exceeded | |

### Accessibility and responsive behavior

- Keyboard and screen-reader semantics.
- Focus ownership and restoration.
- Desktop, narrow desktop, web mobile, iPhone, and Android differences.
- Stable dimensions, overflow, and long-text behavior.

## Business and data rules

- Authoritative source of truth.
- Validation and invariants.
- Identity and ownership boundaries.
- Ordering, deduplication, occurrence, date/time, and currency rules.
- Retention, deletion, migration, and backward compatibility.
- Idempotency, concurrency, and stale-write expectations.

## API and integration contract

- Existing endpoints/contracts to reuse.
- New request/response fields, including optional/backward-compatible behavior.
- Provider dependencies and graceful degradation.
- Cache/invalidation behavior.
- Mobile/shared-client contract impact.

Do not prescribe a new technical abstraction unless it is a genuine constraint.
The agent should choose the smallest implementation that matches existing owners.

## Privacy, security, abuse, and cost

- Personal or sensitive data involved.
- What must never enter analytics, logs, URLs, or third parties.
- Authentication/authorization and tenant boundaries.
- Abuse and rate-limit considerations.
- Provider calls, model tokens, storage, and expected cost ceiling.
- Required budget alerts or kill switches.

## Observability and feedback

- Success event(s), with a minimal property allowlist.
- Failure/retry event(s).
- Funnel or quality metric affected.
- Qualitative feedback prompt and timing, if any.
- Rollout evidence required before expansion.

## Acceptance criteria

Number criteria so implementation, tests, and review can reference them.

- **AC-01:** ...
- **AC-02:** ...
- **AC-03:** ...

Every criterion should be observable. Avoid "works correctly," "intuitive," or
"fast" unless a concrete behavior or threshold defines it.

## Validation matrix

| Layer | Required check | Evidence |
|---|---|---|
| Pure/domain logic | Focused unit tests | Pending |
| Backend contract | Focused API tests | Pending |
| Web behavior | Component/integration tests | Pending |
| Shared client | Contract/state tests | Pending |
| iOS/Android | Type/lint/device checks as affected | Pending |
| Accessibility/responsive | Keyboard + target viewports | Pending |
| Build | Relevant production builds | Pending |
| Canary | Smoke + manual critical flow + bake | Pending or N/A |
| Production | Explicit approval + smoke + monitoring | Pending or N/A |

## Delivery and rollout

- Smallest coherent implementation milestone.
- Data/configuration prerequisites.
- Feature flag, staged rollout, or immediate release.
- Canary manual checks and bake duration.
- Rollback behavior, including data written before rollback.
- Documentation and runbook updates.

## Decisions and open questions

Only include questions whose answers change behavior, scope, risk, cost, or
architecture. Record a recommendation where the agent has enough evidence.

| ID | Question or decision | Recommendation | Owner answer/status |
|---|---|---|---|
| D-01 | | | Open |

## Agent execution contract

Unless this brief overrides them:

- Treat `docs/REQUIREMENTS_V2.md`, `docs/PRODUCT.md`, `docs/CODEMAP.md`, and
  `docs/ENGINEERING_LEARNINGS.md` as the current baseline.
- Preserve unrelated user changes and existing public contracts.
- Inspect the nearest current implementation and test before editing.
- Implement the smallest coherent slice that satisfies the acceptance criteria.
- Keep equivalent actions consistent across panes and native clients.
- Validate the affected behavior, then the milestone-level checks once.
- Update this brief with resolved decisions and validation evidence.
- Update canonical docs when capability, architecture, taste, or operations change.
- Commit and push the completed milestone. Never deploy production without explicit
  owner approval.

## Change log

| Date | Change | Author |
|---|---|---|
| YYYY-MM-DD | Brief created | Owner/Agent |