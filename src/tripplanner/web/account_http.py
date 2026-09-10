"""Account, preferences, documents, privacy, and auth HTTP routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from tripplanner.api_contracts import (
    DocumentDeleteRequest,
    DocumentExtractRequest,
    DocumentSaveRequest,
    FamilyMemberRequest,
    GuestMigrateRequest,
    PreferencesRequest,
    PrivacyActionRequest,
    ProfileSuggestionRequest,
    RemoveFamilyMemberRequest,
    SelectRequest,
    UserRequest,
)
from tripplanner.observability import app_event
from tripplanner.request_identity import (
    is_anonymous_id,
    is_hosted,
    require_guest_capability,
    require_signed_user,
    resolve_user_id,
)
from tripplanner.request_limits import acquire_workspace_exclusive, release_workspace_exclusive
from tripplanner.user_context import set_user_id
from tripplanner.web import oauth
from tripplanner.web.http_context import document_user as _document_user
from tripplanner.web.http_context import mobile_auth_redirect as _mobile_auth_redirect
from tripplanner.web.http_context import secure_cookie as _secure_cookie
from tripplanner.web.http_context import set_request_user as _set_request_user

router = APIRouter()

@router.get("/profile/suggestions")
async def get_profile_suggestions(request: Request, user_id: str = "local") -> dict:
    """Facts chat noticed that are waiting for the user to confirm or decline."""
    from tripplanner.tools import profile_suggestions

    _set_request_user(request, user_id)
    return {"suggestions": profile_suggestions.list_pending()}


@router.post("/profile/suggestions/{suggestion_id}")
async def resolve_profile_suggestion(
    suggestion_id: str, req: ProfileSuggestionRequest, request: Request
) -> dict:
    """Confirm a noticed fact into the durable profile, or decline it for good."""
    from tripplanner.tools import profile_suggestions

    _set_request_user(request, req.user_id)
    resolved = profile_suggestions.resolve(suggestion_id, req.action)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"resolved": resolved, "suggestions": profile_suggestions.list_pending()}


@router.get("/preferences")
async def get_preferences(request: Request, user_id: str = "local") -> dict:
    """Return the editable subset of the user's saved preferences (for the
    SPA settings panel)."""
    from tripplanner.tools import user_preferences as prefs_store

    _set_request_user(request, user_id)
    prefs = prefs_store.load_preferences()
    profile = prefs.get("profile") or {}
    transport = prefs.get("transport_preferences") or {}
    hotel = prefs.get("hotel_preferences") or {}
    food = prefs.get("food_preferences") or {}
    return {
        "display_name": profile.get("display_name") or "",
        "home_city": profile.get("home_city") or "",
        "home_country": profile.get("home_country") or "",
        "display_region": profile.get("display_region") or profile.get("home_country") or "",
        "display_language": profile.get("display_language") or "en",
        "display_currency": prefs.get("display_currency") or "USD",
        "display_currency_configured": "display_currency" in set(prefs.get("_explicit_fields") or []),
        "trip_style": prefs.get("trip_style") or "",
        "budget_level": prefs.get("budget_level") or "",
        "flight_class": transport.get("flight_class") or "",
        "prefer_direct_flights": bool(transport.get("prefer_direct_flights", True)),
        "hotel_star_rating_min": int(hotel.get("star_rating_min") or 3),
        "dietary": list(food.get("dietary") or []),
        "interests": list(prefs.get("interests") or []),
        "dislikes": list(prefs.get("dislikes") or []),
        "about_me": prefs.get("about_me") or "",
        "profile_summary": prefs.get("profile_summary") or "",
        "profile_summary_updated_at": prefs.get("profile_summary_updated_at"),
        "planning_mode": prefs.get("planning_mode") or "direct",
        # Read-only: collected passively from chat, shown but not edited here.
        "family_members": [m for m in (prefs.get("family_members") or []) if isinstance(m, dict)],
    }


@router.post("/preferences")
async def save_preferences_endpoint(req: PreferencesRequest, request: Request) -> dict:
    """Merge the provided preference fields and persist them (additive — only    keys present in the request are written)."""
    from tripplanner.tools import preferences_merge
    from tripplanner.tools import profile_summary as profile_summary_mod
    from tripplanner.tools import user_preferences as prefs_store

    _set_request_user(request, req.user_id)
    current = prefs_store.load_preferences()
    about_text: str | None = None
    about_extracted: dict = {}
    about_learned: list[dict] = []
    extracted_keys: list[str] = []
    summary_conflict = False
    summary_has_compare_token = "profile_summary_updated_at" in req.model_fields_set
    explicit_paths = {
        "display_name": "profile.display_name",
        "home_city": "profile.home_city",
        "home_country": "profile.home_country",
        "display_region": "profile.display_region",
        "display_language": "profile.display_language",
        "display_currency": "display_currency",
        "trip_style": "trip_style",
        "budget_level": "budget_level",
        "flight_class": "transport_preferences.flight_class",
        "prefer_direct_flights": "transport_preferences.prefer_direct_flights",
        "hotel_star_rating_min": "hotel_preferences.star_rating_min",
        "dietary": "food_preferences.dietary",
        "interests": "interests",
        "dislikes": "dislikes",
        "planning_mode": "planning_mode",
        "about_me": "about_me",
        "profile_summary": "profile_summary",
    }
    submitted_paths = {
        path
        for field, path in explicit_paths.items()
        if field in req.model_fields_set
    }
    if req.about_me is not None:
        about_text = req.about_me.strip()[: preferences_merge.ABOUT_ME_MAX_CHARS]
        old_about = str(current.get("about_me") or "").strip()
        if about_text and about_text != old_about:
            extracted = preferences_merge.about_me_extractor.extract_about_me(about_text)
            about_learned = list(extracted.pop("_learned_notes_to_append", None) or [])
            about_extracted = extracted
            extracted_keys = preferences_merge.flatten_keys(extracted)
            if about_learned:
                extracted_keys.append("learned_notes")

    def apply(prefs: dict) -> dict | None:
        nonlocal summary_conflict
        summary_conflict = False
        if (
            req.profile_summary is not None
            and summary_has_compare_token
            and prefs.get("profile_summary_updated_at") != req.profile_summary_updated_at
        ):
            summary_conflict = True
            return None

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
        if req.display_region is not None:
            profile["display_region"] = req.display_region.strip() or None
        if req.display_language is not None:
            profile["display_language"] = req.display_language
        if req.display_currency is not None:
            prefs["display_currency"] = req.display_currency
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
            food["dietary"] = [value.strip() for value in req.dietary if value.strip()]
        if req.interests is not None:
            prefs["interests"] = [value.strip() for value in req.interests if value.strip()]
        if req.dislikes is not None:
            prefs["dislikes"] = [value.strip() for value in req.dislikes if value.strip()]
        if req.planning_mode is not None:
            prefs["planning_mode"] = req.planning_mode

        prefs["profile"] = profile
        prefs["transport_preferences"] = transport
        prefs["hotel_preferences"] = hotel
        prefs["food_preferences"] = food

        if about_text is not None:
            prefs["about_me"] = about_text
            prefs = preferences_merge.additive_overlay_extracted(prefs, about_extracted)
            if about_learned:
                notes = list(prefs.get("learned_notes") or [])
                seen = {
                    (entry.get("note") or "").strip().lower()
                    for entry in notes
                    if isinstance(entry, dict)
                }
                for entry in about_learned:
                    note = str(entry.get("note") or "").strip()
                    if note and note.lower() not in seen:
                        seen.add(note.lower())
                        notes.append(entry)
                prefs["learned_notes"] = notes
        if req.profile_summary is not None:
            profile_summary_mod.apply_summary(prefs, req.profile_summary)
        prefs_store.mark_explicit_fields(prefs, submitted_paths)
        return prefs

    updated = prefs_store.mutate_preferences(apply)
    if summary_conflict:
        return JSONResponse(
            {
                "error": "profile summary changed while settings were open",
                "profile_summary": updated.get("profile_summary") or "",
                "profile_summary_updated_at": updated.get("profile_summary_updated_at"),
            },
            status_code=409,
        )

    app_event("api_preferences_saved")
    return {"ok": True, "about_me_extracted": extracted_keys}


@router.post("/profile/summary/regenerate")
async def regenerate_profile_summary(req: SelectRequest, request: Request) -> dict:
    """Force a fresh LLM-authored profile summary for the user.

    Re-uses ``SelectRequest`` only for ``user_id`` (``kind``/``name`` ignored).
    Returns the new ``profile_summary`` (may be empty if there's nothing durable
    to summarize or the model is unavailable).
    """
    from tripplanner.tools import profile_summary as profile_summary_mod

    _set_request_user(request, req.user_id)
    profile_summary_mod.update_summary(force=True)
    prefs = profile_summary_mod.user_preferences.load_preferences()
    app_event("api_profile_summary_regenerated")
    return {
        "ok": True,
        "profile_summary": prefs.get("profile_summary") or "",
        "profile_summary_updated_at": prefs.get("profile_summary_updated_at"),
    }


@router.post("/profile/family")
async def save_family_member(req: FamilyMemberRequest, request: Request) -> dict:
    """Add or fully replace one traveller's editable profile."""
    from tripplanner.tools import user_preferences as prefs_store

    _set_request_user(request, req.user_id)
    updated = await asyncio.to_thread(
        prefs_store.set_family_member,
        original_relationship=req.original_relationship,
        original_name=req.original_name,
        relationship=req.relationship,
        name=req.name,
        age=req.age,
        dietary=req.dietary,
        mobility=req.mobility,
        interests=req.interests,
        notes=req.notes,
    )
    app_event("api_family_member_saved")
    return {"ok": True, "family_members": updated.get("family_members") or []}


