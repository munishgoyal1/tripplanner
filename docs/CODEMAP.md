# CODEMAP — multiagent

> Drop-in orientation for any new agent session or human contributor.
> If something here is wrong, fix it in the same commit as the code change.
> Keep it short — link out to the file, don't duplicate the file.

## 1) One-paragraph summary

AI-powered trip planner. Single LangGraph trip agent with 25 tools (flights,
hotels, activities, places, web, plan lifecycle, user preferences). One FastAPI
process (`api.py`) does double duty: serves the API and hosts the built React
SPA from [frontend/dist](../frontend) at the root. Persistence is local JSON in
dev and Cosmos DB in production. Auto-dispatch via `storage_cosmos.is_enabled()`
(true when `COSMOS_ENDPOINT` is set). Identity is per-request through
`user_context.get_user_id()` (ContextVar, default `"local"`).

## 2) Run / validate (copy-paste)

| Goal             | Command                                                    |
|------------------|------------------------------------------------------------|
| Run full stack   | `.\scripts\dev-spa.ps1`                                    |
| Backend only     | `.\scripts\dev-spa.ps1 -BackendOnly`                       |
| Frontend only    | `.\scripts\dev-spa.ps1 -FrontendOnly`                      |
| Verbose backend  | `.\scripts\dev-spa.ps1 -Logs`                              |
| Tests            | `.\.venv\Scripts\python.exe -m pytest -q`                  |
| Type-check SPA   | `cd frontend; npx tsc --noEmit`                            |
| Build SPA        | `cd frontend; npm run build`                               |
| Deploy           | See [infra/README.md](../infra/README.md)                  |

`scripts/test.ps1` is **legacy** (Chainlit era). Don't use it.

## 3) Top-level layout

```
src/multiagent/
  api.py              FastAPI app — routes, SSE chat, /api prefix strip, SPA mount
  cli.py              Local CLI entrypoint (no SPA)
  config.py           Pydantic Settings from .env
  graph.py            LangGraph StateGraph: agent ↔ tools loop
  observability.py    OpenTelemetry / Azure Monitor (best-effort)
  storage_cosmos.py   Cosmos DB persistence (lazy; on iff COSMOS_ENDPOINT set)
  user_context.py     ContextVar holding the current user_id per request
  agents/
    trip_agent.py     Single trip-planning agent — system prompt + 25 @tools
  tools/
    duffel_flights.py     Primary flight provider
    flight_search.py      Amadeus fallback (Amadeus self-service EOL 2026-07-17)
    hotel_search.py       Amadeus hotels
    activities_search.py  Amadeus activities + POI
    amadeus_client.py     Shared Amadeus auth/HTTP
    google_places.py      Places API New (search/reviews/photos)
    routing.py            Google Routes API v2 (travel time + day optimizer)
    web_search.py         Tavily
    trip_planner.py       Trip lifecycle: create/get/update/finalize/execute/list
    user_preferences.py   Preferences CRUD (atomic write + tolerant load)
    preferences_merge.py  Additive merge used by api.py (no UI imports)
    about_me_extractor.py LLM extractor for the "About me" textbox in Settings
  web/
    oauth.py          Standalone Google OAuth, HMAC mg_session cookie
    trip_view.py      PURE-PYTHON view-model (build_view, build_destination_overview)
    places_cache.py   Google Places cache (ThreadPoolExecutor, 30-min TTL)
frontend/
  index.html          Loads Google Fonts via <link> (NOT from CSS)
  vite.config.ts      Dev: proxies /api → :8000
  tailwind.config.js  Design tokens: coral brand, teal accent, ink/muted/surface,
                      shadow-card/-pop, rounded-4xl, Inter + Fraunces
  src/
    main.tsx          React 19 root
    App.tsx           Layout: chat ‖ resizable divider ‖ trip panel
    api.ts            All HTTP/SSE + auth glue + per-destination overview cache
    types.ts          Shared TS contracts (TripView, TripItem, Preferences, …)
    index.css         Tailwind + reusable .card/.btn-primary/.btn-ghost/.pill/.chip
    components/
      ChatPanel.tsx        Sticky header, message bubbles, composer
      TripPanel.tsx        Hero summary + NavStrip + ItemCard
      DestinationOverview.tsx  Hero photo + summary + attractions + reviews + news
      SettingsModal.tsx    Identity + Preferences + About-me extractor
      Lightbox.tsx         Full-screen photo viewer
infra/
  main.bicep          ACA + Cosmos Free Tier + Log Analytics
  main.bicepparam     Default param values (keep API version aligned)
  README.md           Walkthrough
scripts/
  dev-spa.ps1         THE dev entrypoint (use this)
  autoheal.ps1        Legacy auto-heal watcher (Chainlit era)
  smoke_test.py       Smoke check
  test.ps1            Legacy (Chainlit era) — do not use
tests/                pytest (179 tests, ~2s)
docs/
  CODEMAP.md          This file
  dev.md              Dev environment notes
  setup-oauth.md      OAuth setup walkthrough
```

