# CODEMAP — tripplanner

> Drop-in orientation for any new agent session or human contributor.
> If something here is wrong, fix it in the same commit as the code change.
> Keep it short — link out to the file, don't duplicate the file.

## 1) One-paragraph summary

AI-powered trip planner. Single LangGraph trip agent with 25 tools (flights,
hotels, activities, places, web, plan lifecycle, user preferences). One FastAPI
process (`api.py`) does double duty: serves the API and hosts the built React
SPA from [frontend/dist](../frontend) at the root. Persistence is the local
Cosmos DB Emulator in SPA development, local JSON for an unconfigured CLI, and
a shared free-tier Cosmos account in hosted environments. Auto-dispatch via `storage_cosmos.is_enabled()`
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
| Frontend tests   | `cd frontend; npm test -- --run`                            |
| Browser smoke    | `cd frontend; npm run test:e2e`                             |
| Start/check Cosmos emulator | `.\infra\start-cosmos-emulator.ps1`           |
| Deploy           | See [infra/README.md](../infra/README.md)                  |

`scripts/test.ps1` is **legacy** (Chainlit era). Don't use it.

## 3) Top-level layout

```
src/tripplanner/
  api.py              FastAPI app — routes, SSE chat, /api prefix strip, SPA mount
  cli.py              Local CLI entrypoint (no SPA)
  config.py           Pydantic Settings from .env
  graph.py            LangGraph StateGraph: agent ↔ tools loop
                      (binds only select_tools(messages) per turn)
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
    place_hours.py        Opening-hours + closure check (catches "Louvre Tue")
    routing.py            Google Routes API v2 (travel time + day optimizer)
    weather.py            Open-Meteo forecast + archive (seasonal estimate)
    visa.py               Tavily-backed visa & entry rules (prefers .gov / IATA)
    events.py             Tavily-backed local events / festivals / public holidays
    memory_recall.py      BM25-lite recall over learned notes / past trips / family
    web_search.py         Tavily
    trip_planner.py       Trip lifecycle: create/get/update/finalize/execute/list
                          + remembered saved trips (resume/switch/delete); warns
                          the agent when restaurant itinerary planning is incomplete
    user_preferences.py   Preferences CRUD (atomic write + tolerant load)
    preferences_merge.py  Additive merge used by api.py (no UI imports)
    about_me_extractor.py LLM extractor for the "About me" textbox in Settings
  web/
    oauth.py          Standalone Google OAuth, HMAC mg_session cookie
    trip_view.py      PURE-PYTHON view-model (build_view, build_destination_overview,
                      build_map_view, build_itinerary — structured day-by-day stops)
    chat_store.py     PURE-PYTHON per-trip chat transcript persistence
                      (Cosmos users/chat_<trip_id> or local chats/<trip_id>.json)
    places_cache.py   Google Places cache (ThreadPoolExecutor; 1-week details TTL +
                      50-min photo-URL TTL; persisted L2 — Cosmos places_cache or
                      local cache.json — survives restarts; surfaces lat/lng)
    itinerary_export.py  Print-ready HTML export with optional photos, daily route
              diagrams/links/QR codes, and minimal/detailed/family themes
frontend/
  index.html          Loads Google Fonts via <link> (NOT from CSS)
  vite.config.ts      Dev: proxies /api → :8000
  tailwind.config.js  Design tokens: coral brand, teal accent, ink/muted/surface,
                      shadow-card/-pop, rounded-4xl, Inter + Fraunces
  src/
    main.tsx          React 18 root
    App.tsx           Responsive workspace owner. Desktop: fixed 100dvh spatial
          planner with itinerary left, persistent map center, contextual
          right dock with independently hidden mounted Details/Assistant; no
          page scroll. Top command/status bar owns saved-trip selection,
        New trip, pane visibility, export, lifecycle/completeness, cost, and
        latest mutation result; desktop account/preferences and login status
        live here too. Shared place/day focus synchronizes itinerary, map,
        and details.
          Persistent mouse/keyboard separators resize all
              desktop pane splits. Four-pane maximize/restore, request cancellation,
              shared map/details place focus. Mobile: chat + on-demand trip-details
              sheet. Only the active responsive shell mounts.
    workspaceState.ts Canonical reducer for trip identity/revision, active place,
              chat reload, and itinerary jump state
    api.ts            All HTTP/SSE + auth glue + per-destination overview cache
    types.ts          Shared TS contracts (TripView, TripItem, Preferences, …)
    index.css         Tailwind + reusable .card/.btn-primary/.btn-ghost/.pill/.chip
    components/
      ChatPanel.tsx        Bubbles/composer + mounted account/settings dialogs;
               mobile header owns launchers, desktop top row triggers them
      TripPanel.tsx        Hero summary + NavStrip + recommendation ItemCards
      TripSwitcher.tsx     Persistent saved-trip switch/delete control; dropdown
               overlays all workspace panes
      ExportModal.tsx      Print/PDF/email export options and handoff
      RightRail.tsx        Mobile trip-details sheet: TripSwitcher + stacked
               itinerary/photos + opt-in lazy map
      ItineraryPanel.tsx   Compact day summary + clickable stops + booked checkbox
      DestinationOverview.tsx  Hero photo + summary + attractions + reviews + news
      MapPanel.tsx         Interactive Google map: day-colored pins + route bands
                           (place focus highlights pins; day focus jumps itinerary
                           and sends a representative place to Details)
      SettingsModal.tsx    Identity + Preferences + About-me extractor
      Lightbox.tsx         Full-screen photo viewer
  playwright.config.ts     Chrome-channel desktop + Pixel 7 smoke projects
  vitest.config.ts         jsdom unit/component test configuration
infra/
  data-stack.bicep    Subscription orchestration for shared data RG/account
  data.bicep          Shared free-tier Cosmos data plane
  modules/cosmos-data.bicep  Two 400-RU/s databases + runtime containers
  main.bicep          ACA + Log Analytics; references existing shared Cosmos
  canary.bicepparam   Canary app parameters (`tripplanner-canary` database)
  prod.bicepparam     Production app parameters (`tripplanner-prod` database)
  cosmos-emulator.compose.yml  Portable local Cosmos DB Emulator
  README.md           Walkthrough
scripts/
  dev-spa.ps1         THE dev entrypoint; starts/uses local Cosmos Emulator
  cosmos_copy.py      Copy + exact verification across Cosmos databases
  autoheal.ps1        Legacy auto-heal watcher (Chainlit era)
  smoke_test.py       Smoke check
  test.ps1            Legacy (Chainlit era) — do not use
tests/                pytest (322 tests, ~5s)
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

`src/tripplanner/web/trip_view.py` is **pure Python with zero UI imports**.
It exports:

- `build_view(trip, focus) -> dict` — the JSON shape consumed by
  `GET /trip/view` and rendered by [TripPanel.tsx](../frontend/src/components/TripPanel.tsx).
  Merges selected items with deduped destination top-places so the panel never
  collapses. Selected items get an `"In trip"` marker. `overview.budget` is the
  live budget meter (see `build_budget`).
- `build_budget(trip) -> dict | None` — pure-aggregation budget meter: running
  spend (prefers `total_cost`, falls back to per-item price sums), per-traveler
  split, category breakdown, and remaining-vs-`budget` bar. Uses the plan's
  sticky `currency` via `currency_symbol`. Returns `None` (panel hides it) when
  there's no spend and no target.
- `build_destination_overview(destination) -> dict` — hero photo, summary,
  attractions, reviews, Tavily news. Backed by `places_cache.py`.
- `build_map_view(trip) -> dict` — interactive-map view-model: geocoded pins
  for selected hotels/activities + destination suggestions, each tagged with
  its itinerary day (structured `stops` first, else prose `plan` match),
  grouped into day-colored route bands, plus an arrival-airport pin and map
  center. Each day now includes estimated route metrics
  (`distance_km/duration_min/mode` plus display strings) derived from the day
  path so the UI can show day-wise travel distance/time/mode without billed
  Directions calls. Structured places can participate in multiple day bands,
  and each band closes from/to the selected hotel. `enabled` mirrors whether
  `GOOGLE_MAPS_BROWSER_KEY` is set. Served by
  `GET /trip/map`; the browser key comes from `GET /maps/config`. Rendered by
  [MapPanel.tsx](../frontend/src/components/MapPanel.tsx), which lazily loads
  the Maps JavaScript API and draws geodesic per-day route lines client-side
  (no billed Directions API). Structured restaurant/meal stops retain their
  place kind, dedupe by name, and join ordered day circuits.
- `build_itinerary(trip) -> dict` — structured day-by-day itinerary:
  `days[{day,date,title,summary,color,stops[{name,kind,time,duration_min,note,
  booked,selected,color}]}]` + `stats{days,stops,booked}`. `_normalize_stop` /
  `_infer_stop_kind` turn string OR dict stops into structured dicts. Served by
  `GET /trip/itinerary`; `trip_planner.set_stop_booked(day,name,booked)` (behind
  `POST /trip/stop/booked`) persists a stop's booked flag (normalizing string
  stops to dicts). Rendered by
  [ItineraryPanel.tsx](../frontend/src/components/ItineraryPanel.tsx); clicking a
  place stop focuses the Photos section, the 📍 button reveals it on the Map.
  When a trip has no structured `day_wise_itinerary` yet,
  `_itinerary_from_selections` synthesizes a single "Your picks so far" day from
  the selected hotels/activities so the panel is never blank.

UI add/remove actions call `trip_planner.add_selection` / `remove_selection`.
Every hotel or attraction mutation runs `_reflow_unbooked_attractions`: hotel
anchors, booked attractions, and non-place stops remain fixed while unbooked
attractions are reassigned by proximity and balanced day load. The API returns
the resulting alert so `App.tsx` can show the latest mutation outcome in the
workspace command bar while refreshing the full trip view.

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
  local JSON under `~/.tripplanner/`.
- Cosmos containers: `users` (one doc per user: `preferences`, `active_trip`)
  and `trips` (every saved trip — drafts, finalized, and booked). Also
  `tool_cache` (read-through tool results) and `places_cache` (durable Google
  Places cache — one shared doc, partition `_shared`).
- **Places cache (Session 22)**: `places_cache.py` is a two-layer cache —
  in-process dict (hot) + durable store (Cosmos `places_cache` or local
  `~/.tripplanner/places_cache/cache.json`). Place details/reviews/top-places
  keep a 1-week TTL; signed photo URLs keep a 50-min TTL and are re-resolved
  on demand from long-lived `photo_refs` (URLs are NEVER persisted). Public
  fns take `refresh=True` to force re-fetch; `prefetch` batches the durable
  write.
- **Saved trips (Session 19)**: every `_save_active_trip` mirrors the plan into
  the `trips` collection keyed by a stable `trip_id = slug(destination)_dep_ret`.
  Same destination + same dates → same id → `create_trip_plan` RESUMES (keeps
  selections) instead of overwriting; different dates/duration → different id →
  kept as a separate, date-tagged trip. So no in-progress trip is ever lost
  when the user starts another or logs back in. Non-tool helpers
  `list_saved_trips()` / `switch_active_trip(id)` / `delete_saved_trip(id)`
  power the SPA's "My trips" switcher (`GET /trips`, `POST /trips/switch`,
  `POST /trips/delete`); the agent tool `resume_trip(destination|trip_id)` lets
  the assistant offer to continue a saved plan.
- **Fresh trips (Session 22)**: `POST /trip/new` → `trip_planner.start_new_trip()`
  clears the active-trip pointer (saved trips untouched, already mirrored to
  `trips`) and resets the chat; the SPA exposes it via the ChatPanel "New trip"
  button. `/chat/stream`'s error path now saves the partial transcript so a
  tool side-effect (e.g. `create_trip_plan`) can never orphan the chat.

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

## 8) Tests (408 passing)

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