@router.post("/profile/family/remove")
async def remove_family_member(req: RemoveFamilyMemberRequest, request: Request) -> dict:
    """Remove one traveller from the durable profile."""
    from tripplanner.tools import user_preferences as prefs_store

    _set_request_user(request, req.user_id)
    updated = await asyncio.to_thread(prefs_store.remove_family_member, req.relationship, req.name)
    app_event("api_family_member_removed")
    return {"ok": True, "family_members": updated.get("family_members") or []}

@router.get("/documents")
async def documents_list(request: Request, user_id: str = "local") -> dict:
    """Every stored traveller document detail for this account.

    Returns the extracted fields only — there is no original file to return,
    because none was kept.
    """
    from tripplanner.web import travel_documents

    _document_user(request, user_id)
    documents = await asyncio.to_thread(travel_documents.list_documents, "traveler")
    return {"documents": documents, "type_labels": travel_documents.TYPE_LABELS}


@router.post("/documents/extract")
async def documents_extract(req: DocumentExtractRequest, request: Request) -> dict:
    """Read one document and propose its fields for confirmation.

    Nothing is written here. The response is a proposal the person must accept
    before ``POST /documents`` stores anything.
    """
    from tripplanner.web import document_extract

    _document_user(request, req.user_id)
    try:
        result = await asyncio.to_thread(
            document_extract.extract,
            req.type,
            content_base64=req.content_base64,
            text=req.text,
        )
    except document_extract.ExtractionError as exc:
        app_event("api_document_extract", document_type=req.type, outcome="rejected")
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=422)

    app_event(
        "api_document_extract",
        document_type=req.type,
        source_kind=result["source_kind"],
        field_count=len(result["fields"]),
        outcome="proposed",
    )
    return {"ok": True, **result}