## 4) Request flow (hosted mode)

```
Browser (frontend/dist)
  └─ fetch /api/chat/stream  ──▶  FastAPI _strip_api_prefix middleware
                                     ──▶ app.post("/chat/stream")  (api.py)
                                            ──▶ graph.py: agent ↔ tools loop
                                                  ──▶ tools/* (Duffel, Places, …)
                                                  ──▶ storage_cosmos OR local JSON
                                            ──▶ SSE events back to the SPA
```

The same FastAPI app serves `frontend/dist` at `/` so production = one container,
one origin. In dev, Vite serves on :5173 and proxies `/api` to :8000.

## 5) View-model contract (decoupled from UI)

`src/multiagent/web/trip_view.py` is **pure Python with zero UI imports**.
It exports:

- `build_view(trip, focus) -> dict` — the JSON shape consumed by
  `GET /trip/view` and rendered by [TripPanel.tsx](../frontend/src/components/TripPanel.tsx).
  Merges selected items with deduped destination top-places so the panel never
  collapses. Selected items get an `"In trip"` marker.
- `build_destination_overview(destination) -> dict` — hero photo, summary,
  attractions, reviews, Tavily news. Backed by `places_cache.py`.

If you change the shape, update tests in [tests/test_trip_view.py](../tests/test_trip_view.py)
AND the consumer in `TripPanel.tsx` / `DestinationOverview.tsx`.

## 6) Identity & persistence

- Per-request user_id lives in `user_context.get_user_id()` (ContextVar).
  Default `"local"` (CLI). Hosted mode sets it from the OAuth/guest cookie.
- OAuth (Google): `"google-<sub>"` (cross-device). Signed HttpOnly `mg_session`
  cookie, HMAC-SHA256 with `WEB_SESSION_SECRET` (back-compat fallback
  `CHAINLIT_AUTH_SECRET`).
- Guest fallback: `"web-<uuid>"` (per-browser via localStorage).
- Persistence dispatcher: `storage_cosmos.is_enabled()` → Cosmos if true, else
  local JSON under `~/.multiagent/`.
- Cosmos containers: `users` (one doc per user: `preferences`, `active_trip`)
  and `trips` (archived/finalized trips).

## 7) Landmines (cycles already burned)

- **CSS `@import` after `@tailwind`** breaks PostCSS. Use `<link>` in
  `frontend/index.html` for fonts. (Fixed Session 14.)
- **Tailwind brand utilities**: `brand` palette has `DEFAULT` so `bg-brand`,
  `text-brand`, `ring-brand` all keep working. Shades available: 50/100/500/600/700.
- **Azure OpenAI API version**: must be `2024-10-21`. `2024-11-20` is a model
  snapshot, not a data-plane version, and yields 404 NotFoundError.
- **`/api` prefix**: stripped by middleware in production. In dev, hit endpoints
  without `/api` if calling FastAPI directly.
- **Currency rule**: trip agent prompt CRITICAL RULE 8 picks ONE sticky display
  currency per plan (home currency for domestic, USD/local for international).
  Don't let prices flip INR↔USD between sessions.
- **Local prefs race**: always atomic write + tolerant load in
  `tools/user_preferences.py`. `JSONDecodeError: line 1 column 1 (char 0)` is
  almost always a 0-byte file, not a schema bug.
- **`Chainlit` references** anywhere in code/docs/scripts are STALE (removed
  Session 13). Don't reintroduce them.
- **`tsconfig.tsbuildinfo`** is a build artifact (in `frontend/.gitignore`).
  If tsc behaves weirdly after big edits, delete it and re-run.

## 8) Tests (167 passing)

- [tests/test_trip.py](../tests/test_trip.py) — trip lifecycle + selection.
- [tests/test_trip_view.py](../tests/test_trip_view.py) — view-model shape.
- [tests/test_about_me_extractor.py](../tests/test_about_me_extractor.py),
  [tests/test_apply_about_me.py](../tests/test_apply_about_me.py),
  [tests/test_about_me_additive_merge.py](../tests/test_about_me_additive_merge.py) —
  About-me extractor + additive merge.
- [tests/test_observability.py](../tests/test_observability.py) — OTel wiring.

All pytest. Run them with `.\.venv\Scripts\python.exe -m pytest -q`.

## 9) Process rules (per the owner)

- **Always commit AND push** after every coherent change.
- **No major functional changes** without explicit consent.
- Keep it **simple and modular**; no over-engineering.
- Update `REQUIREMENTS.txt` when new requirements come in.
- Update `README.md` when architecture changes.
- Update [`.github/copilot-instructions.md`](../.github/copilot-instructions.md)
  AND this CODEMAP whenever the structure shifts.
