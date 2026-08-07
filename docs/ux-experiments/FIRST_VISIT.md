# First Visit — the public entry, from stranger to a trip they own

## Meta

- Branch: `agents/worker-3`
- Owner: mugoy
- Date started: 2026-08-06
- Date ended: —
- Status: Open
- Lab URL: `http://127.0.0.1:5175/lab-21-first-visit.html`
- Full-size previews: `?preview=magazine`, `?preview=stage`, `?preview=prompt`, `?preview=intake`
- Preview modifiers: `&surface=landing|first-plan|share`, `&mobile=1`

## Hypothesis

Today the root URL boots the SPA into an empty workspace. A stranger sent a link sees a
blank trip: no statement of what the product makes, no evidence that its plans are real, no
public page for a trip that has already been built, and no moment where a guest is invited
to keep what they made. Every acquisition path the product has — word of mouth, a shared
itinerary, a search result — arrives at that blank screen.

The hypothesis is that the first visit is a designed surface with three moments, not one
page: the landing screen, the forty seconds after Plan is pressed, and the shared trip a
stranger actually arrives through. The lab further claims that the decisive question is not
visual style but *what the first ten seconds are spent on* — asking, proving, interviewing,
or performing — because the product's two claims (it plans like a person who has been there,
and it finds the best real total) are both invisible until something demonstrates them.

## Variants

**A · Prompt-first hero.** The planner input is the hero: one sentence of promise, one large
field, four example prompts, and a "no account needed" line directly beneath it. Proof — a
four-day sample plan, the sourced price table, the savings bar, the capability trio, the
three-step explainer, trust and FAQ — follows below the fold in the familiar order, with a
second composer at the end.

*Exact delta:* the first and largest element on the page is the thing you type into. Proof is
offered as evidence after the ask, not before it.

**B · Proof-first magazine.** A full-bleed editorial hero opens onto a complete generated
plan: four real days with times and transfers, the map, the reason this hotel was chosen over
two others, and every price line with its source and fetch time. Destination plans follow as
their own readable pages. The composer is docked to the bottom of the viewport and travels
with the reader.

*Exact delta:* the first screen is a generated plan, not an input. The composer is a sticky
bar rather than the hero, and destination plans are indexable pages in their own right.

**C · Guided intake.** Four structured answers — where, when, who, budget and pace — assemble
the first prompt in front of the visitor, with the exact sentence it will read shown live as
they change their mind. A side column states what the planner will decide on their behalf and
shows a miniature of the result. The price section, trust and FAQ follow.

*Exact delta:* the entry point is a form that writes the prompt for you, and its answers
double as the preference profile the account will keep.

**D · Live agent stage.** A dark, full-bleed console where the product plans a trip in front
of you. Research receipts stream on the left from 0:02 to 1:12, day cards assemble on the
right as skeletons resolve, and the total falls from €3,833 to €3,480 while the sources are
named. The call to action is to take over the plan already running. A light band below the
stage carries the price receipt, destinations, trust and footer.

*Exact delta:* the hero performs rather than describes. It is the only option whose first
screen moves on its own, the only one that shows the price falling live, and the only one
written in a visual language different from the rest of the site.

**Today (baseline).** Selectable from the preview toolbar. The root URL mounts the workspace
with an empty trip; there is no public page, no guest expiry messaging, no public trip URL,
and no link preview.

### Why a fourth option exists

The owner asked for a genuinely different look and feel if one was worth presenting. D is
that option, and it is not a restyle of A: it is the only design in the set that makes both
product claims legible simultaneously, because the reasoning and the falling price are the
demonstration rather than the copy. It is included precisely so its risks can be judged —
autoplay, a dark theme unlike the workspace, dependence on JavaScript for any content at all,
and a single fixed destination that is not the visitor's.

## Required in every option

1. A visitor can start a real trip with no account, and the page says so before they type.
2. What the product does — and what it refuses to do, including never holding a card or taking
   a payment — is legible on the first screen.
3. At least one complete generated plan is reachable, with real times, transfers and place
   names, not a screenshot of a chat.
4. Every price shows its source and when it was fetched; estimates are labelled as estimates.
5. The best-total story is public: what was compared, what was saved, what was rejected.
6. Pressing Plan produces a durable trip URL immediately, and the guest state states its own
   expiry.
7. Signing in adopts the existing guest trip unchanged; nothing is re-planned and nothing is
   lost.
