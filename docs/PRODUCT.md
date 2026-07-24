# PRODUCT — tripplanner trip planner

> The "what & why" companion to [CODEMAP.md](./CODEMAP.md) (the "where").
> Keep this short, opinionated, and current. If a feature lands that
> changes the vision/taste/scope, update this file in the same commit.

## 1) Product

A personal AI trip planner that produces a **complete, bookable** trip — not
a list of suggestions. Real flights (Duffel), real hotels & activities
(Amadeus), real ratings & reviews (Google Places), fresh travel content
(Tavily). Single LangGraph agent with 25 tools. Learns from preferences and
past trips and remembers them across devices.

**Target user**: the owner (Munish). One-person product. Optimize for *his*
flow, not a generic SaaS. If it isn't useful to him today, it doesn't ship.

## 2) Non-goals (resist scope creep)

- ❌ Multi-tenant features (orgs, teams, sharing) until explicitly asked.
- ❌ Booking automation beyond `execute_trip` (we link out; we don't card-charge).
- ❌ Mobile app. The SPA must work great on a desktop browser first.
- ❌ Background email/SMS/push notifications (removed Session 1).
- ❌ Calendar/Gmail/Keep integrations (removed Session 1).
- ❌ Generic chatbot vibes. This is a planner, not a friend-bot.

## 3) Run modes

| Mode   | UI                     | Persistence              | When                  |
|--------|------------------------|--------------------------|-----------------------|
| LOCAL  | CLI (`cli.py`) or API  | `~/.tripplanner/*.json`   | dev, hacking          |
| HOSTED | React SPA via FastAPI  | Cosmos DB (Free Tier)    | personal use on ACA   |

One codebase, dispatcher in `storage_cosmos.is_enabled()`.

## 4) Owner taste — the look & feel

Reference points: **Airbnb** and **TripAdvisor** (magazine-style travel
browsing). NOT a corporate dashboard, NOT a chat-toy, NOT generic Bootstrap.

- **Layout**: desktop is a fixed-height spatial planner: itinerary left, a
  persistent dominant map center, and a contextual details inspector right.
  Chat is a collapsible dock inside the inspector and stays mounted while
  hidden. Only panes scroll; the page never does. Map and itinerary can be
  maximized, but there are no dashboard-style resize/move controls. On narrower
  desktops the inspector overlays the map on demand. Mobile mounts chat plus an
  on-demand trip-details sheet.
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
  focus-only navigation never triggers unrelated panel reloads.
- **Itinerary scanning**: each day header shows stop count, planned duration,
  route distance/time/mode, and a direct Maps handoff before the stop details.

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
- Booking handoffs (Duffel `execute_trip`) are a future direction; the
  current "finalize → manual booking" loop is fine for now.

## 9) When this file goes out of date

Update PRODUCT.md the same commit you change vision/scope/taste. If you
ship a feature that demands a new "Non-goal" entry, add it. If a redesign
changes the type/color/shape vocabulary, update §4. If a new run mode
appears, add it to §3. Stale PRODUCT.md = wasted onboarding time for the
next agent session.

