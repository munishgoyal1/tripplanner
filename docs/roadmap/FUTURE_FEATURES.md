# Future Features and Enhancements

## Purpose

This is the consolidated candidate backlog for meaningful future product work.
It complements the implemented capability baseline in
[`../REQUIREMENTS_V2.md`](../REQUIREMENTS_V2.md) and does not approve any item
for implementation. Before work begins, the owner selects one coherent outcome
and scopes it through [`../feature-briefs/NEXT_INCREMENT.md`](../feature-briefs/NEXT_INCREMENT.md).

## Prioritization principles

Prefer work that makes a trip more complete, trustworthy, usable during travel,
and consistent across web and native clients. New work should preserve the
single-agent architecture, explicit user control over mutations and purchases,
privacy boundaries, low operating cost, and behavioral parity across affected
surfaces.

## Tier 1: Strong next product increments

### 1. Live Trip Mode

**Outcome:** turn a finalized plan into a calm, useful companion while the trip
is happening.

- Show a time-aware "Now / Next / Later" view for the current day.
- Surface the next reservation, travel leg, opening-hours risk, weather, and
  essential address/contact details.
- Offer one-tap navigation, call, booking-document, and mark-complete actions.
- Detect likely disruption and propose a replacement plan, but never mutate the
  itinerary without approval.
- Keep essential itinerary, reservation, and emergency information available
  offline on mobile.
- Use foreground refresh first; background notifications require a separate
  privacy, platform, and cost decision.

**Bounded first version:** current-day timeline, next-stop card, manual refresh,
o autonomous replanning, and offline read-only essentials.

### 2. Reservation Import and Trip Inbox

**Outcome:** replace manually re-entered bookings with structured, verified trip
facts.

- Import flight, hotel, rail, activity, and restaurant confirmations from PDF,
  image, forwarded email content, or manual paste.
- Extract provider, confirmation number, dates, times, travelers, price, and
  cancellation terms into a review screen.
- Require explicit confirmation before imported data changes the itinerary.
- Preserve the original source and distinguish extracted facts from inferred
  suggestions.
- Reconcile duplicates and itinerary conflicts safely.

### 3. Disruption-Aware Replanning

**Outcome:** help the traveler recover from delays, closures, weather, or missed
stops without destroying trusted parts of the plan.

- Detect conflicts using current weather, opening hours, local travel times, and
  imported reservation constraints.
- Explain what changed, what remains fixed, and why alternatives are proposed.
- Present a compact before/after diff with accept, adjust, and keep-current
  choices.
- Protect booked and user-pinned stops unless the user explicitly unlocks them.
- Reflow only the affected day or remaining trip segment.

### 4. Planning Readiness and Pre-Trip Checklist

**Outcome:** make it obvious whether a trip is genuinely ready to use.

- Derive a readiness score from transport, lodging, daily completeness,
  reservations, entry requirements, and traveler-specific needs.
- Generate a dated checklist for visas, documents, payments, packing, local
  transport, connectivity, and reservations.
- Separate required, recommended, completed, and not-applicable items.
- Link each gap directly to the relevant planning action.
- Avoid generic checklist noise by using destination, dates, companions, and
  stored preferences.

### 5. Offline Mobile Essentials

**Outcome:** retain the core trip when connectivity is weak or expensive.

- Cache the active itinerary, reservation facts, addresses, contact details,
  day maps or route summaries, and emergency information.
- Clearly label freshness and offline state.
- Queue only safe local actions and reconcile them after reconnecting.
- Never imply that provider availability, opening hours, or disruption data is
  current while offline.

### 6. Itinerary Alternatives and Comparison

**Outcome:** let users compare genuinely different plans before committing.

- Generate a small number of intentional alternatives such as relaxed,
  balanced, lower-cost, food-focused, or activity-heavy.
- Compare price range, travel load, free time, family fit, and key tradeoffs.
- Let the user choose one base plan or selectively adopt a day.
- Avoid producing cosmetically different duplicates.

## Tier 2: High-value extensions

### 7. Collaborative Trip Planning

- Invite companions through a scoped trip link rather than account-wide access.
- Collect votes, comments, availability, and must-do preferences per proposal.
- Keep one authoritative itinerary and show pending suggestions separately.
- Record who proposed and approved each material change.

### 8. Actual-versus-Planned Budget

- Import or enter actual expenses against the existing planned budget.
- Track shared and personal costs, categories, currencies, refunds, and splits.
- Show forecast versus actual without turning the product into a general finance
  application.
- Produce a simple post-trip settlement summary.

### 9. Post-Trip Review and Learning

- Prompt for lightweight ratings of lodging, activities, restaurants, pace, and
  overall fit.
- Compare planned versus completed stops and actual versus expected spend.
- Convert only user-confirmed patterns into durable preferences.
- Create a reusable trip memory without exposing private notes in public shares.

### 10. Smarter Preference Control

- Show the user what the planner believes, where it came from, and whether it is
  stated, inferred, or trip-specific.
- Let users confirm, correct, pin, or forget individual learned preferences.
- Explain when a recommendation is materially influenced by a preference.
- Add temporary trip personas without contaminating durable profile data.

### 11. Destination Discovery and Shortlisting

- Recommend destinations from dates, budget, origin, weather tolerance,
  companions, visa constraints, and interests.
- Compare a short list using total effort and fit, not only flight price.
- Convert a selected destination directly into the existing planning workflow.
- Clearly distinguish fresh provider facts from model-generated guidance.

