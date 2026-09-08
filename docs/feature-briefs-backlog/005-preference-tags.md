# 005 - Preference tags as one-click intent

> Sections 1-5 are **agent-drafted from the owner's dictated intent** on
> 2026-08-14. Overwrite them freely.

## 1. Raw mind dump

> OWNER INPUT (agent draft)

Free text is hard to fill. People prefer easy clicks to typing, and most users
will never write a paragraph about how they like to travel. We should define a
standard set of tags per category and offer them as a click selector, with free
text still available as an override for anything the tags cannot say.

The same destination is many different trips. Goa can be relaxed, or a party
trip, or a hectic see-it-all. Today that intent only arrives if the user
articulates it. A tag makes it one click.

The planner should keep learning from past itineraries and feedback regardless,
so tags are a faster way in, not a replacement for learning.

## 2. User problem

Stating how you want to travel currently requires prose. A new user with no
history gets a generic itinerary because the planner has nothing to go on, and
the cost of telling it is a paragraph they will not write. The planner already
holds a rich structured preference model, but the only ways to fill it are free
text and slow inference from behavior.

## 3. Desired outcome

In a few clicks, a user states the nature of the trip they want, and the
itinerary visibly changes to match. They can see exactly what a tag did, change
any part of it, and say the rest in their own words.

## 4. Must-have examples

1. **Same place, different trip.** Goa tagged `relaxed` and Goa tagged
   `see-it-all` produce visibly different itineraries - fewer, longer stops with
   real gaps versus a dense day - not the same plan with different wording.
2. **Override survives.** A user picks `relaxed`, then says "but I want an early
   start every day". The free-text instruction wins over the tag's day-start
   value, and the rest of the tag stays in effect.
3. **Edge case: one-off versus forever.** A user picks `party` for a stag trip.
   That must not become their permanent travel style, so a tag applied to one
   trip must be distinguishable from a tag saved to the profile.

## 5. Boundaries

- A tag must not be a second source of truth. Tags write the existing preference
  document; nothing new stores preference state.
- A tag must not ship unless it demonstrably changes the itinerary.
- Free text must remain able to express anything a tag can, and must win when
  the two disagree.
- No tag may silently rewrite durable preferences from a one-off trip choice.

---

## Document control

| Field | Value |
|---|---|
| Brief ID | `005` |
| Status | Draft - blocked on brief 004 evidence |
| Owner | Munish Goyal |
| Created | 2026-08-14 |
| Updated | 2026-08-14 |
| Baseline | `docs/REQUIREMENTS.md` @ `8cdfc23` |
| Target milestone | After 004 Phase 6 has proved the vocabulary |
| Related capability IDs | `user_preferences`, `preferences_snapshot`, brief 004 |

## One-sentence requirement

As a traveller who will not write a paragraph about myself, I need to state the
nature of a trip in a few clicks, so that the itinerary matches the trip I
actually want without me having to describe it.

## Why now and evidence

- **Trigger:** the owner's observation that free-text preference entry is the
  hardest field to fill, and that people prefer clicking to typing.
- **Evidence:** the stored preference document has ~30 structured fields
  (`trip_style`, `budget_level`, `planning_preferences.*`, `interests`,
  `transport_preferences.*`, `food_preferences.*`, `hotel_preferences.*`) and
  the owner's own profile leaves most of them at defaults - the model is
  expressive but effectively unfilled.
- **Expected signal:** more trips planned with non-default planning preferences;
  fewer replans immediately after the first itinerary.

## Current behavior

- `user_preferences.load_preferences` returns a structured document already
  containing `trip_style` (currently a single named bundle, e.g. `balanced`),
  `budget_level`, `planning_preferences`, `interests`, `dislikes`, and per-domain
  preference blocks.
- Preferences are set from free text through `save_travel_preferences`, and
  inferred over time into `learned_notes` and `behavior_signals`.
- `trip_constraints` already separates one-off exceptions for a single trip from
  durable preferences, and the agent is instructed never to save one-offs as
  durable.

`trip_style` is the precedent: a tag is the same idea, generalized and made
visible.

## Scope and priority

### Must ship

- A tag vocabulary where each tag declares exactly which preference fields it
  sets, stored as data rather than logic.
- A click selector grouped by category, with free text retained alongside.
- Applying a tag writes the existing preference document; no new store.
- A visible, reversible summary of what a tag changed.
- Per-trip versus durable application, honoring the existing `trip_constraints`
  separation.

### Should ship

- Destination-aware ordering, so plausible tags for this place surface first.
- Tag suggestions derived from the user's own past trips.

### Could ship later

- Learned personal tags.
- Sharing a tag set between travellers.

### Out of scope

- Replacing free text.
- Any tag that does not change planner behavior.
- Changing how preferences are learned from behavior.

## User scenarios

1. **Primary path**
   - Given a user starting a Goa trip
   - When they click `relaxed`
   - Then the itinerary is planned with fewer stops per day and real free time,
     and the user can see which preference values the tag set
2. **Edge case - conflict**
   - Given `relaxed` is applied, which sets a later day start
   - When the user writes "I want to start by 7am"
   - Then the free-text instruction wins and the rest of `relaxed` remains
