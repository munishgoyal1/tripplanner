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

import asyncio
import logging
import os
import time
import uuid
from typing import Any

import chainlit as cl
import yaml
from chainlit.input_widget import NumberInput, Select, Switch, Tags, TextInput
from langchain_core.messages import AIMessage, HumanMessage

from multiagent.graph import app_graph
from multiagent.observability import (
    app_event,
    audit_enabled_for_user_messages,
    audit_event,
    setup_logging,
)
from multiagent.tools import about_me_extractor  # noqa: F401  (re-exported elsewhere)
from multiagent.tools import preferences_merge
from multiagent.tools import trip_planner
from multiagent.tools import user_preferences as prefs_store
from multiagent.user_context import set_user_id

# Re-export the additive-merge helpers from the shared module so existing
# imports (and tests) that reference them via ``multiagent.web.app`` keep
# working. The single source of truth now lives in ``preferences_merge``.
_union_keep_existing_case = preferences_merge.union_keep_existing_case
_merge_family_member = preferences_merge.merge_family_member
_additive_overlay_extracted = preferences_merge.additive_overlay_extracted
_flatten_keys = preferences_merge.flatten_keys
from multiagent.web.sidebar import build_focus_actions, render_sidebar

setup_logging()
log = logging.getLogger(__name__)

_now = time.monotonic

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
    "- _10 days in Japan in April, history and food, $4k total_\n\n"
    "\U0001f5bc\ufe0f _As you plan, the **side panel** on the right fills with "
    "photos, ratings and reviews for every hotel and attraction in your trip. "
    "Tap a \U0001f3e8 / \U0001f3af button under any of my replies to zoom in on "
    "one item, or **Whole trip** to zoom back out._\n\n"
    "\u2699\ufe0f _Tap the **gear icon** next to the message box to edit your "
    "travel preferences. The **About me** field at the top accepts free text "
    "(\"I'm Munish, 43, in Bengaluru, travel with wife Megha 40 and son Amay 11, "
    "love hills and beaches, vegetarian\") and I'll auto-extract the structured "
    "fields below. For the full data dump, type **`/profile`**; "
    "**`/help`** lists all commands._"
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
# Slash commands — let the user inspect and edit everything we remember
# about them, without going through the LLM. Keeps preferences transparent.
# ---------------------------------------------------------------------------
_PROFILE_HELP = (
    "**Profile commands**\n"
    "- `/profile` \u2014 show everything I've saved about you (as editable YAML)\n"
    "- `/profile save` *(followed by an edited YAML block)* \u2014 overwrite saved prefs\n"
    "- `/profile reset` \u2014 wipe all saved prefs and start fresh\n"
    "- `/whoami` \u2014 show your identity (sign-in name and id)\n"
    "- `/help` \u2014 show this list\n\n"
    "Anything else is a normal trip-planning request \u2014 just tell me where "
    "you want to go."
)

# Keys we hide from the editable YAML because they're either internal
# bookkeeping or auto-managed (timestamps, system-set lists).
_PROFILE_HIDDEN_KEYS = {"learned_notes"}