### 12. Flexible-Date and Price-Aware Planning

- Compare nearby departure dates, trip lengths, airports, and transport modes.
- Explain the cost, convenience, and itinerary impact of each option.
- Add price watching only after notification permissions and provider terms are
  explicitly designed.

### 13. Accessibility and Family Logistics

- Expand mobility, sensory, dietary, child-age, senior, and rest-break needs into
  concrete itinerary constraints.
- Surface accessible transport and venue evidence with source confidence.
- Plan stroller, car-seat, medication, and realistic transfer-time needs.
- Avoid claiming accessibility where providers do not supply verified data.

### 14. Safety, Health, and Emergency Pack

- Build a destination-specific pack with emergency numbers, embassy details,
  insurance references, medical notes chosen by the user, and offline contacts.
- Surface severe weather, strikes, closures, and official travel advisories.
- Keep warnings sourced, dated, actionable, and free from alarmist language.

### 15. Richer Sharing and Export

- Add audience-specific views for travelers, family at home, and public sharing.
- Support selective redaction of confirmation numbers, prices, traveler names,
  exact dates, and private notes.
- Add a concise live-trip share view without granting mutation access.
- Keep PDF, print, calendar, email, and link exports visually and semantically
  consistent.

## Tier 3: Distribution, trust, and growth

### 16. Public MVP Trust Surfaces

- Add privacy, terms, contact, support, and understandable data-deletion flows.
- Expose provider freshness, estimate, and booking-status language consistently.
- Add a global daily AI spend circuit breaker and guard newly exposed expensive
  endpoints.
- Establish Azure and provider budget alerts before broader distribution.

### 17. Privacy-Safe Product Analytics and Feedback

- Track a small activation funnel: first prompt, trip created, complete plan,
  export/share/handoff, and return.
- Never put chat text, itinerary content, family data, email, or exact dates in
  analytics events.
- Ask for contextual feedback after a meaningful outcome rather than showing a
  permanent survey.
- Use evidence to select the next feature brief and to remove low-value work.

### 18. Mobile Beta and Store Distribution

- Complete platform keys, deep links, privacy declarations, store metadata,
  crash diagnostics, and beta feedback.
- Validate web/native contract parity and hosted abuse safeguards before each
  distribution stage.
- Keep TestFlight, Play testing, and public submission behind explicit owner
  approval.

### 19. Verified Affiliate Handoffs

- Add measured provider handoffs only where destination, dates, traveler count,
  and selected option can be transferred accurately.
- Label affiliate relationships and preserve neutral comparison.
- Measure successful handoff intent without claiming an external booking.
- Prefer this over unrelated display advertising.

### 20. Limited Destination Advertising Experiment

- Consider only after useful traffic and privacy/consent requirements are met.
- Use one stable, labeled placement in destination content.
- Never place ads in Assistant, Map controls, Itinerary actions, dialogs,
  navigation, or near mutation buttons.
- Stop the experiment if activation, completion, latency, trust, or retention
  degrades materially.

## Tier 4: Longer-term commercial capabilities

### 21. Verified Booking Integrations

- Replace simulated execution language with explicit planned, handed-off, and
  externally confirmed states.
- Add providers only where commercial access, payment, confirmation,
  cancellation, support, identity, and regulatory responsibilities are clear.
- Require an explicit final user confirmation for every purchase.
- Persist provider references and reconcile uncertain outcomes idempotently.
- Never infer booking success from a click, redirect, or local state change.

### 22. Proactive Monitoring and Notifications

- Monitor imported flights, severe weather, closures, and time-sensitive
  reservation events where provider terms permit it.
- Let users choose alert types, channels, quiet hours, and retention.
- Deduplicate alerts and tie each one to a concrete action.
- Treat background email, SMS, and push as separately approved capabilities,
  not an incidental extension of chat.

## Enhancement themes for existing capabilities

These are smaller improvements that should normally accompany a coherent
feature rather than become isolated projects:

- Improve source freshness, confidence, and estimate labels.
- Reduce planning completion time and unnecessary model/tool calls.
- Make partial failure and retry behavior consistent across web and native.
- Preserve exact occurrence identity through every itinerary mutation.
- Improve search comparison quality for flights, hotels, restaurants, and
  activities.
- Strengthen itinerary feasibility using travel time, opening hours, meals,
  rest, and reservation constraints.
- Improve destination and place content with useful, inspectable media rather
  than decorative content.
- Keep exports, sharing, and lifecycle labels truthful and mutually consistent.
- Continue accessibility, keyboard, screen-reader, and responsive-layout work.
- Revisit exact-place map zoom only when observed usage triggers the existing
  deferred decision.

## Explicit exclusions

The following remain out of scope unless the product direction is deliberately
reopened:

- General todo, email, messaging, calendar, or personal-assistant features.
- Generic multi-agent architecture without a proven product need.
- Autonomous purchasing or itinerary mutation without user confirmation.
- Enterprise tenancy and organization administration.
- Notifications or monitoring added without consent, provider, privacy, and
  operating-cost design.

## Intake rule

A candidate moves out of this backlog only when the owner selects it. The next
step is a focused brief stating the user problem, bounded first version,
non-goals, affected capabilities, risk/cost/privacy boundaries, acceptance
criteria, and validation matrix. Implementing several unrelated candidates in
one milestone is intentionally discouraged.
