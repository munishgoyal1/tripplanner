# Next Increment Working Brief

This is the editable input for the next coherent product milestone. It is seeded
with the current capabilities so the owner can mark what changes and delete
everything irrelevant. It is **not** a second history log and it does not approve
all ideas listed in the roadmap.

Fastest workflow:

1. Replace the owner-input prompts in **Requested increment** with a raw mind dump.
2. Mark only affected rows in **Impact map**.
3. Delete unneeded rows or leave them as `Preserve`; unchanged behavior defaults
   to preservation.
4. Ask the agent to normalize this brief, identify contradictions, and implement.

For a large feature, the agent should rename/archive this file as
`NNN-short-outcome-name.md` once scope is stable, then create a fresh copy from
`FEATURE_BRIEF_TEMPLATE.md` for the following increment.

## Document control

| Field | Value |
|---|---|
| Brief ID | `NEXT` |
| Status | Draft owner input |
| Owner | Munish Goyal |
| Created | 2026-07-28 |
| Updated | 2026-07-28 |
| Baseline | `docs/REQUIREMENTS.md` at `f4f4392` |
| Target milestone | TBD |
| Related capability IDs | Mark below |

## Requested increment

### Raw mind dump

> OWNER: Write freely here. Describe what you noticed, what felt wrong, ideas,
> examples, and the experience you want. Grammar and structure do not matter.

### User problem

> OWNER: Who is trying to do what, and where does the current product fall short?

### Desired outcome

> OWNER: What should become easier, faster, safer, or more trustworthy?

### Must-have examples

> OWNER: Add two normal examples and one awkward or failure example if possible.

### Boundaries

> OWNER: What must remain unchanged? What should definitely not be built?

## Current capabilities: preserve or change

Change `Preserve` to `Change` or `Remove` only where the new requirement affects
the current contract. Add a short note describing the delta, not the whole
existing feature.

| Capability | Current baseline | Decision | Incremental requirement |
|---|---|---|---|
| CORE-01 Agent | One phase-aware trip agent with grounded tools and live progress | Preserve | |
| PLAN-01 Planning flow | Preference-first, few-question, sticky-currency planning | Preserve | |
| PLAN-02 Research | Real flights, stays, places, meals, routes, weather, visa, and events | Preserve | |
| PLAN-03 Itinerary quality | Structured chronological days, concrete hotels/meals, complete circuits | Preserve | |
| PLAN-04 Planner review | Immediate deterministic mutations; AI review is explicit and proposal-only | Preserve | |
| MEM-01 Personalization | Profile, family, preferences, history, passive learning, and recall | Preserve | |
| LIFE-01 Lifecycle | Draft -> finalized -> locally recorded booked/handoff; no real purchasing | Preserve | |
| LIFE-02 Saved work | Resume/switch/delete saved trips and persistent per-trip chat | Preserve | |
| WEB-01 Workspace | Itinerary, Map, Details, and Assistant with shared owner state | Preserve | |
| ITIN-01 Itinerary | Trip snapshot, day summaries, exact occurrence rows, route context | Preserve | |
| MAP-01 Map | Exact-stop, whole-day, all-days, circuits, and temporary POI inspection | Preserve | |
| PLACE-01 Details | Destination guide or rich focused-place inspector | Preserve | |
| MUT-01 Mutations | Cross-surface add/remove/move/stay/booked coherence | Preserve | |
| EXPORT-01 Handoffs | Preview, print, PDF, email, share, and calendar | Preserve | |
| MOBILE-01 Native | Shared-contract iPhone and Android Plan/Map/Details/Assistant/Account | Preserve | |
| ID-01 Identity | Persistent guest plus shared Google web/mobile identity | Preserve | |
| DATA-01 Persistence | Atomic local/emulator storage and isolated hosted Cosmos data | Preserve | |
| REL-01 Reliability | Cancellation, stale-response guards, recovery, and caching | Preserve | |
| SAFE-01 Safety | Server-derived principals, signed guests, chat admission limits, model cap, and grounding critic | Preserve | |
| OPS-01 Delivery | Reproducible setup, canary, immutable promotion, smoke, and rollback | Preserve | |
| PUBLIC-01 Public MVP | Custom domain and hosted chat controls implemented; analytics, feedback, privacy/legal surfaces, and broader controls proposed | Preserve | |
| MONEY-01 Monetization | Not implemented; evidence-led ads/affiliate experiment proposed | Preserve | |
| BOOK-01 Real booking | Explicitly not implemented and not implied by booked status | Preserve | |

## Priority cut

### Must ship in this increment

- OWNER: ...

### Should ship if it remains small

- OWNER: ...

### Later

- OWNER: ...

### Explicitly out of scope

- OWNER: ...

## Scenarios and acceptance

The agent should convert the mind dump into numbered, observable criteria before
the first implementation edit.

1. **Primary scenario:** OWNER/AGENT: ...
2. **Edge scenario:** OWNER/AGENT: ...
3. **Failure/recovery scenario:** OWNER/AGENT: ...

- **AC-01:** OWNER/AGENT: ...
- **AC-02:** OWNER/AGENT: ...
- **AC-03:** OWNER/AGENT: ...

## Affected surfaces

Mark only those that should change. The agent must still check synchronized
dependents for regressions.

- [ ] Agent prompt/tool behavior
- [ ] Backend domain logic
- [ ] API/view contract
- [ ] Web Itinerary
- [ ] Web Map
- [ ] Web Details
- [ ] Web Assistant
- [ ] Shared TypeScript client/state
- [ ] iPhone
- [ ] Android
- [ ] Identity/preferences/persistence
- [ ] Export/share/calendar
- [ ] Analytics/feedback
- [ ] Cost/security/abuse controls
- [ ] Infrastructure/release operations
- [ ] Canonical documentation only

## Non-functional requirements

Delete irrelevant prompts; add concrete thresholds only when they matter.

- **Reliability:** OWNER/AGENT: stale, retry, conflict, offline, or rollback needs.
- **Performance:** OWNER/AGENT: interaction or response threshold.
- **Privacy:** OWNER/AGENT: data that must not be logged, analyzed, or shared.
- **Cost:** OWNER/AGENT: provider call/model/storage ceiling or kill switch.
- **Accessibility:** OWNER/AGENT: keyboard, focus, screen reader, and viewport needs.
- **Compatibility:** OWNER/AGENT: saved trips, old clients, or API migration needs.

## Decisions that require owner input

The agent should keep this list short and include a recommendation.

| ID | Decision | Agent recommendation | Owner answer |
|---|---|---|---|
| D-01 | TBD | TBD | Open |

## Delivery plan and validation

The agent completes this after scope is normalized.

| Milestone | Behavior delivered | Focused validation | Status |
|---|---|---|---|
| 1 | TBD | TBD | Pending |

Milestone completion also requires:

- [ ] Relevant backend tests
- [ ] Relevant frontend/shared-client/mobile checks
- [ ] Production build for affected clients
- [ ] Canonical docs updated
- [ ] Brief decisions and evidence updated
- [ ] Commit created and pushed
- [ ] Canary/deployment only when separately requested

## Agent execution notes

- Current behavior is preserved unless this brief explicitly changes it.
- The raw mind dump is intent, not an instruction to implement every mentioned idea.
- Normalize conflicting ideas into Must/Should/Later and surface only material
  decisions to the owner.
- Start from the owning behavior and its nearest regression test.
- Prefer one end-to-end coherent outcome over several partially connected features.
- Never deploy production or submit mobile builds without explicit owner approval.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-28 | Seeded from the current capability baseline | GitHub Copilot |