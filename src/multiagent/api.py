"""FastAPI server for the personal assistant.

This is the **frontend-agnostic backend** that also serves the built React SPA
(``frontend/dist``) at the root origin. The SPA is just a client of these
endpoints — no UI framework is imported here. The trip-panel data contract
lives in the pure-Python ``web/trip_view.py`` and is served verbatim by
``GET /trip/view``.

Endpoints
---------
* ``POST /chat``         — one-shot reply (no streaming), handy for scripts.
* ``POST /chat/stream``  — Server-Sent Events: tokens + tool steps in real time.
* ``GET  /trip/view``    — the trip-panel view-model JSON.
* ``POST /trip/select``  — add a hotel/attraction to the active trip.
* ``GET  /health``       — liveness probe.

Per-user conversation history is kept in a small in-memory store keyed by the
``user_id`` the client sends (the SPA generates a stable ``web-<uuid>`` and
stores it in ``localStorage``). Trip state itself is already persisted per user
by ``trip_planner`` (local JSON or Cosmos), so this store only holds the
in-flight chat turns for context.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from multiagent import config as _config  # noqa: F401  -- import triggers load_dotenv()
from multiagent.observability import app_event, setup_logging
from multiagent.web import oauth

setup_logging()

app = FastAPI(title="Personal Assistant API", version="0.1.0")

# CORS — the SPA runs on a different origin in dev (Vite :5173). Override the
# allowed origins in production via WEB_ALLOWED_ORIGINS (comma-separated).
# Cookie-based OAuth needs credentials, which browsers forbid alongside the
# "*" wildcard — so only enable credentials when explicit origins are set.
# (In dev the SPA talks to the API through the Vite proxy, i.e. same-origin,
# so credentials flow without CORS anyway.)
_origins = [o.strip() for o in os.getenv("WEB_ALLOWED_ORIGINS", "*").split(",") if o.strip()]
_allow_credentials = _origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _strip_api_prefix(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Let the SPA call ``/api/...`` in production the same way it does in dev.

    The API routes live at the root (``/chat``, ``/trip/view``, ...). In dev the
    Vite proxy rewrites ``/api`` away; in production (single origin) we do the
    same rewrite here so one build works in both places.
    """
    path = request.scope.get("path", "")
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)

# Per-user chat history is persisted per active trip via ``web.chat_store`` so
# the conversation + itinerary summary survive a browser refresh and follow
# saved-trip switches. These helpers wrap the load/save dance for both chat
# endpoints (sync and streaming).
def _load_chat() -> tuple[str | None, list[BaseMessage]]:
    """Return (active_trip_id, message history) for the current user."""
    from multiagent.tools.trip_planner import active_trip_id
    from multiagent.web import chat_store

    tid = active_trip_id()
    return tid, chat_store.load(tid)


def _save_chat(tid_before: str | None, history: list[BaseMessage]) -> None:
    """Persist the turn under the trip that's active *after* the turn.

    If a trip was created during the turn (``None`` -> real id), the whole
    pre-trip conversation migrates into the new trip's bucket and the general
    bucket is cleared.
    """
    from multiagent.tools.trip_planner import active_trip_id
    from multiagent.web import chat_store

    tid_after = active_trip_id()
    target = tid_after if tid_after else tid_before
    chat_store.save(target, history)
    if tid_before is None and tid_after and tid_after != tid_before:
        chat_store.clear(None)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "local"


class ChatResponse(BaseModel):
    reply: str
    agent: str


class SelectRequest(BaseModel):
    kind: str
    name: str
    user_id: str = "local"


class TripIdRequest(BaseModel):
    trip_id: str
    user_id: str = "local"


class UserRequest(BaseModel):
    user_id: str = "local"


class StopBookedRequest(BaseModel):
    day: int
    name: str
    booked: bool
    user_id: str = "local"