def _format_prefs_yaml(prefs: dict[str, Any]) -> str:
    visible = {k: v for k, v in prefs.items() if k not in _PROFILE_HIDDEN_KEYS}
    return yaml.safe_dump(
        visible,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def _strip_yaml_fence(text: str) -> str:
    """Allow users to paste the YAML either raw or inside `````yaml ... ````` fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped


async def _send_profile_view() -> None:
    prefs = prefs_store.load_preferences()
    yaml_text = _format_prefs_yaml(prefs)
    body = (
        "\U0001f4cb **Your saved preferences** (everything I remember about you):\n\n"
        f"```yaml\n{yaml_text}```\n"
        "To **edit**, copy the block above, change anything you like, then send "
        "it back to me as:\n\n"
        "```\n/profile save\n<paste the edited YAML here>\n```\n"
        "_Tip: you can wrap the YAML in_ ```yaml ... ``` _fences or paste it raw \u2014 "
        "both work._"
    )
    await cl.Message(content=body).send()


async def _handle_profile_save(payload: str) -> None:
    yaml_text = _strip_yaml_fence(payload)
    if not yaml_text.strip():
        await cl.Message(
            content=(
                "\u26a0\ufe0f I didn't see any YAML after `/profile save`. Send "
                "`/profile` first to see the current values, then paste the edited "
                "block on a new line after `/profile save`."
            )
        ).send()
        return
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        await cl.Message(
            content=(
                "\u274c Couldn't parse that as YAML:\n\n"
                f"```\n{exc}\n```\n"
                "Send `/profile` again to get a fresh copy and try once more."
            )
        ).send()
        return
    if not isinstance(parsed, dict):
        await cl.Message(
            content=(
                "\u274c The YAML must be a mapping at the top level (key: value pairs). "
                "Send `/profile` to see the expected shape."
            )
        ).send()
        return
    # Preserve hidden fields (learned_notes) - only overwrite what the user sees.
    current = prefs_store.load_preferences()
    merged = {**current, **parsed}
    for key in _PROFILE_HIDDEN_KEYS:
        merged[key] = current.get(key, [])
    prefs_store.save_preferences(merged)
    await cl.Message(
        content="\u2705 Saved. Send `/profile` again to see the new values."
    ).send()


async def _handle_profile_reset() -> None:
    import copy

    defaults = copy.deepcopy(prefs_store._DEFAULT_PREFS)  # noqa: SLF001
    prefs_store.save_preferences(defaults)
    await cl.Message(
        content=(
            "\u267b\ufe0f All saved preferences wiped. I won't remember anything "
            "about you until you tell me again (or sign in)."
        )
    ).send()


async def _handle_whoami() -> None:
    user = cl.user_session.get("user")
    if user is None:
        await cl.Message(content="You're not signed in (anonymous session).").send()
        return
    md = user.metadata or {}
    lines = [
        f"**Display name:** {user.display_name or '_(none)_'}",
        f"**Identifier:** `{user.identifier}`",
    ]
    if md.get("provider"):
        lines.append(f"**Signed in via:** {md['provider']}")
    if md.get("email"):
        lines.append(f"**Email:** {md['email']}")
    if md.get("role"):
        lines.append(f"**Role:** {md['role']}")
    await cl.Message(content="\n".join(lines)).send()


async def _maybe_handle_slash_command(text: str) -> bool:
    """Return True if ``text`` is a slash command we handled."""
    stripped = text.lstrip()
    if not stripped.startswith("/"):
        return False
    first_line, _, rest = stripped.partition("\n")
    cmd = first_line.strip().lower()
    if cmd in ("/help", "/?"):
        await cl.Message(content=_PROFILE_HELP).send()
        return True
    if cmd == "/whoami":
        await _handle_whoami()
        return True
    if cmd == "/profile":
        await _send_profile_view()
        return True
    if cmd == "/profile reset":
        await _handle_profile_reset()
        return True
    if cmd == "/profile save":
        await _handle_profile_save(rest)
        return True
    await cl.Message(
        content=f"Unknown command `{cmd}`. Send `/help` for the list."
    ).send()
    return True


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
        name = (
            raw_user_data.get("name")
            or raw_user_data.get("given_name")
            or raw_user_data.get("login")
        )
        email = raw_user_data.get("email")
        picture = raw_user_data.get("picture") or raw_user_data.get("avatar_url")
        metadata = {
            "provider": provider_id,
            "email": email,
            "name": name,
            "picture": picture,
            "role": "user",
        }
        # Seed the profile so the agent (and `/profile`) see the real name
        # immediately, without waiting for the user to introduce themselves.
        if name:
            try:
                set_user_id(identifier)
                prefs_store.update_profile({
                    "display_name": name.split()[0] if name else None,
                })
            except Exception:  # pragma: no cover - non-fatal
                log.warning("Could not seed profile from OAuth payload", exc_info=True)
        return cl.User(
            identifier=identifier,
            display_name=name or identifier,
            metadata=metadata,
        )

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
        from chainlit.oauth_providers import get_configured_oauth_providers
        from chainlit.server import app as _chainlit_app
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import RedirectResponse

        def _signin_target() -> str:
            """Where /sign-in should send the browser.

            If exactly one OAuth provider is configured we redirect straight
            to its authorize endpoint so the user gets to Google in one
            click (Google's default behaviour does SSO automatically when
            the browser already has an active Google session). With multiple
            providers we fall back to Chainlit's /login page so the user
            can pick.
            """
            try:
                providers = list(get_configured_oauth_providers() or [])
            except Exception:
                providers = []
            if len(providers) == 1:
                return f"/auth/oauth/{providers[0]}"
            return "/login"

        class _AuthFlowMiddleware(BaseHTTPMiddleware):
            """Handle ``/sign-in`` upgrades and persistent guest cookies.

            Chainlit registers a catch-all route for the React SPA, so a
            normal ``add_route`` call for ``/sign-in`` is shadowed. Doing the
            work in middleware guarantees we run before route matching.
            """

            async def dispatch(self, request, call_next):
                if request.url.path == "/sign-in" and request.method == "GET":
                    target = _signin_target()
                    response = RedirectResponse(url=target, status_code=303)
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


# ---------------------------------------------------------------------------
# Chat settings panel - the "gear icon" form. Covers the 80% of preferences
# most users want to set; power users can still use /profile for the full
# YAML view + edit. Mapping is bidirectional: load_preferences() -> widgets,
# widget values -> save_preferences().
# ---------------------------------------------------------------------------
_TRIP_STYLES = ["balanced", "relaxed", "adventurous", "cultural", "foodie", "luxury", "budget"]
_BUDGET_LEVELS = ["budget", "moderate", "comfortable", "luxury"]
_FLIGHT_CLASSES = ["economy", "premium_economy", "business", "first"]


def _select_index(values: list[str], current: str | None) -> int:
    try:
        return values.index(current) if current else 0
    except ValueError:
        return 0


def _build_chat_settings() -> cl.ChatSettings:
    """Build the settings form pre-populated from the user's saved prefs."""
    prefs = prefs_store.load_preferences()
    profile = prefs.get("profile") or {}
    hotel = prefs.get("hotel_preferences") or {}
    transport = prefs.get("transport_preferences") or {}
    food = prefs.get("food_preferences") or {}
    return cl.ChatSettings(
        [
            TextInput(
                id="about_me",
                label="About me (free text)",
                initial=str(prefs.get("about_me") or ""),
                placeholder=(
                    "Tell me anything about you and your travel preferences in your own "
                    "words. e.g. 'I'm Munish, 43, live in Bengaluru, travel with my "
                    "wife Megha (40) and son Amay (11). We love hill stations and "
                    "beaches, prefer 4-star hotels, vegetarian, no early-morning "
                    "flights.' When you save, I'll extract structured fields from "
                    "this and add anything new to the matching fields below — "
                    "existing values are kept, nothing is ever removed."
                ),
                description=(
                    "Saving this adds any new details (home city, family, "
                    "interests, dietary, etc.) to your profile. Existing values "
                    "are never overwritten — clear individual fields manually "
                    "if you want to change them."
                ),
                multiline=True,
            ),
            TextInput(
                id="display_name",
                label="Your name",
                initial=profile.get("display_name") or "",
                placeholder="What should I call you?",
            ),
            TextInput(
                id="home_city",
                label="Home city",
                initial=profile.get("home_city") or "",
                placeholder="e.g. Bangalore",
            ),
            TextInput(
                id="home_country",
                label="Home country",
                initial=profile.get("home_country") or "",
                placeholder="e.g. India",
            ),
            Select(
                id="trip_style",
                label="Default trip style",
                values=_TRIP_STYLES,
                initial_index=_select_index(_TRIP_STYLES, prefs.get("trip_style")),
            ),
            Select(
                id="budget_level",
                label="Default budget level",
                values=_BUDGET_LEVELS,
                initial_index=_select_index(_BUDGET_LEVELS, prefs.get("budget_level")),
            ),
            Select(
                id="flight_class",
                label="Flight class",
                values=_FLIGHT_CLASSES,
                initial_index=_select_index(_FLIGHT_CLASSES, transport.get("flight_class")),
            ),
            Switch(
                id="prefer_direct_flights",
                label="Prefer direct flights",
                initial=bool(transport.get("prefer_direct_flights", True)),
            ),
            NumberInput(
                id="hotel_star_rating_min",
                label="Minimum hotel star rating",
                initial=int(hotel.get("star_rating_min") or 3),
                placeholder="1-5",
            ),
            Tags(
                id="dietary",
                label="Dietary restrictions",
                initial=list(food.get("dietary") or []),
                description="e.g. vegetarian, halal, gluten-free",
            ),
            Tags(
                id="cuisine_likes",
                label="Cuisines you love",
                initial=list(food.get("cuisine_likes") or []),
            ),
            Tags(
                id="cuisine_dislikes",
                label="Cuisines you avoid",
                initial=list(food.get("cuisine_dislikes") or []),
            ),
            Tags(
                id="interests",
                label="Interests",
                initial=list(prefs.get("interests") or []),
                description="e.g. hiking, museums, photography, nightlife",
            ),
            Tags(
                id="dislikes",
                label="Things to avoid",
                initial=list(prefs.get("dislikes") or []),
                description="e.g. crowded places, late nights, seafood",
            ),
        ]
    )


def _apply_settings(values: dict[str, Any]) -> dict[str, Any]:
    """Merge widget values back into the structured preferences dict.

    Returns a small status dict the caller can use to confirm what happened::

        {"about_me_extracted": ["profile.home_city", "interests", ...]}

    When the user changes the free-text ``about_me`` field, an LLM extraction
    pass converts it into structured fields and those are layered on top of
    the widget values **additively** — list fields get unioned, blank scalar
    fields get filled in, and family members get appended/extended. We never
    remove or overwrite an existing value via this path (per the user's
    intent: "always additive, don't remove existing data").
    """
    prefs = prefs_store.load_preferences()
    profile = dict(prefs.get("profile") or {})
    hotel = dict(prefs.get("hotel_preferences") or {})
    transport = dict(prefs.get("transport_preferences") or {})
    food = dict(prefs.get("food_preferences") or {})

    def _clean_str(v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def _clean_list(v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v if str(x).strip()]

    profile["display_name"] = _clean_str(values.get("display_name"))
    profile["home_city"] = _clean_str(values.get("home_city"))
    profile["home_country"] = _clean_str(values.get("home_country"))
    if values.get("trip_style"):
        prefs["trip_style"] = values["trip_style"]
    if values.get("budget_level"):
        prefs["budget_level"] = values["budget_level"]
    if values.get("flight_class"):
        transport["flight_class"] = values["flight_class"]
    transport["prefer_direct_flights"] = bool(values.get("prefer_direct_flights", True))
    try:
        star = int(values.get("hotel_star_rating_min") or 3)
        hotel["star_rating_min"] = max(1, min(5, star))
    except (TypeError, ValueError):
        pass
    food["dietary"] = _clean_list(values.get("dietary"))
    food["cuisine_likes"] = _clean_list(values.get("cuisine_likes"))
    food["cuisine_dislikes"] = _clean_list(values.get("cuisine_dislikes"))
    prefs["interests"] = _clean_list(values.get("interests"))
    prefs["dislikes"] = _clean_list(values.get("dislikes"))

    prefs["profile"] = profile
    prefs["hotel_preferences"] = hotel
    prefs["transport_preferences"] = transport
    prefs["food_preferences"] = food

    # --- About me: save raw, then extract & overlay structured fields ------
    # Single-sourced in preferences_merge so the SPA backend shares it.
    new_about = str(values.get("about_me") or "")
    prefs, extracted_keys = preferences_merge.apply_about_me(prefs, new_about)

    prefs_store.save_preferences(prefs)
    return {"about_me_extracted": extracted_keys}


@cl.on_settings_update
async def on_settings_update(settings: dict) -> None:
    """Persist the gear-icon form values into the user's preferences."""
    user_id = cl.user_session.get("user_id") or "anonymous"
    set_user_id(user_id)
    # Run synchronously in a worker thread — _apply_settings may call the LLM
    # for the "About me" extraction pass, which is a blocking HTTPS call.
    try:
        status = await asyncio.to_thread(_apply_settings, settings)
    except Exception:
        log.exception("on_settings_update: _apply_settings failed")
        await cl.Message(
            content=(
                "\u26a0\ufe0f Couldn't save your settings just now. Your previous "
                "values are still in place. Please try again."
            )
        ).send()
        return

    extracted = status.get("about_me_extracted") or []
    if extracted:
        bullets = "\n".join(f"- `{k}`" for k in extracted)
        msg = (
            "\u2705 Preferences saved. I picked up these fields from your "
            "**About me** text and added them (existing values were kept):\n\n"
            f"{bullets}\n\n"
            "Type `/profile` to see the full saved state."
        )
    else:
        msg = (
            "\u2705 Preferences saved. I'll use these on your next trip request. "
            "Type `/profile` to see the full saved state."
        )
    await cl.Message(content=msg).send()


async def _refresh_sidebar() -> None:
    """Reload the active trip and re-render every panel in the right rail.

    Safe to call any time — silently no-ops outside a Chainlit context or
    when there's nothing to show. Uses the current ``sidebar_focus`` from
    the session (set by :func:`_on_focus_item`).
    """
    user_id = cl.user_session.get("user_id") or "anonymous"
    set_user_id(user_id)
    try:
        trip = trip_planner.load_active_trip_dict()
    except Exception:  # pragma: no cover -- never block the chat on this
        log.exception("sidebar refresh: failed to load active trip")
        trip = None
    focus = cl.user_session.get("sidebar_focus")
    await render_sidebar(trip, focus, user_id)


@cl.action_callback("focus_item")
async def _on_focus_item(action: cl.Action) -> None:
    """Zoom the sidebar onto a single hotel/attraction (or reset to overview)."""
    payload = action.payload or {}
    if payload.get("kind") == "overview":
        cl.user_session.set("sidebar_focus", None)
    else:
        cl.user_session.set(
            "sidebar_focus",
            {"kind": payload.get("kind", "place"), "name": payload.get("name", "")},
        )
    await _refresh_sidebar()


@cl.action_callback("select_item")
async def _on_select_item(action: cl.Action) -> None:
    """Add a hotel/attraction (from the panel's *Add to trip*) to the trip."""
    payload = action.payload or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return
    kind = payload.get("kind", "attraction")
    user_id = cl.user_session.get("user_id") or "anonymous"
    set_user_id(user_id)
    try:
        ok = trip_planner.add_selection(kind, {"name": name})
    except Exception:  # pragma: no cover -- never block the chat on this
        log.exception("select_item: failed to add %s", name)
        ok = False
    if ok:
        cl.user_session.set("sidebar_focus", None)
    await _refresh_sidebar()



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
    # Make sure prefs_store reads/writes the right user before building the form.
    set_user_id(str(identifier))
    app_event(
        "session_start",
        user_id=str(identifier),
        is_guest=str(identifier).startswith("guest-"),
        has_oauth=_oauth_configured(),
    )
    await _build_chat_settings().send()
    welcome = WELCOME_BASE
    if identifier.startswith("guest-") and _oauth_configured():
        welcome += _SIGN_IN_HINT_TEMPLATE.format(url=_sign_in_url())
    await cl.Message(content=welcome).send()
    # Open the side panel right away so returning users see their trip and
    # first-time users see the "no trip yet" prompt.
    await _refresh_sidebar()


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

    # Slash commands bypass the LLM entirely - keeps profile UX snappy and
    # avoids burning tokens on simple "show me what you remember" requests.
    if await _maybe_handle_slash_command(msg.content):
        app_event("slash_command", user_id=user_id, length=len(msg.content))
        return

    # APP LOG: only counts -- no content. Safe to keep in stdout / Log Analytics.
    app_event(
        "user_message",
        user_id=user_id,
        length=len(msg.content),
        words=len(msg.content.split()),
    )
    # AUDIT LOG: raw content goes to the restricted sink only when explicitly
    # enabled via AUDIT_USER_MESSAGES=1. Never on stdout, regardless.
    if audit_enabled_for_user_messages():
        audit_event("user_message", user_id=user_id, content=msg.content)

    messages: list = cl.user_session.get("messages") or []
    messages.append(HumanMessage(content=msg.content))

    answer = cl.Message(content="")
    await answer.send()

    open_tool_steps: dict[str, cl.Step] = {}
    tool_starts: dict[str, float] = {}
    tool_call_count = 0
    final_state: dict | None = None
    turn_start = _now()

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
                tool_starts[run_id] = _now()
                tool_call_count += 1

            elif kind == "on_tool_end":
                step = open_tool_steps.pop(run_id, None)
                if step is not None:
                    step.output = _format_tool_output(data.get("output"))
                    await step.update()
                started = tool_starts.pop(run_id, None)
                app_event(
                    "tool_call",
                    user_id=user_id,
                    tool=name,
                    status="ok",
                    ms=int((_now() - started) * 1000) if started else None,
                )

            elif kind == "on_chain_end" and name in {"LangGraph", "trip_agent_graph"}:
                output = data.get("output")
                if isinstance(output, dict) and "messages" in output:
                    final_state = output

    except Exception as exc:  # surface failure to the user without crashing the chat
        log.exception("graph streaming failed")
        app_event(
            "turn_error",
            user_id=user_id,
            error_kind=exc.__class__.__name__,
            tool_calls=tool_call_count,
            ms=int((_now() - turn_start) * 1000),
        )
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
    app_event(
        "turn_complete",
        user_id=user_id,
        tool_calls=tool_call_count,
        reply_length=len(answer.content or ""),
        ms=int((_now() - turn_start) * 1000),
    )

    # Refresh the right-rail side panel and attach per-item focus buttons
    # to the agent's reply. Anything that fails here is logged but never
    # bubbles up — sidebar is supplementary, the chat reply is the contract.
    try:
        trip = trip_planner.load_active_trip_dict()
    except Exception:  # pragma: no cover
        log.exception("sidebar: failed to load active trip after turn")
        trip = None
    focus_actions = build_focus_actions(trip)
    if focus_actions:
        answer.actions = focus_actions
        try:
            await answer.update()
        except Exception:  # pragma: no cover
            log.exception("sidebar: failed to attach focus actions")
    focus = cl.user_session.get("sidebar_focus")
    try:
        await render_sidebar(trip, focus, user_id)
    except Exception:  # pragma: no cover
        log.exception("sidebar: render failed")
