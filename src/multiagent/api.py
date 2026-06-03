"""FastAPI server for the personal assistant.

This is the **frontend-agnostic backend**. The Chainlit app (``web/app.py``)
and the React SPA (``frontend/``) are both just clients of these endpoints —
no UI framework is imported here. The trip-panel data contract lives in the
pure-Python ``web/trip_view.py`` and is served verbatim by ``GET /trip/view``.

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

import json
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

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

# In-memory per-user chat history. Replace with Redis/Cosmos for multi-replica
# hosting; fine for single-process dev and the personal-use footprint.
_HISTORY: dict[str, list[BaseMessage]] = {}
_MAX_HISTORY = 40


def _history(user_id: str) -> list[BaseMessage]:
    return _HISTORY.setdefault(user_id, [])


def _trim(user_id: str) -> None:
    msgs = _HISTORY.get(user_id)
    if msgs and len(msgs) > _MAX_HISTORY:
        _HISTORY[user_id] = msgs[-_MAX_HISTORY:]


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


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    from multiagent.graph import app_graph
    from multiagent.user_context import set_user_id

    set_user_id(req.user_id)
    app_event("api_chat_request", length=len(req.message), words=len(req.message.split()))

    history = _history(req.user_id)
    history.append(HumanMessage(content=req.message))
    result = app_graph.invoke({"messages": history, "current_agent": ""})

    reply = ""
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and msg.content and msg.type == "ai":
            reply = msg.content
            break
    history.append(AIMessage(content=reply))
    _trim(req.user_id)

    app_event("api_chat_response", reply_length=len(reply))
    return ChatResponse(reply=reply, agent=result.get("current_agent", "unknown"))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Stream the agent turn as Server-Sent Events.

    Emits ``token`` (assistant text deltas), ``tool`` (tool start/end), then a
    final ``done`` with the full reply — mirroring the Chainlit experience so
    the SPA gets live typing and tool-progress without coupling to Chainlit.
    """
    from multiagent.graph import app_graph
    from multiagent.user_context import set_user_id

    set_user_id(req.user_id)
    app_event("api_chat_stream_request", length=len(req.message))
    history = _history(req.user_id)
    history.append(HumanMessage(content=req.message))

    async def gen():
        reply_parts: list[str] = []
        try:
            async for ev in app_graph.astream_events(
                {"messages": history, "current_agent": ""}, version="v2"
            ):
                kind = ev.get("event")
                name = ev.get("name", "")
                data = ev.get("data", {}) or {}
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    text = getattr(chunk, "content", "") if chunk is not None else ""
                    if text:
                        reply_parts.append(text)
                        yield _sse("token", {"text": text})
                elif kind == "on_tool_start":
                    yield _sse("tool", {"name": name, "phase": "start"})
                elif kind == "on_tool_end":
                    yield _sse("tool", {"name": name, "phase": "end"})
        except Exception as exc:  # surface a clean error to the client
            app_event("api_chat_stream_error", error=type(exc).__name__)
            yield _sse("error", {"message": "The assistant hit an error. Please retry."})
            return

        reply = "".join(reply_parts)
        history.append(AIMessage(content=reply))
        _trim(req.user_id)
        app_event("api_chat_stream_done", reply_length=len(reply))
        yield _sse("done", {"reply": reply, "agent": "trip"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/trip/view")
async def trip_view_endpoint(
    user_id: str = "local", focus_kind: str = "", focus_name: str = ""
) -> dict:
    """Frontend-agnostic trip-panel view-model (same shape the Chainlit panel
    renders). ``focus_kind``/``focus_name`` optionally zoom one item."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(user_id)
    trip = trip_planner.load_active_trip_dict()
    focus = {"kind": focus_kind, "name": focus_name} if focus_name else None
    return trip_view.build_view(trip, focus)


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


@app.get("/preferences")
async def get_preferences(user_id: str = "local") -> dict:
    """Return the editable subset of the user's saved preferences (for the
    SPA settings panel — mirrors the old Chainlit gear form)."""
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
    }


@app.post("/preferences")
async def save_preferences_endpoint(req: PreferencesRequest) -> dict:
    """Merge the provided preference fields and persist them (additive — only
    keys present in the request are written)."""
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
    prefs_store.save_preferences(prefs)
    app_event("api_preferences_saved")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Google OAuth — standalone (the Chainlit app has its own; both share the
# `google-<sub>` identifier scheme so a user is the same across both UIs).
# All endpoints degrade gracefully: when OAUTH_GOOGLE_CLIENT_ID etc. are unset,
# /auth/me reports {authenticated: false} and the SPA falls back to name/anon.
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
    # Seed the display name on first login (mirrors the Chainlit app).
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