class PreferencesRequest(BaseModel):
    user_id: str = "local"
    # Editable subset of the structured preferences. All optional — only
    # provided keys are merged (additive, never wiping unspecified fields).
    display_name: str | None = None
    home_city: str | None = None
    home_country: str | None = None
    trip_style: str | None = None
    budget_level: str | None = None
    flight_class: str | None = None
    prefer_direct_flights: bool | None = None
    hotel_star_rating_min: int | None = None
    dietary: list[str] | None = None
    interests: list[str] | None = None
    dislikes: list[str] | None = None
    # Free-text "About me" blurb. When provided and changed, the backend runs
    # the LLM extractor and additively overlays the structured fields it finds.
    about_me: str | None = None


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    from multiagent.graph import app_graph
    from multiagent.usage import cap_message, is_over_cap
    from multiagent.user_context import set_user_id

    set_user_id(req.user_id)
    app_event("api_chat_request", length=len(req.message), words=len(req.message.split()))

    over, usage = is_over_cap(req.user_id)
    if over:
        msg = cap_message(usage)
        app_event("api_chat_capped", cost_usd=usage.get("cost_usd"))
        return ChatResponse(reply=msg, agent="cap")

    history_tid, history = _load_chat()
    history.append(HumanMessage(content=req.message))
    result = app_graph.invoke({"messages": history, "current_agent": ""})

    reply = ""
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and msg.content and msg.type == "ai":
            reply = msg.content
            break
    # Hallucination critic: log unverified prices/times/URLs as telemetry only
    # (internal QA signal — not surfaced to the user to avoid noisy footers).
    from multiagent.hallucination_critic import critique

    issues = critique(reply, result.get("messages", []))
    if issues:
        app_event("hallucination_critic", issues=len(issues), claims=issues)
    history.append(AIMessage(content=reply))
    _save_chat(history_tid, history)

    app_event("api_chat_response", reply_length=len(reply))
    return ChatResponse(reply=reply, agent=result.get("current_agent", "unknown"))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _summarize_tool_input(raw: Any, max_len: int = 160) -> str:
    """Render a one-line preview of a tool's input for the SSE 'tool' event.

    Keeps the panel chatty ("running search_hotels(city='Paris', nights=5)...")
    without flooding the wire with the full payload.
    """
    if raw is None:
        return ""
    payload = raw.get("input") if isinstance(raw, dict) and "input" in raw else raw
    if isinstance(payload, dict):
        parts = []
        for k, v in payload.items():
            if isinstance(v, (list, tuple, dict)):
                vs = json.dumps(v, ensure_ascii=False, default=str)
            else:
                vs = str(v)
            if len(vs) > 40:
                vs = vs[:37] + "..."
            parts.append(f"{k}={vs}")
        text = ", ".join(parts)
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            text = str(payload)
    if len(text) > max_len:
        text = text[: max_len - 1] + "\u2026"
    return text


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Stream the agent turn as Server-Sent Events.

    Emits ``token`` (assistant text deltas), ``tool`` (tool start/end), then a
    final ``done`` with the full reply, so the SPA gets live typing and
    tool-progress over a plain HTTP stream.
    """
    from multiagent.graph import app_graph
    from multiagent.usage import cap_message, is_over_cap
    from multiagent.user_context import set_user_id

    set_user_id(req.user_id)
    app_event("api_chat_stream_request", length=len(req.message))

    over, usage = is_over_cap(req.user_id)
    if over:
        msg = cap_message(usage)
        app_event("api_chat_stream_capped", cost_usd=usage.get("cost_usd"))

        async def _capped():
            yield _sse("token", {"text": msg})
            yield _sse("done", {"reply": msg, "agent": "cap"})

        return StreamingResponse(_capped(), media_type="text/event-stream")

    history_tid, history = _load_chat()
    history.append(HumanMessage(content=req.message))

    async def gen():
        reply_parts: list[str] = []
        tool_starts: dict[str, float] = {}
        # Capture tool message outputs so we can fact-check the agent's final
        # reply against them (hallucination critic).
        tool_outputs: list[ToolMessage] = []
        try:
            async for ev in app_graph.astream_events(
                {"messages": history, "current_agent": ""}, version="v2"
            ):
                kind = ev.get("event")
                name = ev.get("name", "")
                run_id = ev.get("run_id", "")
                data = ev.get("data", {}) or {}
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    text = getattr(chunk, "content", "") if chunk is not None else ""
                    if text:
                        reply_parts.append(text)
                        yield _sse("token", {"text": text})
                elif kind == "on_tool_start":
                    tool_starts[run_id] = time.monotonic()
                    args_preview = _summarize_tool_input(data.get("input"))
                    yield _sse("tool", {
                        "name": name,
                        "phase": "start",
                        "args": args_preview,
                    })
                elif kind == "on_tool_end":
                    started = tool_starts.pop(run_id, None)
                    duration_ms = int((time.monotonic() - started) * 1000) if started else None
                    payload: dict[str, Any] = {"name": name, "phase": "end"}
                    if duration_ms is not None:
                        payload["duration_ms"] = duration_ms
                    output = data.get("output")
                    if output is not None:
                        # ToolNode wraps the result in a ToolMessage; the raw
                        # @tool may also surface a plain string.
                        if isinstance(output, str):
                            tool_outputs.append(ToolMessage(content=output, tool_call_id=name))
                        else:
                            content = getattr(output, "content", None)
                            if content is not None:
                                tool_outputs.append(
                                    ToolMessage(content=content, tool_call_id=name)
                                )
                    yield _sse("tool", payload)
        except Exception as exc:  # surface a clean error to the client
            app_event("api_chat_stream_error", error=type(exc).__name__)
            # Persist whatever we have so a tool side-effect during the turn
            # (e.g. a freshly created trip) doesn't leave the conversation
            # orphaned — otherwise the active trip exists with an empty chat
            # that vanishes on refresh.
            partial = "".join(reply_parts)
            history.append(AIMessage(content=partial or "(interrupted)"))
            try:
                _save_chat(history_tid, history)
            except Exception:
                pass
            yield _sse("error", {"message": "The assistant hit an error. Please retry."})
            return

        reply = "".join(reply_parts)
        # Hallucination critic: log unverified prices/times/URLs as telemetry
        # only (internal QA signal — not surfaced to the user).
        from multiagent.hallucination_critic import critique

        issues = critique(reply, tool_outputs)
        if issues:
            app_event("hallucination_critic", issues=len(issues), claims=issues)
        history.append(AIMessage(content=reply))
        _save_chat(history_tid, history)
        app_event("api_chat_stream_done", reply_length=len(reply))
        yield _sse("done", {"reply": reply, "agent": "trip"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/chat/history")
async def chat_history(user_id: str = "local", trip_id: str = "") -> dict:
    """The persisted transcript for the user's *currently active* trip.

    Lets the SPA restore the conversation + itinerary summary after a refresh,
    and load the right conversation when the user switches saved trips.
    """
    from multiagent.user_context import set_user_id
    from multiagent.tools.trip_planner import active_trip_id
    from multiagent.web import chat_store

    set_user_id(user_id)
    tid = trip_id.strip() or await asyncio.to_thread(active_trip_id) or ""
    rows = await asyncio.to_thread(chat_store.transcript, tid)
    return {"trip_id": tid, "messages": rows}


@app.get("/trip/view")
async def trip_view_endpoint(
    user_id: str = "local", focus_kind: str = "", focus_name: str = ""
) -> dict:
    """Frontend-agnostic trip-panel view-model. ``focus_kind``/``focus_name``
    optionally zoom one item."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(user_id)
    trip = trip_planner.load_active_trip_dict()
    focus = {"kind": focus_kind, "name": focus_name} if focus_name else None
    return await asyncio.to_thread(trip_view.build_view, trip, focus)


