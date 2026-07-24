# PRODUCT — tripplanner trip planner

> The "what & why" companion to [CODEMAP.md](./CODEMAP.md) (the "where").
> Keep this short, opinionated, and current. If a feature lands that
> changes the vision/taste/scope, update this file in the same commit.

## 1) Product

A personal AI trip planner that produces a **complete, bookable** trip — not
a list of suggestions. Real flights (Duffel), real hotels & activities
(Amadeus), real ratings & reviews (Google Places), fresh travel content
(Tavily). A single LangGraph agent uses a phase-selected tool set. It learns from preferences and
past trips and remembers them across devices.

**Target user**: the owner (Munish). One-person product. Optimize for *his*
flow, not a generic SaaS. If it isn't useful to him today, it doesn't ship.

## 2) Non-goals (resist scope creep)

- ❌ Multi-tenant features (orgs, teams, sharing) until explicitly asked.
- ❌ Automated purchasing or card charging (booking remains a verified handoff).
- ❌ Mobile app. The SPA must work great on a desktop browser first.
- ❌ Background email/SMS/push notifications (removed Session 1).
- ❌ Calendar/Gmail/Keep integrations (removed Session 1).
- ❌ Generic chatbot vibes. This is a planner, not a friend-bot.

## 3) Run modes

- **LOCAL**: CLI or React SPA/API; isolated Azure `tripplanner-local` database
  by default, with the Cosmos Emulator as a config option and JSON fallback for
  an unconfigured CLI.
- **HOSTED**: React SPA via FastAPI on Container Apps; shared free-tier Cosmos
  account with isolated environment databases.

One codebase, dispatcher in `storage_cosmos.is_enabled()`.

## 4) Owner taste — the look & feel

Reference points: **Airbnb** and **TripAdvisor** (magazine-style travel
browsing). NOT a corporate dashboard, NOT a chat-toy, NOT generic Bootstrap.

- **Layout**: desktop is a fixed-height spatial planner: itinerary left, a
  persistent dominant map center, and a contextual details inspector right.
  A compact top command bar owns saved-trip selection, global workspace
  controls (including account/preferences), lifecycle/completeness status,
  total cost, and the latest mutation outcome. Its saved-trip menu must overlay
  every planner pane. Itinerary, Map, Details, and Assistant have obvious,
  symmetric show/hide controls. Details and Assistant are independent sections
  in the right dock: either can fill it while the other is hidden, and both stay
  mounted so their state survives. Only panes scroll; the page never does.
  Accessible drag/keyboard
  separators resize itinerary, map, inspector, and the details/chat split, and
  sizes persist locally. Itinerary, Map, Details, and Assistant can each be
  maximized and restored. On narrower desktops
  the inspector overlays the map on demand. Mobile mounts chat plus an on-demand
  trip-details sheet.