3. **Recovery - one-off**
   - Given a user picks `party` for one trip
   - When the trip ends
   - Then their durable profile is unchanged and the next trip does not inherit it

## Experience contract

### Entry point and workflow

- Entry: trip setup and the preferences surface.
- Shortest path: pick one intent tag, plan.
- Reversal: deselecting a tag restores the values it set, not the defaults, so an
  unrelated manual change survives.

### Cross-surface behavior

| Surface | Current behavior | Required change | Must stay synchronized with |
|---|---|---|---|
| Web Assistant | Free-text preference capture | Tag click as an equivalent input | Preferences store |
| Web Details | Shows preference-derived hints | Reflect active tags | Web Assistant |
| Mobile Assistant | Free-text capture | Same tag semantics | Web Assistant |
| Export/share | No preference display | Unchanged | - |

### UI states

| State | Expected behavior |
|---|---|
| Empty | Categories shown with no tag selected; free text available |
| Loading | Selector disabled, existing selection visible |
| Existing data while refreshing | Prior tags stay selected |
| Partial provider data | Unaffected - tags are local state |
| Success | Selected tags visible with what they set |
| Validation conflict | Conflicting tag pairs cannot both be active; the newer wins and says so |
| Network/provider error | Selection retained locally and retried |
| Retry | Idempotent |
| Permission or quota exceeded | Not applicable |

### Accessibility and responsive behavior

- Tags are toggle buttons with pressed state, reachable and operable by keyboard,
  labelled with both the tag and its effect.
- Wraps to multiple rows on narrow widths without horizontal scrolling.

## Business and data rules

- The preference document is the only source of truth. A tag is a named bundle
  of values within it.
- Applying a tag is idempotent and records which fields it set, so deselecting
  reverses exactly those and nothing else.
- A per-trip tag writes trip-scoped constraints; a profile tag writes durable
  preferences. The two must never be conflated.
- Explicit user statements outrank tags; tags outrank inferred defaults.
- Adding or changing a tag definition must not silently rewrite stored
  preferences of users who applied it earlier.

## API and integration contract

- Reuses `user_preferences.save_travel_preferences` and the existing
  `trip_constraints` path. No new persistence.
- The tag catalogue is served as data so web and native render the same list.
- No provider dependencies.

## Privacy, security, abuse, and cost

- Tags are ordinary preference data with the same handling as today.
- No new provider or model cost; a tag is applied locally before planning.

## Observability and feedback

- Record which tags were applied and whether the resulting itinerary was kept or
  replanned - the signal that tells us whether a tag is honest.
- Quality metric: replan rate immediately after first itinerary, by tag.

## Acceptance criteria

- **AC-01:** Each tag declares the preference fields and values it sets, as data.
- **AC-02:** Applying a tag changes only the declared fields and is reversible to
  the prior values.
- **AC-03:** Two trips to one destination under two different intent tags produce
  itineraries that differ measurably in stops per day or free time.
- **AC-04:** An explicit user instruction overrides the tag value for that field
  while the tag's other fields remain in effect.
- **AC-05:** A tag applied to one trip leaves the durable profile unchanged.
- **AC-06:** Every shipped tag has evidence from the 004 corpus that it changes
  the itinerary; a tag without that evidence cannot ship.
- **AC-07:** The selector is fully keyboard operable and states each tag's effect.

## Validation matrix

| Layer | Required check | Evidence |
|---|---|---|
| Pure/domain logic | Tag application, reversal, precedence | Pending |
| Backend contract | Preference write path unchanged | Pending |
| Web behavior | Selector component and state | Pending |
| Shared client | Tag catalogue contract | Pending |
| iOS/Android | Renders same catalogue | Pending |
| Accessibility/responsive | Keyboard, pressed state, wrapping | Pending |
| Build | Full suite | Pending |
| Canary | Smoke plus one tagged plan | Pending |
| Production | Owner approval | Pending |

## Delivery and rollout

Blocked on brief 004 producing the evidence for AC-06. Smallest milestone is one
category - trip intent (`relaxed` / `balanced` / `see-it-all`) - since
`trip_style` already exists and needs only to be made visible and expanded.

## Decisions and open questions

| ID | Question or decision | Recommendation | Owner answer/status |
|---|---|---|---|
| D-01 | Ship before 004 proves the vocabulary? | **No.** Shipping a list users click creates a preference contract that needs migration if a tag turns out to change nothing. | Open |
| D-02 | How many tags per category? | Aim for 4-6. A wall of tags is as hard as a text box. | Open |
| D-03 | Are tags per trip, per profile, or both? | **Both, explicitly chosen**, reusing the existing one-off versus durable separation. Defaulting silently to durable is how a stag weekend becomes someone's permanent travel style. | Open |
| D-04 | Do tags compose or conflict? | Composition within a category is usually conflict (`relaxed` + `see-it-all`); across categories it is usually fine (`relaxed` + `mountain`). Model conflict explicitly per category. | Open |

## Agent execution contract

Per template. Additionally: no tag ships without corpus evidence that it changes
the itinerary, and no tag may introduce preference state outside the existing
preference document.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-08-14 | Brief created from owner's dictated intent | Agent |