@app.get("/maps/config")
async def maps_config_endpoint() -> dict:
    """Expose whether the interactive map is enabled + its browser key.

    The key is a referrer-restricted browser key (see ``config.py``); returning
    it here is the standard pattern for the Maps JavaScript API. Empty key →
    ``enabled: false`` and the SPA hides the map panel.
    """
    from multiagent.config import get_settings

    key = get_settings().google_maps_browser_key or ""
    return {"enabled": bool(key), "key": key}


@app.get("/trip/map")
async def trip_map_endpoint(user_id: str = "local") -> dict:
    """Interactive-map view-model: geocoded, day-tagged pins + route bands."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(user_id)
    trip = trip_planner.load_active_trip_dict()
    return await asyncio.to_thread(trip_view.build_map_view, trip)


@app.get("/destination/overview")
async def destination_overview_endpoint(
    destination: str = "", user_id: str = "local", news: bool = True
) -> dict:
    """Destination-level overview (photos, key attractions, reviews, news).

    When ``destination`` is omitted, falls back to the active trip's
    destination so the SPA can show "about the place" before any selections.
    """
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(user_id)
    if not destination:
        trip = trip_planner.load_active_trip_dict()
        destination = str((trip or {}).get("destination") or "")
    return await asyncio.to_thread(
        trip_view.build_destination_overview, destination, include_news=news
    )



@app.post("/trip/select")
async def trip_select(req: SelectRequest) -> dict:
    """Add a hotel/attraction to the active trip (the SPA's 'Add to trip')."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(req.user_id)
    ok = trip_planner.add_selection(req.kind, {"name": req.name})
    trip = trip_planner.load_active_trip_dict()
    return {"ok": ok, "view": trip_view.build_view(trip, None)}


@app.post("/trip/deselect")
async def trip_deselect(req: SelectRequest) -> dict:
    """Remove a hotel/attraction from the active trip (the SPA's 'Remove')."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(req.user_id)
    ok = trip_planner.remove_selection(req.kind, req.name)
    trip = trip_planner.load_active_trip_dict()
    return {"ok": ok, "view": trip_view.build_view(trip, None)}


@app.get("/trip/itinerary")
async def trip_itinerary_endpoint(user_id: str = "local") -> dict:
    """Structured day-by-day itinerary view-model (the Itinerary tab)."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(user_id)
    trip = trip_planner.load_active_trip_dict()
    return await asyncio.to_thread(trip_view.build_itinerary, trip)


@app.post("/trip/stop/booked")
async def trip_stop_booked(req: StopBookedRequest) -> dict:
    """Toggle one itinerary stop's booked flag (the Itinerary checkbox)."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(req.user_id)
    ok = await asyncio.to_thread(
        trip_planner.set_stop_booked, req.day, req.name, req.booked
    )
    trip = trip_planner.load_active_trip_dict()
    return {"ok": ok, "itinerary": await asyncio.to_thread(trip_view.build_itinerary, trip)}


@app.get("/trips")
async def trips_list(user_id: str = "local") -> dict:
    """All saved trips for the user (the SPA's 'My trips' switcher)."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id

    set_user_id(user_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    return {"trips": trips}


@app.post("/trips/switch")
async def trips_switch(req: TripIdRequest) -> dict:
    """Make a saved trip active (auto-saving whatever was active) and return
    the refreshed trip-panel view."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(req.user_id)
    plan = await asyncio.to_thread(trip_planner.switch_active_trip, req.trip_id)
    if plan is None:
        return {"ok": False, "error": "trip not found"}
    return {"ok": True, "view": trip_view.build_view(plan, None)}


@app.post("/trips/delete")
async def trips_delete(req: TripIdRequest) -> dict:
    """Delete a saved trip; returns the refreshed saved-trips list."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id

    set_user_id(req.user_id)
    await asyncio.to_thread(trip_planner.delete_saved_trip, req.trip_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    return {"ok": True, "trips": trips}


@app.post("/trip/new")
async def trip_new(req: UserRequest) -> dict:
    """Start a fresh planning chat: clear the active trip + the general chat
    bucket so the next conversation begins clean. Saved trips are untouched."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import chat_store

    set_user_id(req.user_id)
    await asyncio.to_thread(trip_planner.start_new_trip)
    await asyncio.to_thread(chat_store.clear, None)
    return {"ok": True}



@app.get("/trip/export.ics")
async def trip_export_ics(user_id: str = "local") -> Response:
    """Download the active trip as an iCalendar (.ics) file."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web.ics_export import build_ics

    set_user_id(user_id)
    plan = trip_planner.load_active_trip_dict()
    body = build_ics(plan)
    dest = ((plan or {}).get("destination") or "trip").lower()
    safe = "".join(c if c.isalnum() else "-" for c in dest).strip("-") or "trip"
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{safe}.ics"'},
    )


@app.post("/trip/share")
async def trip_share(req: SelectRequest) -> dict:
    """Mint an opaque read-only share token for the active trip.

    Re-using ``SelectRequest`` only for its ``user_id`` field — ``kind``/``name``
    are ignored. Returns ``{token, url}`` or ``{error}`` if no active plan.
    """
    from multiagent.user_context import set_user_id
    from multiagent.web.share import mint_for_active_trip

    set_user_id(req.user_id)
    token = mint_for_active_trip()
    if not token:
        return {"error": "no active trip to share"}
    return {"token": token, "url": f"/trip/shared/{token}"}


@app.get("/trip/shared/{token}")
async def trip_shared_view(token: str) -> dict:
    """Public read-only view of a shared trip plan. No auth required."""
    from multiagent.web.share import resolve

    plan = resolve(token)
    if plan is None:
        return JSONResponse(
            {"error": "invalid or expired share link"}, status_code=404
        )
    return {"plan": plan}


@app.get("/preferences")
async def get_preferences(user_id: str = "local") -> dict:
    """Return the editable subset of the user's saved preferences (for the
    SPA settings panel)."""
    from multiagent.tools import user_preferences as prefs_store
    from multiagent.user_context import set_user_id

    set_user_id(user_id)
    prefs = prefs_store.load_preferences()
    profile = prefs.get("profile") or {}
    transport = prefs.get("transport_preferences") or {}
    hotel = prefs.get("hotel_preferences") or {}
    food = prefs.get("food_preferences") or {}
    return {
        "display_name": profile.get("display_name") or "",
        "home_city": profile.get("home_city") or "",
        "home_country": profile.get("home_country") or "",
        "trip_style": prefs.get("trip_style") or "",
        "budget_level": prefs.get("budget_level") or "",
        "flight_class": transport.get("flight_class") or "",
        "prefer_direct_flights": bool(transport.get("prefer_direct_flights", True)),
        "hotel_star_rating_min": int(hotel.get("star_rating_min") or 3),
        "dietary": list(food.get("dietary") or []),
        "interests": list(prefs.get("interests") or []),
        "dislikes": list(prefs.get("dislikes") or []),
        "about_me": prefs.get("about_me") or "",
    }


@app.post("/preferences")
async def save_preferences_endpoint(req: PreferencesRequest) -> dict:
    """Merge the provided preference fields and persist them (additive — only
    keys present in the request are written)."""
    from multiagent.tools import preferences_merge
    from multiagent.tools import user_preferences as prefs_store
    from multiagent.user_context import set_user_id

    set_user_id(req.user_id)
    prefs = prefs_store.load_preferences()
    profile = dict(prefs.get("profile") or {})
    transport = dict(prefs.get("transport_preferences") or {})
    hotel = dict(prefs.get("hotel_preferences") or {})
    food = dict(prefs.get("food_preferences") or {})

    if req.display_name is not None:
        profile["display_name"] = req.display_name.strip() or None
    if req.home_city is not None:
        profile["home_city"] = req.home_city.strip() or None
    if req.home_country is not None:
        profile["home_country"] = req.home_country.strip() or None
    if req.trip_style is not None:
        prefs["trip_style"] = req.trip_style or None
    if req.budget_level is not None:
        prefs["budget_level"] = req.budget_level or None
    if req.flight_class is not None:
        transport["flight_class"] = req.flight_class or None
    if req.prefer_direct_flights is not None:
        transport["prefer_direct_flights"] = req.prefer_direct_flights
    if req.hotel_star_rating_min is not None:
        hotel["star_rating_min"] = max(1, min(5, int(req.hotel_star_rating_min)))
    if req.dietary is not None:
        food["dietary"] = [d.strip() for d in req.dietary if d.strip()]
    if req.interests is not None:
        prefs["interests"] = [d.strip() for d in req.interests if d.strip()]
    if req.dislikes is not None:
        prefs["dislikes"] = [d.strip() for d in req.dislikes if d.strip()]

    prefs["profile"] = profile
    prefs["transport_preferences"] = transport
    prefs["hotel_preferences"] = hotel
    prefs["food_preferences"] = food

    # Free-text About-me: extract structured fields and overlay additively
    # (shared logic in preferences_merge).
    extracted_keys: list[str] = []
    if req.about_me is not None:
        prefs, extracted_keys = preferences_merge.apply_about_me(prefs, req.about_me)

    prefs_store.save_preferences(prefs)
    app_event("api_preferences_saved")
    return {"ok": True, "about_me_extracted": extracted_keys}


# ---------------------------------------------------------------------------
# Google OAuth — standalone HMAC-signed session cookie. Degrades gracefully:
# when OAUTH_GOOGLE_CLIENT_ID etc. are unset, /auth/me reports
# {authenticated: false} and the SPA falls back to name/anon.
# ---------------------------------------------------------------------------
def _secure_cookie(request: Request) -> bool:
    return oauth.redirect_uri(str(request.base_url)).startswith("https://")


@app.get("/auth/config")
async def auth_config(request: Request) -> dict:
    """Tells the SPA whether to show the 'Sign in with Google' button, and
    surfaces the exact redirect URI the backend will hand to Google — copy
    this verbatim into the Google Cloud Console 'Authorized redirect URIs'
    list to avoid redirect_uri_mismatch."""
    return {
        "google": oauth.is_enabled(),
        "redirect_uri": oauth.redirect_uri(str(request.base_url)),
    }


@app.get("/auth/me")
async def auth_me(request: Request) -> dict:
    """Return the signed-in identity (from the session cookie) or anonymous."""
    session = oauth.read_session(request.cookies.get(oauth.SESSION_COOKIE))
    if not session:
        return {"authenticated": False}
    return {"authenticated": True, **session}


@app.get("/auth/login/google")
async def auth_login_google(request: Request, redirect: str = "/") -> RedirectResponse:
    """Kick off the authorization-code flow → redirect the browser to Google."""
    if not oauth.is_enabled():
        return RedirectResponse(redirect or "/", status_code=302)
    callback = oauth.redirect_uri(str(request.base_url))
    url, state_token = oauth.build_authorize_url(callback, redirect or "/")
    res = RedirectResponse(url, status_code=302)
    res.set_cookie(
        "mg_oauth_state",
        state_token,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(request),
        path="/",
    )
    return res


@app.get("/auth/callback/google")
async def auth_callback_google(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> RedirectResponse:
    """Google redirects here with ?code. Exchange it, set the session cookie,
    then bounce back to the SPA path the user started from."""
    post_login = oauth.verify_state(request.cookies.get("mg_oauth_state"), state)
    if error or not code or post_login is None:
        app_event("api_oauth_callback_rejected", reason=error or "bad_state")
        res = RedirectResponse("/?auth=failed", status_code=302)
        res.delete_cookie("mg_oauth_state", path="/")
        return res

    callback = oauth.redirect_uri(str(request.base_url))
    try:
        profile = await oauth.exchange_code(code, callback)
    except Exception as exc:
        app_event("api_oauth_exchange_error", error=type(exc).__name__)
        res = RedirectResponse("/?auth=failed", status_code=302)
        res.delete_cookie("mg_oauth_state", path="/")
        return res

    identifier = profile["identifier"]
    # Seed the display name on first login.
    try:
        from multiagent.tools import user_preferences as prefs_store
        from multiagent.user_context import set_user_id

        set_user_id(identifier)
        prefs = prefs_store.load_preferences()
        profile_blob = dict(prefs.get("profile") or {})
        if not profile_blob.get("display_name") and profile.get("name"):
            profile_blob["display_name"] = profile["name"].split()[0]
            prefs["profile"] = profile_blob
            prefs_store.save_preferences(prefs)
    except Exception:
        pass  # profile seeding is best-effort; never block login

    app_event("api_oauth_login", provider="google")
    token = oauth.make_session_token(
        identifier, profile.get("name", ""), profile.get("email", ""), profile.get("picture", "")
    )
    res = RedirectResponse(post_login or "/", status_code=302)
    res.delete_cookie("mg_oauth_state", path="/")
    res.set_cookie(
        oauth.SESSION_COOKIE,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(request),
        path="/",
    )
    return res


@app.post("/auth/logout")
async def auth_logout() -> JSONResponse:
    res = JSONResponse({"ok": True})
    res.delete_cookie(oauth.SESSION_COOKIE, path="/")
    return res


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics/tools")
async def metrics_tools() -> dict:
    """Return per-tool latency + error + cache-hit counters.

    In-process only — accumulated for the lifetime of the current container.
    Intended for live introspection during a session; long-horizon data lives
    in Log Analytics via the structured ``tool_call`` events.
    """
    from multiagent.observability import tool_metrics_snapshot

    return {"tools": tool_metrics_snapshot()}


@app.get("/usage")
async def usage_for_user(user_id: str = "local") -> dict:
    """Return this month's LLM token + cost usage for ``user_id`` and the cap."""
    from multiagent.usage import get_cap_usd, get_usage, is_over_cap

    over, doc = is_over_cap(user_id)
    return {
        "user_id": user_id,
        "month": doc.get("month"),
        "prompt_tokens": doc.get("prompt_tokens", 0),
        "completion_tokens": doc.get("completion_tokens", 0),
        "calls": doc.get("calls", 0),
        "cost_usd": round(float(doc.get("cost_usd", 0.0)), 4),
        "cap_usd": get_cap_usd(),
        "over_cap": over,
    }


# ---------------------------------------------------------------------------
# Static SPA — serve the built React frontend (frontend/dist) so a single
# container/origin hosts both the API and the UI. Registered LAST so it never
# shadows an API route; the catch-all returns index.html for client-side
# routing. Skipped entirely when the build is absent (pure-API dev runs).
# ---------------------------------------------------------------------------
from pathlib import Path  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_SPA_DIST = (
    Path(os.environ["SPA_DIST_DIR"])
    if os.environ.get("SPA_DIST_DIR")
    else Path(__file__).resolve().parents[2] / "frontend" / "dist"
)

if (_SPA_DIST / "index.html").is_file():
    _assets = _SPA_DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/", include_in_schema=False)
    async def _spa_index() -> FileResponse:
        return FileResponse(str(_SPA_DIST / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_catchall(full_path: str) -> FileResponse:
        target = _SPA_DIST / full_path
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_SPA_DIST / "index.html"))