@router.post("/documents")
async def documents_save(req: DocumentSaveRequest, request: Request) -> dict:
    """Store the fields a person confirmed for one document."""
    from tripplanner.web import travel_documents

    user_id = _document_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        stored = await asyncio.to_thread(
            travel_documents.save_document,
            {
                "id": req.id,
                "type": req.type,
                "scope": req.scope,
                "traveller_key": req.traveller_key,
                "traveller_name": req.traveller_name,
                "trip_id": req.trip_id,
                "fields": req.fields,
                "provenance": req.provenance,
            },
        )
    except travel_documents.DocumentError as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=422)
    finally:
        await release_workspace_exclusive(workspace)

    app_event("api_document_saved", document_type=stored["type"], scope=stored["scope"])
    return {"ok": True, "document": stored}


@router.post("/documents/delete")
async def documents_delete(req: DocumentDeleteRequest, request: Request) -> dict:
    """Delete one stored document detail."""
    from tripplanner.web import travel_documents

    user_id = _document_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        deleted = await asyncio.to_thread(travel_documents.delete_document, req.id)
    finally:
        await release_workspace_exclusive(workspace)

    app_event("api_document_deleted", deleted=deleted)
    return {"ok": deleted}


@router.post("/documents/clear")
async def documents_clear(req: UserRequest, request: Request) -> dict:
    """Delete every stored document detail for this account."""
    from tripplanner.web import travel_documents

    user_id = _document_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        deleted = await asyncio.to_thread(travel_documents.clear_all_documents)
    finally:
        await release_workspace_exclusive(workspace)

    app_event("api_documents_cleared", deleted=deleted)
    return {"ok": True, "deleted": deleted}