- **Color**: coral `brand` (#e11d48) as the single accent for primary action +
  active state; teal `accent` for secondary surfaces; ink/muted/surface
  neutrals everywhere else. No rainbow.
- **Type**: Inter for UI; Fraunces for display headings. Fonts loaded via
  `<link>` in `frontend/index.html` (NOT from CSS — PostCSS rejects late `@import`).
- **Shape**: generous radii (`rounded-2xl`, `rounded-3xl`, `rounded-4xl`),
  `shadow-card` / `shadow-pop`, ring-1 hairlines, gradient hero on the trip panel.
- **Density**: airy. Whitespace > squeezing more in. One clear primary action
  per card. Pills for status, ribbons for "In trip".
- **Motion**: subtle hover-lift, 300ms cross-fades on data switches. NO
  blanking the panel while data loads — keep prior content dimmed (`stale`
  opacity-70) and swap when ready.
- **Reliability**: only the active responsive shell mounts. Focus/view requests
  cancel stale predecessors, interrupted chat streams recover the composer,
  and map/itinerary refreshes retain prior data with visible retry states.
  One workspace reducer owns trip identity/revision and active place state, so
  focus-only navigation never triggers unrelated panel reloads. Stale trip,
  map, and itinerary requests abort during rapid changes.
- **Itinerary scanning**: each day header shows stop count, planned duration,
  route distance/time/mode, and a direct Maps handoff before the stop details.
  Clicking a place stop focuses both its map pin and its contextual Details view.
  Selecting a Map day scrolls the itinerary to that day and focuses its primary
  place in Details. Restaurants are place stops too: they join day circuits and
  support the same focus behavior. Substantial planning days use concrete,
  preference-matched restaurant names from search results, never generic or
  `TBD` meal placeholders. Each day circuit starts at the selected stay,
  includes every geocoded structured stop in itinerary order, and returns to the
  stay at night; repeated places remain part of every day that references them.
  The Map stop picker searches Google Places within the current map context and
  also accepts labeled POIs clicked directly on the map. A user can choose the
  exact itinerary day before adding; that explicit choice takes precedence over
  automatic cross-day rebalancing, including when the place already exists on
  another day. A genuinely unavailable day or booked-occurrence conflict leaves
  the trip unchanged and offers available days, Best day, or unbook-and-retry;
  the Map retains the user's place/day inputs. Restaurant POIs persist as meal stops.
- **Common commands**: itinerary export belongs in the desktop command bar and
  supports photo-rich preview, print/save PDF, direct PDF, and email. The account
  control visibly distinguishes a signed-in identity from a local guest.
- **Mutation coherence**: adding/removing a place or changing the stay refreshes
  the complete itinerary, not only one card. Unbooked attractions redistribute
  around the current hotel anchors using geographic proximity and balanced day
  load; booked attractions, hotels, and non-place stops stay fixed.
  Successful mutations always supersede older in-flight reads. Repeated clicks
  for the same removal coalesce, and every removal surface shows a disabled
  pending state until the mutation completes. Adding or removing a place keeps
  that changed place focused in Details, with the opposite action immediately
  available so the decision is easy to reverse.
- **Mutation status**: the latest update sits near the trip identity in a
  flexible command-bar region. Routine add/remove/reflow messages stay concise;
  the region wraps when space is tight instead of clipping the update.

If a redesign violates the above without a stated reason, push back.

## 5) Owner taste — interaction rules

- **Suggestions never disappear** when you pick one. Selected items get a
  green "In trip" pill and stay in the list (Airbnb/TripAdvisor pattern),
  rest of the list still scrollable. No "you picked it, it's gone" UX.
- **Currency is sticky per trip.** Domestic = home currency (INR ₹ default
  via `profile.home_country`). International = USD or local where it makes
  sense, optionally with home-currency equivalent in parens. Prices must
  not flip INR↔USD between sessions.
- **Read-only views render instantly from cache.** Per-destination overview
  uses split caching: backend place details/reviews keep a 1-week TTL while
  signed photo URLs refresh at ~50 minutes (`places_cache.py`), and frontend
  keeps a 30-min response cache in `api.ts` module Map. Background refresh,
  don't block paint.
- **Settings has an "About me" textbox** that runs an LLM extractor and
  **additively** merges into preferences. Never overwrite existing user data.
- **Account details behave like a popover.** The account control toggles it;
  clicking elsewhere or pressing Escape dismisses it.

## 6) Owner taste — code & process

- Python 3.11, typed (`from __future__ import annotations`). One file per
  concern, flat layout under `src/tripplanner/`. Tools = `@tool`-decorated
  functions that return strings; the agent interprets.
- No unnecessary comments. No docstrings on code I didn't touch.
- Tests run in ~1.5s; keep them mock-free for pure logic. Run pytest once
  per milestone, not per micro-edit.
- **Always commit AND push** after every coherent change. Never leave
  unpushed work.
- **No major functional changes without explicit consent.** Refactors and
  structural improvements are fine; new features/behaviors require a yes.
- Update `README.md`, `REQUIREMENTS.txt`, [CODEMAP.md](./CODEMAP.md), and
  [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) in
  the SAME commit as the code change that triggers them.
- Free-tier or near-free everything: Azure ≤ ₹10K/mo, Amadeus test, Google
  Places $200/mo credit, Tavily 1000/mo. Cosmos Free Tier (1000 RU/s + 25 GB).

## 7) Owner taste — agent behavior

- Be terse. 1–3 sentences for simple answers. Skip preamble/conclusion.
- No emojis unless asked.
- Don't start servers — the owner runs `.\scripts\dev-spa.ps1` himself.
- Don't open `http://localhost:8000` in the integrated browser — the owner
  tests in his external browser. Playwright tools only when explicitly asked.
- When something goes wrong, read the dev terminal output and fix; don't ask
  for screenshots.
- Read in 50–200 line chunks; parallelize independent file reads.
- Validate (tsc + pytest + build) ONCE at end of milestone.

## 8) Roadmap signals (loose, not commitments)

- Continuous learning is the moat. Every chat should leave the
  `learned_notes` / `past_trip_mentions` / `interests` / `dislikes` richer.
- The trip panel is the showroom. Anything that makes it feel more like an
  Airbnb listing page (photos, ratings, reviews, attractions) is on-brand.
- Booking handoffs through verified provider actions are a future direction; the
  current "finalize → manual booking" loop is fine for now.

## 9) When this file goes out of date

Update PRODUCT.md the same commit you change vision/scope/taste. If you
ship a feature that demands a new "Non-goal" entry, add it. If a redesign
changes the type/color/shape vocabulary, update §4. If a new run mode
appears, add it to §3. Stale PRODUCT.md = wasted onboarding time for the
next agent session.

