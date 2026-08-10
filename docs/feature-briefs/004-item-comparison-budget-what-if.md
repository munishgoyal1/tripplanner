# Item Comparison and Budget What-If

## Document control

| Field | Value |
|---|---|
| Brief ID | `004` |
| Status | Validated foundation |
| Owner | Munish Goyal |
| Created | 2026-08-10 |
| Updated | 2026-08-10 |
| Baseline | `docs/REQUIREMENTS.md` on `sandbox/1-stay-comparison` |
| Target milestone | Exact item comparison, then budget what-if foundation |
| Related capability IDs | `PLAN-02`, `DEAL-01` |

## One-sentence requirement

As the trip owner, I need grounded comparisons and explicit budget what-if suggestions so I can change the plan while understanding evidence, uncertainty, and tradeoffs.

## Current behavior

Stay and flight searches retain exact returned candidates as persisted decisions. The trip now stores new budget targets as user-owned structured data, labels incomplete headroom with live-price coverage, retains timestamped published FX provenance, and builds exact-alternative savings proposals only on explicit request. Each proposal can be accepted through the existing revision-checked decision mutation. Coordinated multi-item acceptance remains a follow-up.

## Scope and priority

### Must ship

- Compare only candidates present in the exact provider response used for the recommendation.
- Keep opaque provider references internally and remove them from public views and shares.
- Apply and restore a selected stay or flight as one deterministic trip mutation.
- Add a structured, user-owned budget target without breaking trips that do not have one.
- Produce budget suggestions only on demand.
- Label incomplete headroom as an estimate and disclose evidence coverage.
- Use published, timestamped FX rates for cross-currency totals.
- Apply accepted budget suggestions as coordinated eventual trip patches.
- Require personalized evidence before claiming an option is "worth it."

### Out of scope

- Provider-side booking, payment, cancellation, or held-price claims.
- Silent plan mutation when a quote or budget estimate changes.
- Treating ratings, review counts, or general popularity as personalized value.
- Inventing prices for unpriced trip items.

## Settled business and data rules

1. The budget target is structured data owned and explicitly changed by the user.
2. Incomplete budget headroom may be shown only as a labeled estimate with evidence coverage.
3. Currency conversion uses a published rate with source currency, target currency, rate, and timestamp.
4. What-if suggestions are generated on demand, not continuously in the background.
5. An accepted multi-item suggestion becomes coordinated eventual trip patches through existing mutation ownership.
6. "Worth it" requires evidence tied to the owner's preferences or constraints.
7. Popularity evidence may be displayed as sourced context but cannot establish personalized value.

## User scenarios

1. **Flight comparison**
   - Given a search returns several flight offers,
   - When the planner recommends one,
   - Then the exact returned offers and deterministic ranking evidence remain available for comparison without a second search.
2. **Reversal**
   - Given the owner selects another stay or flight,
   - When they restore the original,
   - Then the exact original provider candidate and trip total return.
3. **Incomplete budget evidence**
   - Given some selected items are unpriced or stale,
   - When the owner asks for a budget what-if,
   - Then the result is labeled as an estimate, names evidence coverage, and does not imply a complete verified total.
4. **Personalized value claim**
   - Given an option is highly rated but no owner preference supports it,
   - When suggestions are ranked,
   - Then the product may show the rating but must not call the option "worth it."

## Privacy, security, and cost

- Provider offer and property handles remain internal and never enter public shared payloads.
- Budget targets and preference evidence follow existing trip ownership and hosted identity boundaries.
- What-if generation is explicit and bounded; no background provider fan-out is introduced by this brief.

## Acceptance criteria

- **AC-01:** Stay and flight decisions contain only candidates from the exact search response used for the recommendation.
- **AC-02:** Selecting and restoring a candidate updates the selected item and total cost deterministically.
- **AC-03:** Backend and shared-client views expose useful stay and flight facts without opaque provider references.
- **AC-04:** Public shares strip provider references from decisions and selected items.
- **AC-05:** A structured budget target is optional and backward compatible.
- **AC-06:** On-demand budget what-if output distinguishes verified totals from incomplete estimates and reports evidence coverage.
- **AC-07:** Cross-currency budget calculations retain published FX provenance and timestamp.
- **AC-08:** Accepted budget suggestions use coordinated trip mutations and can report partial or stale failure without silently diverging surfaces.
- **AC-09:** Personalized value language is emitted only when preference or constraint evidence supports it.

## Validation matrix

| Layer | Required check | Evidence |
|---|---|---|
| Domain | Exact candidate conversion and deterministic ranking | Focused decision tests |
| Provider | One response supplies both recommendation and decision | Provider regression tests |
| Mutation | Override and restore exact selected item | Decision apply tests |
| Contract | Display-safe facts and no provider handles | Trip-view and share tests |
| Web | Kind-specific facts and reversal controls | Decision panel tests and production build |
| Budget | Target, evidence, FX, and on-demand proposal | Focused backend, API, shared-client, and view tests |

## Remaining follow-up

- Add one coordinated multi-item acceptance contract with stale/partial-failure reporting before AC-08 is complete.
- Add a dedicated proposal review UX only after its placement and interaction are owner-approved; the existing decision panel remains the acceptance surface for individual exact alternatives.
