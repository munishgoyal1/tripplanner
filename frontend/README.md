# Trip Planner — React SPA (Option C)

A standalone React single-page app for the AI trip planner. It talks to the
existing FastAPI backend (`src/multiagent/api.py`) over HTTP + Server-Sent
Events — **no Chainlit dependency**. This is the future-facing frontend that
gives full control over the UX (routing, layout, mobile, maps, drag-drop, …).

The Chainlit app (`src/multiagent/web/app.py`) still runs as a fallback during
the migration. Both are just clients of the same agent backend.

## Architecture

```
React SPA (Vite :5173)  ──HTTP/SSE──►  FastAPI (:8000)  ──►  LangGraph trip agent
        │                                    │
        │  GET  /trip/view  ◄────────────────┘  trip_view.build_view()  (shared contract)
        │  POST /trip/select
        └─ POST /chat/stream (tokens + tool steps)
```

The trip-panel data contract is the pure-Python `web/trip_view.py::build_view()`.
TypeScript types in `src/types.ts` mirror it — keep them in sync.

## Run (dev)

From the repo root:

```powershell
scripts\dev-spa.ps1          # starts FastAPI (:8000) + Vite (:5173)
```

Or manually:

```powershell
# Terminal 1 — backend
.venv\Scripts\Activate.ps1
python -m uvicorn multiagent.api:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install      # first time only
npm run dev
```

Open http://localhost:5173. Vite proxies `/api/*` to the FastAPI server, so no
CORS setup is needed in dev. The browser gets a stable `web-<uuid>` user id
(stored in `localStorage`) that keys both chat history and trip state.

## Build (production)

```powershell
cd frontend
npm run build      # outputs to frontend/dist
```

Serve `dist/` from any static host (or behind the API). Set `VITE_API_BASE_URL`
to the deployed API origin and `WEB_ALLOWED_ORIGINS` on the backend to the SPA
origin for CORS.

## Structure

| File | Purpose |
| --- | --- |
| `src/api.ts` | HTTP/SSE client + `user_id` management |
| `src/types.ts` | TypeScript mirror of the `build_view` contract |
| `src/components/ChatPanel.tsx` | streaming chat (tokens + tool steps) |
| `src/components/TripPanel.tsx` | trip view-model renderer (focus + add-to-trip) |
| `src/App.tsx` | two-pane layout, focus/refresh wiring |
