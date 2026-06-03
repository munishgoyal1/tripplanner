"""Chainlit chat UI for the trip planner.

Runs as: ``chainlit run src/multiagent/web/app.py``

Identity model (in order of precedence per request):

1. **OAuth** — when ``OAUTH_<PROVIDER>_CLIENT_ID/SECRET`` env vars are set
   AND ``CHAINLIT_AUTH_SECRET`` is set, users can sign in with Google or
   GitHub via Chainlit's built-in OAuth. The identifier becomes
   ``"{provider}-{external_id}"`` (e.g. ``google-12345``).
2. **Persistent guest cookie** — if the user is not authenticated, a
   long-lived ``multiagent_guest_id`` cookie is issued on first visit and
   reused across sessions. Identifier becomes ``"guest-<uuid>"``.
3. **Per-session fallback** — if cookies are unavailable, Chainlit's
   ephemeral session id is used. This is the legacy path.

All three identities flow into ``multiagent.user_context.set_user_id``, so
preferences and trip plans persist correctly per user in Cosmos DB.

Facebook OAuth is NOT wired here because Chainlit's built-in OAuth providers
don't include it; see ``docs/setup-oauth.md`` for the custom-flow path.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import chainlit as cl
from langchain_core.messages import AIMessage, HumanMessage

from multiagent.graph import app_graph
from multiagent.user_context import set_user_id

log = logging.getLogger(__name__)

WELCOME_BASE = (
    "\u2708\ufe0f **Trip Planner**\n\n"
    "Tell me where you'd like to go and I'll plan it end-to-end \u2014 flights, "
    "hotels, activities and a day-wise itinerary.\n\n"
    "_The first reply for a fresh request can take ~10\u201320s while I search "
    "flights, hotels and reviews. You'll see each search appear as a step "
    "above the reply so you know what's happening._\n\n"
    "**Try one of:**\n"
    "- _Plan a 5-day family trip to Goa in January for 2 adults and 1 child_\n"
    "- _Weekend getaway from Bangalore to Coorg next month, mid budget_\n"
    "- _10 days in Japan in April, history and food, $4k total_"
)

_SIGN_IN_HINT_TEMPLATE = (
    "\n\n---\n"
    "\U0001f511 _You're chatting as a guest. "
    "[Sign in with Google]({url}) to keep your preferences across devices._"
)

_GUEST_COOKIE = "multiagent_guest_id"
_GUEST_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year
_SIGNIN_INTENT_COOKIE = "mg_signin"
_SIGNIN_INTENT_MAX_AGE = 600  # 10 minutes — long enough to finish OAuth


def _parse_cookies(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for chunk in (cookie_header or "").split(";"):
        chunk = chunk.strip()
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def _oauth_configured() -> bool:
    return any(
        os.environ.get(f"OAUTH_{p}_CLIENT_ID") and os.environ.get(f"OAUTH_{p}_CLIENT_SECRET")
        for p in ("GOOGLE", "GITHUB")
    )


def _sign_in_url() -> str:
    """Build an absolute URL to ``/sign-in``.

    Chainlit's React markdown renderer only treats links as external (i.e.
    real browser navigation, honoring ``target='_blank'``) when the href has
    an explicit ``http(s)://`` scheme. Relative paths are caught by the SPA
    router and bounce back to ``/``. We derive the origin from the WebSocket
    request environ, falling back to ``CHAINLIT_URL`` or localhost.
    """
    try:
        environ = cl.context.session.environ or {}
    except Exception:
        environ = {}
    host = environ.get("HTTP_HOST") or environ.get("HTTP_X_FORWARDED_HOST")
    if host:
        proto = (
            environ.get("HTTP_X_FORWARDED_PROTO")
            or environ.get("wsgi.url_scheme")
            or "http"
        )
        return f"{proto}://{host}/sign-in"
    base = os.environ.get("CHAINLIT_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/sign-in"


def _last_ai_message(messages: list) -> AIMessage | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg
    return None


# ---------------------------------------------------------------------------
# Authentication callbacks (only active when CHAINLIT_AUTH_SECRET is set)
# ---------------------------------------------------------------------------
def _auth_secret_present() -> bool:
    return bool(os.environ.get("CHAINLIT_AUTH_SECRET"))


if _auth_secret_present():

    @cl.oauth_callback
    def oauth_callback(
        provider_id: str,
        token: str,
        raw_user_data: dict[str, Any],
        default_user: cl.User,
    ) -> cl.User | None:
        """Map an OAuth login to a stable user identifier.

        ``provider_id`` will be one of the providers configured via env vars
        (e.g. ``"google"``, ``"github"``). The external user id is read from
        the provider's raw payload (``sub`` for Google, ``id``/``login`` for
        GitHub). We prefix with the provider so identifiers can't collide.
        """
        external_id = (
            raw_user_data.get("sub")
            or raw_user_data.get("id")
            or raw_user_data.get("login")
            or default_user.identifier
        )
        identifier = f"{provider_id}-{external_id}"
        metadata = {
            "provider": provider_id,
            "email": raw_user_data.get("email"),
            "name": raw_user_data.get("name") or raw_user_data.get("login"),
            "picture": raw_user_data.get("picture") or raw_user_data.get("avatar_url"),
            "role": "user",
        }
        return cl.User(identifier=identifier, metadata=metadata)

    @cl.header_auth_callback
    def header_auth_callback(headers: dict) -> cl.User | None:
        """Issue / read a persistent guest cookie so non-logged-in users keep
        the same identity across browser sessions.

        Chainlit invokes this on every request when auth is configured. We
        only return a guest user — the OAuth callback above takes precedence
        if the user has actually signed in. Returning ``None`` causes Chainlit
        to redirect to the login screen, which we use for the explicit
        "Sign in with Google" flow (see ``/sign-in`` route).
        """
        cookies = _parse_cookies(headers.get("cookie") or headers.get("Cookie") or "")
        if cookies.get(_SIGNIN_INTENT_COOKIE) == "1":
            return None
        guest_id = cookies.get(_GUEST_COOKIE) or f"guest-{uuid.uuid4()}"
        identifier = guest_id if guest_id.startswith("guest-") else f"guest-{guest_id}"
        return cl.User(identifier=identifier, metadata={"role": "guest"})

    # Starlette middleware to set the guest cookie when missing on a response.
    # Imported lazily so unit-test imports don't pull in Chainlit's server.
    try:  # pragma: no cover - exercised at runtime
        from chainlit.server import app as _chainlit_app
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import RedirectResponse

        class _AuthFlowMiddleware(BaseHTTPMiddleware):
            """Handle ``/sign-in`` upgrades and persistent guest cookies.

            Chainlit registers a catch-all route for the React SPA, so a
            normal ``add_route`` call for ``/sign-in`` is shadowed. Doing the
            work in middleware guarantees we run before route matching.
            """

            async def dispatch(self, request, call_next):
                if request.url.path == "/sign-in" and request.method == "GET":
                    response = RedirectResponse(url="/login", status_code=303)
                    response.delete_cookie(_GUEST_COOKIE)
                    response.set_cookie(
                        key=_SIGNIN_INTENT_COOKIE,
                        value="1",
                        max_age=_SIGNIN_INTENT_MAX_AGE,
                        httponly=True,
                        samesite="lax",
                    )
                    return response
                response = await call_next(request)
                signin_intent = request.cookies.get(_SIGNIN_INTENT_COOKIE) == "1"
                # Once the OAuth handshake has issued a session JWT, drop the
                # sign-in intent cookie so it doesn't keep forcing /login.
                if signin_intent and request.url.path.startswith("/auth/oauth/"):
                    response.delete_cookie(_SIGNIN_INTENT_COOKIE)
                    signin_intent = False
                if _GUEST_COOKIE not in request.cookies and not signin_intent:
                    response.set_cookie(
                        key=_GUEST_COOKIE,
                        value=f"guest-{uuid.uuid4()}",
                        max_age=_GUEST_COOKIE_MAX_AGE,
                        httponly=True,
                        samesite="lax",
                    )
                return response

        _chainlit_app.add_middleware(_AuthFlowMiddleware)
    except Exception:  # pragma: no cover - non-fatal if Chainlit changes API
        log.warning("Could not install auth-flow middleware", exc_info=True)


@cl.on_chat_start
async def on_chat_start() -> None:
    """Initialize per-session state and greet the user."""
    user = cl.user_session.get("user")
    if user is not None:
        identifier = user.identifier
    else:
        identifier = cl.user_session.get("id") or "anonymous"
    cl.user_session.set("user_id", str(identifier))
    cl.user_session.set("messages", [])
    welcome = WELCOME_BASE
    if identifier.startswith("guest-") and _oauth_configured():
        welcome += _SIGN_IN_HINT_TEMPLATE.format(url=_sign_in_url())
    await cl.Message(content=welcome).send()


def _format_tool_input(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(f"{k} = {v}" for k, v in value.items() if v not in (None, ""))
    return str(value) if value is not None else ""


def _format_tool_output(value: Any, limit: int = 1500) -> str:
    text = getattr(value, "content", None)
    if text is None:
        text = str(value) if value is not None else ""
    return text if len(text) <= limit else text[:limit] + "\n…(truncated)"


@cl.on_message
async def on_message(msg: cl.Message) -> None:
    """Handle one user turn with token streaming and live tool steps.

    The graph is run via ``astream_events`` so we can:
      * Stream the assistant's final reply token-by-token (no long blank wait).
      * Surface each tool call as a collapsible Chainlit Step in real time
        (e.g. "Searching flights…", "Looking up hotels…").
    """
    user_id = cl.user_session.get("user_id") or "anonymous"
    set_user_id(user_id)

    messages: list = cl.user_session.get("messages") or []
    messages.append(HumanMessage(content=msg.content))

    answer = cl.Message(content="")
    await answer.send()

    open_tool_steps: dict[str, cl.Step] = {}
    final_state: dict | None = None

    try:
        async for event in app_graph.astream_events(
            {"messages": messages, "current_agent": ""},
            version="v2",
        ):
            kind = event.get("event")
            name = event.get("name", "")
            run_id = event.get("run_id", "")
            data = event.get("data", {}) or {}

            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                content = getattr(chunk, "content", "") if chunk is not None else ""
                if content:
                    await answer.stream_token(content)

            elif kind == "on_tool_start":
                step = cl.Step(name=name, type="tool")
                step.input = _format_tool_input(data.get("input"))
                await step.send()
                open_tool_steps[run_id] = step

            elif kind == "on_tool_end":
                step = open_tool_steps.pop(run_id, None)
                if step is not None:
                    step.output = _format_tool_output(data.get("output"))
                    await step.update()

            elif kind == "on_chain_end" and name in {"LangGraph", "trip_agent_graph"}:
                output = data.get("output")
                if isinstance(output, dict) and "messages" in output:
                    final_state = output

    except Exception as exc:  # surface failure to the user without crashing the chat
        log.exception("graph streaming failed")
        # Close any dangling tool steps so the UI doesn't show spinners forever.
        for step in open_tool_steps.values():
            step.output = "(interrupted)"
            try:
                await step.update()
            except Exception:  # pragma: no cover
                pass
        answer.content = (
            f"\u26a0\ufe0f Something went wrong: `{exc.__class__.__name__}: {exc}`"
        )
        await answer.update()
        return

    if final_state is not None:
        cl.user_session.set("messages", list(final_state["messages"]))
    else:
        # Fallback: at least keep the user message in history so the next turn isn't lost.
        cl.user_session.set("messages", messages)

    # Degenerate case: the model returned no streamed tokens (rare). Recover
    # the final AI message from state so the user still sees something.
    if not answer.content:
        source = list(final_state["messages"]) if final_state else messages
        last_ai = _last_ai_message(source)
        answer.content = last_ai.content if last_ai else "_(no response)_"

    await answer.update()