@router.get("/trip/documents/readiness")
async def trip_documents_readiness(request: Request, user_id: str = "local") -> dict:
    """Whether the active trip's paperwork is ready.

    Every check is arithmetic over stored fields and trip dates. This endpoint
    answers one question and does not become a third place documents live. It
    resolves the trip's origin and destination to countries first, because the
    passport, visa, and IDP checks stay silent unless the trip is known to
    cross a border.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.web import document_readiness, place_country, travel_documents

    _document_user(request, user_id)

    def _evaluate() -> dict:
        trip = trip_planner.load_active_trip_dict()
        if not trip:
            return {
                "checks": [],
                "blockers": 0,
                "warnings": 0,
                "badge": "",
                "badge_tone": "",
                "reason": "no_trip",
            }
        prefs = prefs_store.load_preferences()
        profile = prefs.get("profile") if isinstance(prefs.get("profile"), dict) else {}
        # A city name the geocoder cannot place is not a border; the home
        # country the user declared is better evidence than a guess.
        origin_country = place_country.resolve_country(trip.get("origin")) or (
            place_country.resolve_country(profile.get("home_country"))
        )
        return document_readiness.evaluate(
            trip,
            travel_documents.list_documents("traveler"),
            prefs,
            origin_country=origin_country,
            destination_country=place_country.resolve_country(trip.get("destination")),
        )

    return await asyncio.to_thread(_evaluate)


@router.post("/account/privacy")
async def account_privacy_action(req: PrivacyActionRequest, request: Request) -> dict:
    """Run user-requested privacy actions (GDPR-style controls).

    Supported actions:
    - ``delete_trip_history``: remove all saved/active trips and chat history.
    - ``clear_all_data``: delete trips/chats + reset preferences + clear usage/cache.
    - ``delete_account``: same as clear-all; identity provider account remains external.
    """
    import tripplanner.tools_cache as tools_cache
    from tripplanner.tools import trip_planner
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.usage import clear_usage
    from tripplanner.web import chat_store, travel_documents

    user_id = _set_request_user(request, req.user_id)

    if req.action in {"clear_all_data", "delete_account"}:
        if req.confirm_text.strip().upper() != "DELETE":
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Type DELETE to confirm this action.",
            }

    workspace = await acquire_workspace_exclusive(user_id)
    try:
        deleted_trips = await asyncio.to_thread(trip_planner.clear_all_trip_history)
        deleted_chats = await asyncio.to_thread(chat_store.clear_all)

        deleted_usage = 0
        deleted_cache = 0
        deleted_documents = 0
        reset_prefs = False

        if req.action in {"clear_all_data", "delete_account"}:
            deleted_documents = await asyncio.to_thread(travel_documents.clear_all_documents)
            await asyncio.to_thread(prefs_store.reset_preferences)
            reset_prefs = True
            deleted_usage = await asyncio.to_thread(clear_usage, user_id)
            deleted_cache = await asyncio.to_thread(tools_cache.clear_cache_for_user, user_id)
            from tripplanner.flight_recorder import clear_user

            await asyncio.to_thread(clear_user, user_id)
    finally:
        await release_workspace_exclusive(workspace)

    app_event(
        "api_privacy_action",
        action=req.action,
        deleted_trips=deleted_trips,
        deleted_chats=deleted_chats,
        deleted_usage=deleted_usage,
        deleted_cache=deleted_cache,
        deleted_documents=deleted_documents,
    )

    return {
        "ok": True,
        "action": req.action,
        "deleted_trips": deleted_trips,
        "deleted_chats": deleted_chats,
        "deleted_usage": deleted_usage,
        "deleted_cache": deleted_cache,
        "deleted_documents": deleted_documents,
        "preferences_reset": reset_prefs,
        "message": (
            "Trip history deleted."
            if req.action == "delete_trip_history"
            else "All app data cleared for this account."
        ),
    }


@router.post("/account/migrate-guest")
async def account_migrate_guest(req: GuestMigrateRequest, request: Request) -> dict:
    """Copy trips and preferences from a guest (web-*) identity into an
    authenticated account.

    Called once after Google OAuth sign-in when the browser had existing guest
    data. Safe to call multiple times — already-migrated trips are skipped.
    Returns {ok, copied_trips, skipped_trips, copied_prefs}.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.web import chat_store

    guest_id = (req.guest_id or "").strip()
    auth_id = require_signed_user(request) if is_hosted() else resolve_user_id(request, req.user_id)
    if not is_anonymous_id(guest_id) or not auth_id:
        return {"ok": False, "error": "invalid_ids"}
    if is_hosted():
        require_guest_capability(request, guest_id)

    workspace = await acquire_workspace_exclusive(guest_id, auth_id)
    try:
        set_user_id(guest_id)
        guest_trips = await asyncio.to_thread(trip_planner.list_saved_trips)
        guest_active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
        guest_trip_ids = [str(item["trip_id"]) for item in guest_trips if item.get("trip_id")]
        guest_active_id = str((guest_active or {}).get("trip_id") or "")
        if guest_active_id:
            guest_trip_ids.append(guest_active_id)
        guest_chat_state = await asyncio.to_thread(chat_store.export_state, guest_trip_ids)

        set_user_id(auth_id)
        auth_trips = await asyncio.to_thread(trip_planner.list_saved_trips)
        auth_trip_ids = {t["trip_id"] for t in auth_trips}

        copied_trips = 0
        skipped_trips = 0
        for summary in guest_trips:
            tid = summary.get("trip_id")
            if not tid or tid in auth_trip_ids:
                skipped_trips += 1
                continue
            set_user_id(guest_id)
            full_plan = await asyncio.to_thread(trip_planner._load_history_trip, tid)
            if not full_plan:
                skipped_trips += 1
                continue
            set_user_id(auth_id)
            await asyncio.to_thread(trip_planner._mirror_to_history, full_plan)
            copied_trips += 1

        copied_prefs = False
        set_user_id(guest_id)
        guest_prefs = prefs_store.load_preferences()
        if prefs_store.has_non_default_preferences(guest_prefs):
            set_user_id(auth_id)

            def adopt_guest_prefs(auth_prefs: dict) -> dict | None:
                nonlocal copied_prefs
                copied_prefs = False
                merged = prefs_store.adopt_missing_preferences(auth_prefs, guest_prefs)
                copied_prefs = merged != auth_prefs
                return merged if copied_prefs else None

            prefs_store.mutate_preferences(adopt_guest_prefs)

        set_user_id(auth_id)
        auth_active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
        if guest_active and not auth_active:
            await asyncio.to_thread(trip_planner._save_active_trip, guest_active)
        copied_chat = await asyncio.to_thread(chat_store.adopt_state, guest_chat_state)
    finally:
        set_user_id(auth_id)
        await release_workspace_exclusive(workspace)

    app_event(
        "api_guest_migrate",
        copied_trips=copied_trips,
        skipped_trips=skipped_trips,
        copied_prefs=copied_prefs,
        copied_chat=copied_chat,
    )
    return {
        "ok": True,
        "copied_trips": copied_trips,
        "skipped_trips": skipped_trips,
        "copied_prefs": copied_prefs,
        "copied_chat": copied_chat,
    }