8. A shared trip link renders a readable plan and a correct link preview without running the
   app.
9. The whole entry works at 390 px, with the first action reachable without a scroll.
10. Privacy, terms and what it costs are one click from the first screen.

## Scope

Changed experiment files:

- `frontend/labs/lab-21-first-visit.html`
- `frontend/labs/src/first-visit/main.tsx` — lab page, option tabs, surface switcher, 390 px
  frame, stale-price stress toggle, baseline comparison, full-size preview
- `frontend/labs/src/first-visit/FirstVisit.tsx` — four options across three surfaces plus the
  baseline facsimile
- `frontend/labs/src/first-visit/pieces.tsx` — tone-parameterized building blocks shared by all
  four options
- `frontend/labs/src/first-visit/fixture.ts` — public-edge content: promise, prompts, priced
  lines with sources, savings, agent receipts, destinations, trust points, FAQ, sign-in moments
- `frontend/labs/vite.config.ts`, `frontend/labs/src/shared/labRecords.ts`,
  `frontend/labs/src/shared/LabScope.tsx`, `frontend/labs/src/shared/OptionContrast.tsx` —
  registration only

Related production code read but not modified: `frontend/src/main.tsx` and the app shell it
mounts, `frontend/labs/src/shared/tripFixture.ts` (source of the Lisbon plan reused here).

Non-goals: the workspace itself, real authentication, provider search, live pricing,
server-side rendering mechanics, SEO tooling, and any pricing tier beyond the single honest
line that the beta is free.

## Interaction intent

The three surfaces are judged as one journey, not three screens.

*Landing* answers "what is this and can I trust it" and offers exactly one action. *First plan*
covers the forty seconds after Plan: a guest trip URL exists at 0:00, reasoning streams while
the plan fills in, the guest banner names a 30-day expiry, and the sign-in moment appears where
that option believes it belongs — at first save for A, B and C, at take-over for D. Sign-in
adopts the guest trip; refusing it costs nothing except durability. *Share* is the second front
door: a message-app link preview that must be correct without the bundle, opening a read-only
public trip page that ends with a composer to plan the same trip for the reader's own dates.

The stale-price toggle is the honesty test. It replaces confident totals with a stated fact —
flight prices 22 minutes old, one hotel rate that could not be re-checked — because the product
would rather look slower than look wrong.

## Test scenarios

1. Arrive cold on desktop. Ten seconds, no scrolling: say what this makes, what it costs, and
   whether it will book anything.
2. Arrive cold at 390 px. Is the hero still one thing and one action, and is that action
   reachable without a scroll?
3. Count the interactions and the scroll distance between arrival and a trip being planned.
4. Read only what is above the fold and decide whether the price claim is believable.
5. Switch to the first-plan surface. Is it clear that a trip already exists, and that it will
   expire?
6. Reach the sign-in moment. Does it arrive at a point that helps the visitor, or only us?
7. Refuse sign-in. Is the plan still usable, and is the cost of refusing stated plainly?
8. Open the share surface as a recipient who has never heard of the product. Does the page work
   as a first impression on its own terms?
9. Turn on the stale-price state. Does the page stay trustworthy when the numbers cannot be
   defended?
10. For D specifically: watch it twice, then replay. Does it still read as evidence the second
    time, or as an advertisement?
11. For B and D: decide how much of what you just read could be served as HTML before the bundle
    loads.
12. Move from the landing page into the workspace mentally. How jarring is the handoff?

## Scorecard (1-5)

| Criterion | A · Prompt | B · Magazine | C · Intake | D · Stage |
| --- | --- | --- | --- | --- |
| Ten-second comprehension | | | | |
| Reason to believe | | | | |
| Time to first prompt | | | | |
| Account pressure | | | | |
| Arrival from a shared link | | | | |
| 390 px survival | | | | |
| First paint and indexing | | | | |
| Distance from the workspace | | | | |

## Decision

- Decision: pending owner review.
- Implementation: none. No production code changes in this Lab.
- Rationale: B answers the belief problem and is the only option whose content is worth
  indexing; D is the only option that makes both product claims visible at once and carries the
  most risk; A is the cheapest and the most copyable; C solves prompt-blank paralysis at the
  cost of feeling like a booking form.
- Next action: owner reviews all four across the three surfaces, at desktop and 390 px, with the
  stale-price state on, then records a selection in the lab's decision capture.