@router.get("/account/guest-data-summary")
async def account_guest_data_summary(request: Request, user_id: str) -> dict:
    """How much data does a guest (web-*) account have?

    Called by the frontend after OAuth login to decide whether to offer
    the guest-import banner.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.tools import user_preferences as prefs_store

    guest_id = (user_id or "").strip()
    if not is_anonymous_id(guest_id):
        return {"has_data": False, "trip_count": 0}
    if is_hosted():
        require_signed_user(request)
        require_guest_capability(request, guest_id)
    set_user_id(guest_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
    count = len(trips) + (1 if active and not trips else 0)
    preferences = await asyncio.to_thread(prefs_store.load_preferences)
    has_preferences = prefs_store.has_non_default_preferences(preferences)
    return {
        "has_data": count > 0 or has_preferences,
        "trip_count": count,
        "has_preferences": has_preferences,
    }


# ---------------------------------------------------------------------------
# Google OAuth — standalone HMAC-signed session cookie. Degrades gracefully:
# when OAUTH_GOOGLE_CLIENT_ID etc. are unset, /auth/me reports
# {authenticated: false} and the SPA falls back to name/anon.
# ---------------------------------------------------------------------------
@router.get("/auth/config")
async def auth_config(request: Request) -> dict:
    """Tells the SPA whether to show the 'Sign in with Google' button, and
    surfaces the exact redirect URI the backend will hand to Google — copy
    this verbatim into the Google Cloud Console 'Authorized redirect URIs'
    list to avoid redirect_uri_mismatch."""
    return {
        "google": oauth.is_enabled(),
        "guest_sessions": oauth.signing_enabled(),
        "redirect_uri": oauth.redirect_uri(str(request.base_url)),
    }


@router.post("/auth/guest/session")
async def auth_guest_session(req: UserRequest, request: Request) -> Response:
    """Issue a signed capability for a browser/native anonymous identity."""
    current = oauth.read_session(request.cookies.get(oauth.SESSION_COOKIE))
    if current and current.get("session_kind") != "guest":
        return JSONResponse({"authenticated": True, "user_id": current["user_id"], "token": ""})
    guest_id = (req.user_id or "").strip()
    if not is_anonymous_id(guest_id):
        return JSONResponse({"authenticated": False}, status_code=400)
    if not oauth.signing_enabled():
        if is_hosted():
            return JSONResponse({"authenticated": False}, status_code=503)
        return JSONResponse({"authenticated": False, "user_id": guest_id, "token": ""})

    token = oauth.make_guest_token(guest_id)
    response = JSONResponse({"authenticated": False, "user_id": guest_id, "token": token})
    response.set_cookie(
        oauth.SESSION_COOKIE,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(request),
        path="/",
    )
    return response


@router.get("/auth/me")
async def auth_me(request: Request) -> dict:
    """Return the signed-in identity (from the session cookie) or anonymous."""
    session = oauth.read_session(request.cookies.get(oauth.SESSION_COOKIE))
    if not session or session.get("session_kind") == "guest":
        return {"authenticated": False}
    return {
        "authenticated": True,
        **{key: value for key, value in session.items() if key != "session_kind"},
    }


@router.get("/auth/mobile/session")
async def auth_mobile_session(token: str = "") -> Response:
    """Validate a signed OAuth session returned to the native app."""
    session = oauth.read_session(token)
    if not session or session.get("session_kind") == "guest":
        return JSONResponse({"authenticated": False}, status_code=401)
    return JSONResponse(
        {
            "authenticated": True,
            **{key: value for key, value in session.items() if key != "session_kind"},
        }
    )


@router.get("/auth/login/google")
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


@router.get("/auth/callback/google")
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
        from tripplanner.tools import user_preferences as prefs_store
        from tripplanner.user_context import set_user_id

        set_user_id(identifier)
        if profile.get("name"):
            display_name = profile["name"].split()[0]

            def seed_display_name(prefs: dict) -> dict | None:
                profile_blob = dict(prefs.get("profile") or {})
                if profile_blob.get("display_name"):
                    return None
                profile_blob["display_name"] = display_name
                prefs["profile"] = profile_blob
                return prefs

            prefs_store.mutate_preferences(seed_display_name)
    except Exception:
        pass  # profile seeding is best-effort; never block login

    app_event("api_oauth_login", provider="google")
    token = oauth.make_session_token(
        identifier, profile.get("name", ""), profile.get("email", ""), profile.get("picture", "")
    )
    res = RedirectResponse(_mobile_auth_redirect(post_login, token) or post_login or "/", status_code=302)
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


@router.post("/auth/logout")
async def auth_logout() -> JSONResponse:
    res = JSONResponse({"ok": True})
    res.delete_cookie(oauth.SESSION_COOKIE, path="/")
    return res


