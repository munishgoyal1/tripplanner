"""Trip workspace HTTP routes: view, mutate, export, share, and history."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from tripplanner.api_contracts import (
    AuditInspectRequest,
    ConfirmPlaceRequest,
    DecisionBatchOverrideRequest,
    DecisionOverrideRequest,
    DeselectRequest,
    ExportEmailRequest,
    SelectRequest,
    StopBookedRequest,
    TripFeedbackRequest,
    TripIdRequest,
    TripRepairRequest,
    UserRequest,
)
from tripplanner.observability import app_event
from tripplanner.request_identity import inspect_override, is_hosted, signed_session
from tripplanner.request_limits import acquire_workspace_exclusive, release_workspace_exclusive
from tripplanner.web.http_context import run_agent_background as _run_agent_background
from tripplanner.web.http_context import set_request_user as _set_request_user

router = APIRouter()

@router.get("/trip/view")
async def trip_view_endpoint(
    request: Request,
    background: BackgroundTasks,
    user_id: str = "local",
    focus_kind: str = "",
    focus_name: str = "",
    focus_day: int | None = None,
    focus_stop: int | None = None,
) -> dict:
    """Frontend-agnostic trip-panel view-model with optional occurrence focus."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    focus = (
        {
            "kind": focus_kind,
            "name": focus_name,
            **({"day": focus_day} if focus_day is not None else {}),
            **({"stop": focus_stop} if focus_stop is not None else {}),
        }
        if focus_name
        else None
    )
    view = await asyncio.to_thread(trip_operations.build_view, focus)
    trip_id = str(view.get("trip_id") or "")
    # A focus response only blocks on the focused place; an unfocused response
    # only blocks on its own small gallery slice (_MAX_GALLERY_ITEMS) -- either
    # way, top up the rest of the trip's places afterwards so the next view
    # (a focus, a panel switch, or a plain reload) stays a cache hit instead of
    # blocking on a fresh, rate-limited Places lookup. Previously this only
    # ran after a *focused* request, so the very first/general load of a large
    # trip never got proactively warmed in the background at all.
    background.add_task(
        _run_agent_background,
        trip_operations.warm_view_items,
        route="warm_view_items",
        trip_id=trip_id,
    )
    if focus is None:
        # Warm the destination-guide dataset too so the first city/kind switch
        # is instant while the user is still reading the itinerary.
        background.add_task(
            _run_agent_background,
            trip_operations.warm_guide,
            route="warm_guide",
            trip_id=trip_id,
        )
    return view


@router.get("/trip/workspace")
async def trip_workspace_endpoint(
    request: Request,
    background: BackgroundTasks,
    user_id: str = "local",
    focus_kind: str = "",
    focus_name: str = "",
    focus_day: int | None = None,
    focus_stop: int | None = None,
) -> dict:
    """Return every workspace projection from one active-trip snapshot."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    focus = (
        {
            "kind": focus_kind,
            "name": focus_name,
            **({"day": focus_day} if focus_day is not None else {}),
            **({"stop": focus_stop} if focus_stop is not None else {}),
        }
        if focus_name
        else None
    )
    payload = await asyncio.to_thread(trip_operations.active_workspace_payload, focus)
    trip_id = str((payload.get("view") or {}).get("trip_id") or "")
    # See /trip/view above: warm the rest of the trip's places regardless of
    # focus, not only after a focused request.
    background.add_task(
        _run_agent_background,
        trip_operations.warm_view_items,
        route="warm_view_items",
        trip_id=trip_id,
    )
    if focus is None:
        background.add_task(
            _run_agent_background,
            trip_operations.warm_guide,
            route="warm_guide",
            trip_id=trip_id,
        )
    return payload


@router.post("/trip/fork")
async def fork_inspected_trip(request: Request) -> dict:
    """Copy the trip being inspected into the caller's own workspace.

    The one write inspection allows. The corpus stays exactly as the audit found
    it, and the caller gets something they may freely break.
    """
    inspected = inspect_override(request)
    if not inspected:
        raise HTTPException(status_code=404, detail="Not found.")

    body = await request.json()
    trip_id = str(body.get("trip_id") or "").strip()
    # The browser only knows its previous identity when one was in localStorage;
    # a cookie-only sign-in leaves it blank, and the session is the truth anyway.
    session = signed_session(request)
    owner_id = str(body.get("owner_id") or "").strip() or str(
        (session or {}).get("user_id") or ""
    ).strip()
    if not owner_id or not trip_id:
        raise HTTPException(status_code=400, detail="A trip id and an owner are required.")
    if owner_id == inspected:
        raise HTTPException(status_code=400, detail="A trip cannot be forked onto itself.")

    def _fork() -> str:
        from tripplanner import storage_cosmos
        from tripplanner.tools import trip_planner

        source = storage_cosmos.read_doc(trip_planner._COSMOS_TRIPS_CONTAINER, inspected, trip_id)
        if source is None:
            raise HTTPException(status_code=404, detail="That trip no longer exists.")

        copy_id = f"{trip_id}__copy-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        plan = dict(source)
        plan["trip_id"] = copy_id
        plan["status"] = "draft"
        plan["created_at"] = datetime.now().isoformat()
        plan["updated_at"] = plan["created_at"]
        # Says, in the data rather than only in the UI, that this is no longer
        # corpus: the audit reads both and must be able to tell them apart.
        plan["forked_from"] = f"{inspected}:{trip_id}"

        storage_cosmos.upsert_doc(
            trip_planner._COSMOS_TRIPS_CONTAINER, owner_id, copy_id, plan
        )
        storage_cosmos.upsert_doc(
            trip_planner._COSMOS_USERS_CONTAINER,
            owner_id,
            trip_planner._ACTIVE_TRIP_DOC_ID,
            plan,
        )
        return copy_id

    copy_id = await asyncio.to_thread(_fork)
    app_event("trip_forked_from_inspection", source=inspected)
    return {"trip_id": copy_id, "owner_id": owner_id, "forked_from": f"{inspected}:{trip_id}"}


@router.post("/trip/budget/what-if")
async def trip_budget_what_if(request: Request, user_id: str = "local") -> dict:
    """Generate grounded savings proposals only when the traveller asks."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    return await asyncio.to_thread(trip_operations.build_budget_what_if)


@router.get("/trip/places")
async def trip_places_endpoint(
    request: Request,
    user_id: str = "local",
    city: str = "",
    kind: str = "",
    query: str = "",
    cursor: str = "",
    limit: int = 6,
    focus_kind: str = "",
    focus_name: str = "",
) -> dict:
    """Cursor-paged destination-guide place discovery (Lab 13).

    Filters the balanced place pool by ``city``/``kind``/``query`` and returns one
    lightweight page plus counts and available filter values. With ``focus_name``
    set, returns same-city, same-kind alternatives to the focused place.
    """
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    return await asyncio.to_thread(
        trip_operations.paged_places,
        city=city or None,
        kind=kind or None,
        query=query or None,
        cursor=cursor or None,
        limit=limit,
        focus_kind=focus_kind or None,
        focus_name=focus_name or None,
    )


@router.get("/maps/config")
async def maps_config_endpoint() -> dict:
    """Expose whether the interactive map is enabled + its browser key.

    The key is a referrer-restricted browser key (see ``config.py``); returning
    it here is the standard pattern for the Maps JavaScript API. Empty key →
    ``enabled: false`` and the SPA hides the map panel.
    """
    from tripplanner.config import get_settings

    settings = get_settings()
    key = settings.google_maps_browser_key or ""
    enabled = settings.enable_google_maps and bool(key)
    return {
        "enabled": enabled,
        "places_enabled": enabled and settings.enable_google_places,
        "key": key if enabled else "",
    }


@router.get("/analytics/config")
async def analytics_config_endpoint() -> dict:
    """Expose the public GA4 id only for the production environment."""
    import os
    import re

    from tripplanner.config import get_settings

    environment = os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower()
    measurement_id = get_settings().google_analytics_measurement_id.strip().upper()
    enabled = environment in {"prod", "production"} and bool(
        re.fullmatch(r"G-[A-Z0-9]+", measurement_id)
    )
    return {"enabled": enabled, "measurement_id": measurement_id if enabled else ""}


@router.get("/trip/map")
async def trip_map_endpoint(request: Request, user_id: str = "local") -> dict:
    """Interactive-map view-model: geocoded, day-tagged pins + route bands."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    return await asyncio.to_thread(trip_operations.build_map)


@router.get("/destination/overview")
async def destination_overview_endpoint(
    request: Request,
    destination: str = "",
    user_id: str = "local",
    news: bool = True,
) -> dict:
    """Destination-level overview (photos, key attractions, reviews, news).

    When ``destination`` is omitted, falls back to the active trip's
    destination so the SPA can show "about the place" before any selections.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.web import trip_view

    _set_request_user(request, user_id)
    if not destination:
        trip = trip_planner.load_active_trip_dict()
        destination = str((trip or {}).get("destination") or "")
    return await asyncio.to_thread(
        trip_view.build_destination_overview, destination, include_news=news
    )



@router.post("/trip/select")
async def trip_select(req: SelectRequest, request: Request) -> dict:
    """Add a hotel/attraction to the active trip (the SPA's 'Add to trip')."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        return await asyncio.to_thread(
            trip_operations.select,
            req.kind,
            req.name,
            start_day=req.start_day,
            end_day=req.end_day,
            day=req.day,
            source_day=req.source_day,
            source_stop=req.source_stop,
            replace_stay=req.replace_stay,
        )
    finally:
        await release_workspace_exclusive(workspace)


@router.post("/trip/deselect")
async def trip_deselect(req: DeselectRequest, request: Request) -> dict:
    """Remove a hotel/attraction from the active trip (the SPA's 'Remove')."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        return await asyncio.to_thread(
            trip_operations.deselect,
            req.kind,
            req.name,
            day=req.day,
            stop=req.stop,
            all_occurrences=req.all_occurrences,
        )
    finally:
        await release_workspace_exclusive(workspace)


@router.get("/trip/itinerary")
async def trip_itinerary_endpoint(request: Request, user_id: str = "local") -> dict:
    """Structured day-by-day itinerary view-model (the Itinerary tab)."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    return await asyncio.to_thread(trip_operations.build_itinerary)


@router.get("/trip/verification")
async def trip_verification_endpoint(request: Request, user_id: str = "local") -> dict:
    """What the planner checked on the active trip, and what it could not."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    return await asyncio.to_thread(trip_operations.build_verification)


@router.post("/trip/verification/refresh")
async def trip_verification_refresh_endpoint(req: TripRepairRequest, request: Request) -> dict:
    """Refresh itinerary place facts and report changes since the last check."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        payload = await asyncio.to_thread(
            trip_operations.refresh_facts, expected_updated_at=req.updated_at
        )
        payload["verification"] = await asyncio.to_thread(
            trip_operations.build_verification
        )
        return payload
    finally:
        await release_workspace_exclusive(workspace)


@router.post("/trip/prices/recheck")
async def trip_price_recheck_endpoint(req: TripRepairRequest, request: Request) -> dict:
    """Explicitly refresh stale quote evidence without changing the selected plan."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        payload = await asyncio.to_thread(
            trip_operations.recheck_prices, expected_updated_at=req.updated_at
        )
        payload["view"] = await asyncio.to_thread(trip_operations.build_view)
        return payload
    finally:
        await release_workspace_exclusive(workspace)


@router.post("/trip/repair")
async def trip_repair_endpoint(req: TripRepairRequest, request: Request) -> dict:
    """Rearrange the planner's own stops until the saved trip reads correctly."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        payload = await asyncio.to_thread(
            trip_operations.repair_trip, expected_updated_at=req.updated_at
        )
        if payload.get("changed"):
            payload["view"] = await asyncio.to_thread(trip_operations.build_view)
            payload["itinerary"] = await asyncio.to_thread(trip_operations.build_itinerary)
        payload["verification"] = await asyncio.to_thread(
            trip_operations.build_verification
        )
        return payload
    finally:
        await release_workspace_exclusive(workspace)


@router.post("/trip/stop/booked")
async def trip_stop_booked(req: StopBookedRequest, request: Request) -> dict:
    """Toggle one itinerary stop's booked flag (the Itinerary checkbox)."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        return await asyncio.to_thread(
            trip_operations.set_stop_booked, req.day, req.name, req.booked
        )
    finally:
        await release_workspace_exclusive(workspace)


@router.post("/trip/stop/place")
async def trip_stop_place(req: ConfirmPlaceRequest, request: Request) -> dict:
    """Accept the map's candidate place for a stop it could not pin."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        return await asyncio.to_thread(trip_operations.confirm_stop_place, req.name)
    finally:
        await release_workspace_exclusive(workspace)


@router.post("/trip/decisions/{decision_id}/override")
async def trip_decision_override(
    decision_id: str, req: DecisionOverrideRequest, request: Request
) -> Response:
    """Switch the plan onto the option the traveller picked."""
    return await _apply_decision_override(
        request, decision_id, req.option_id, req.user_id, req.updated_at
    )


@router.delete("/trip/decisions/{decision_id}/override")
async def trip_decision_restore(
    decision_id: str, request: Request, user_id: str = "local", updated_at: str = ""
) -> Response:
    """Undo an overrule and put the agent's own choice back."""
    return await _apply_decision_override(request, decision_id, None, user_id, updated_at)


@router.post("/trip/decisions/overrides")
async def trip_decision_batch_override(
    req: DecisionBatchOverrideRequest, request: Request
) -> Response:
    """Apply multiple decision changes atomically against one trip revision."""
    from tripplanner.config import get_settings
    from tripplanner.web import trip_operations

    if not get_settings().decisions_ui_enabled:
        return JSONResponse(
            {"ok": False, "stale": False, "message": "Decision records are turned off."},
            status_code=404,
        )
    resolved = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(resolved)
    try:
        payload = await asyncio.to_thread(
            trip_operations.apply_decision_overrides,
            [change.model_dump() for change in req.changes],
            expected_updated_at=req.updated_at,
        )
        if payload.get("ok"):
            payload["view"] = await asyncio.to_thread(trip_operations.build_view)
            payload["itinerary"] = await asyncio.to_thread(trip_operations.build_itinerary)
    finally:
        await release_workspace_exclusive(workspace)
    return JSONResponse(payload, status_code=409 if payload.get("stale") else 200)


async def _apply_decision_override(
    request: Request,
    decision_id: str,
    option_id: str | None,
    user_id: str,
    updated_at: str,
) -> Response:
    from tripplanner.config import get_settings
    from tripplanner.web import trip_operations

    if not get_settings().decisions_ui_enabled:
        return JSONResponse(
            {"ok": False, "stale": False, "message": "Decision records are turned off."},
            status_code=404,
        )
    resolved = _set_request_user(request, user_id)
    workspace = await acquire_workspace_exclusive(resolved)
    try:
        payload = await asyncio.to_thread(
            trip_operations.override_decision,
            decision_id,
            option_id,
            expected_updated_at=updated_at,
        )
    finally:
        await release_workspace_exclusive(workspace)
    # A stale write is not an error the traveller caused; hand back the truth.
    status = 409 if payload.get("stale") else 200
    return JSONResponse(payload, status_code=status)


@router.get("/trips")
async def trips_list(request: Request, user_id: str = "local") -> dict:
    """All saved trips for the user (the SPA's 'My trips' switcher)."""
    from tripplanner.tools import trip_planner

    _set_request_user(request, user_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    return {"trips": trips}


@router.post("/trips/switch")
async def trips_switch(req: TripIdRequest, request: Request) -> dict:
    """Make a saved trip active (auto-saving whatever was active) and return
    the refreshed trip-panel view."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        plan = await asyncio.to_thread(trip_operations.activate_trip, req.trip_id)
    finally:
        await release_workspace_exclusive(workspace)
    if plan is None:
        return {"ok": False, "error": "trip not found"}
    # Building the three panel view-models is pure work on an already-loaded
    # plan, so it happens after the lock is released; holding it that long made
    # concurrent requests collide with a 409.
    return await asyncio.to_thread(trip_operations.workspace_payload, plan)


@router.post("/debug/audit/open")
async def debug_audit_open(req: AuditInspectRequest, request: Request) -> dict:
    """Restore one immutable audit artifact into its local inspection identity."""
    if is_hosted():
        raise HTTPException(status_code=404, detail="Not found.")

    from pathlib import Path

    from tripplanner.tools import trip_planner
    from tripplanner.validation import runner as audit_runner
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    records, _, _ = await asyncio.to_thread(
        audit_runner.collect,
        Path(__file__).resolve().parents[2],
        databases=[],
    )
    record = next(
        (
            item
            for item in records
            if item.id == req.record_id or any(link.id == req.record_id for link in item.links)
        ),
        None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Audit record not found.")
    plan = await asyncio.to_thread(trip_planner.restore_inspection_trip, record.plan, user_id)
    return await asyncio.to_thread(trip_operations.workspace_payload, plan)


@router.post("/trips/delete")
async def trips_delete(req: TripIdRequest, request: Request) -> dict:
    """Delete a single saved trip AND its chat history; returns the refreshed
    saved-trips list."""
    from tripplanner.tools import trip_planner
    from tripplanner.web import chat_store

    user_id = _set_request_user(request, req.user_id)
    # Only the active trip is mutated by an in-flight chat turn, so deleting a
    # different saved trip does not need to wait behind it.
    active_id = await asyncio.to_thread(trip_planner.active_trip_id)
    workspace = (
        await acquire_workspace_exclusive(user_id) if req.trip_id == active_id else ()
    )
    try:
        await asyncio.to_thread(trip_planner.delete_saved_trip, req.trip_id)
        await asyncio.to_thread(chat_store.clear, req.trip_id)
        trips = await asyncio.to_thread(trip_planner.list_saved_trips)
        return {"ok": True, "trips": trips}
    finally:
        if workspace:
            await release_workspace_exclusive(workspace)


@router.post("/trip/feedback")
async def trip_feedback(req: TripFeedbackRequest, request: Request) -> dict:
    """Append optional feedback for the active trip without gating later submissions."""
    from tripplanner.tools import trip_planner

    if req.sentiment is None and req.rating is None and not (req.comment or "").strip():
        raise HTTPException(status_code=422, detail="Feedback cannot be empty")
    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        rollup = await asyncio.to_thread(
            trip_planner.record_trip_feedback,
            feedback_id=req.feedback_id,
            sentiment=req.sentiment,
            rating=req.rating,
            comment=req.comment,
            surface=req.surface,
            client=req.client,
        )
    finally:
        await release_workspace_exclusive(workspace)
    if rollup is None:
        raise HTTPException(status_code=404, detail="No active trip")
    return {"ok": True, "feedback": rollup}


@router.post("/trip/new")
async def trip_new(req: UserRequest, request: Request) -> dict:
    """Start a fresh planning chat: clear the active trip + the general chat
    bucket so the next conversation begins clean. Saved trips are untouched."""
    from tripplanner.tools import trip_planner
    from tripplanner.web import chat_store

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        await asyncio.to_thread(trip_planner.start_new_trip)
        await asyncio.to_thread(chat_store.clear, None)
        return {"ok": True}
    finally:
        await release_workspace_exclusive(workspace)


@router.post("/trip/reset")
async def trip_reset(req: UserRequest, request: Request) -> dict:
    """Empty the active trip's plan but keep its destination, dates and people,
    so the user can rebuild without re-entering the brief."""
    from tripplanner.tools import trip_planner
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        plan = await asyncio.to_thread(trip_planner.reset_active_trip)
    finally:
        await release_workspace_exclusive(workspace)
    if plan is None:
        return {"ok": False, "error": "no active trip"}
    return await asyncio.to_thread(trip_operations.workspace_payload, plan)



@router.get("/trip/export.ics")
async def trip_export_ics(request: Request, user_id: str = "local") -> Response:
    """Download the active trip as an iCalendar (.ics) file."""
    from tripplanner.tools import trip_planner
    from tripplanner.web.ics_export import build_ics

    _set_request_user(request, user_id)
    plan = trip_planner.load_active_trip_dict()
    body = build_ics(plan)
    dest = ((plan or {}).get("destination") or "trip").lower()
    safe = "".join(c if c.isalnum() else "-" for c in dest).strip("-") or "trip"
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{safe}.ics"'},
    )


@router.get("/trip/export/print")
async def trip_export_print(
    request: Request,
    user_id: str = "local",
    include_photos: str = "0",
    include_map_circuit: str = "1",
    template: str = "standard",
    auto_print: str = "0",
) -> Response:
    """Return a print-ready HTML itinerary suitable for Save-as-PDF."""
    from tripplanner.tools import trip_planner
    from tripplanner.web.itinerary_export import build_export_html, parse_export_bool

    _set_request_user(request, user_id)
    plan = trip_planner.load_active_trip_dict()
    html = build_export_html(
        plan,
        include_photos=parse_export_bool(include_photos, default=False),
        include_map_circuit=parse_export_bool(include_map_circuit, default=True),
        template=template,
        auto_print=parse_export_bool(auto_print, default=False),
    )
    return Response(content=html, media_type="text/html; charset=utf-8")


@router.get("/trip/export.pdf")
async def trip_export_pdf(
    request: Request,
    user_id: str = "local",
    template: str = "standard",
    include_photos: str = "0",
    include_map_circuit: str = "1",
) -> Response:
    """Return a downloadable itinerary PDF generated server-side."""
    from tripplanner.tools import trip_planner

    _set_request_user(request, user_id)
    plan = trip_planner.load_active_trip_dict()
    if not plan:
        return JSONResponse({"error": "no active trip"}, status_code=404)

    try:
        from tripplanner.web.itinerary_export import parse_export_bool
        from tripplanner.web.itinerary_pdf import build_itinerary_pdf_bytes

        pdf_bytes = build_itinerary_pdf_bytes(
            plan,
            template=template,
            include_photos=parse_export_bool(include_photos, default=False),
            include_map_circuit=parse_export_bool(include_map_circuit, default=True),
        )
    except ImportError:
        return JSONResponse(
            {
                "error": "pdf_renderer_not_installed",
                "message": "Install reportlab to enable direct PDF download.",
            },
            status_code=503,
        )

    dest = str(plan.get("destination") or "trip").strip().lower()
    safe = "".join(c if c.isalnum() else "-" for c in dest).strip("-") or "trip"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-itinerary.pdf"'},
    )


@router.post("/trip/export/email")
async def trip_export_email(req: ExportEmailRequest, request: Request) -> dict:
    """Send the itinerary export once for a client-generated request ID.

    If SMTP is not configured, returns a `mailto:` fallback so the frontend can
    open the user's mail client with a prefilled subject/body.
    """
    from tripplanner.web.itinerary_email import send_itinerary_email

    _set_request_user(request, req.user_id)
    return send_itinerary_email(req, base_url=str(request.base_url))


@router.post("/trip/share")
async def trip_share(req: SelectRequest, request: Request) -> dict:
    """Mint an opaque read-only share token for the active trip.

    Re-using ``SelectRequest`` only for its ``user_id`` field — ``kind``/``name``
    are ignored. Returns ``{token, url}`` or ``{error}`` if no active plan.
    """
    from tripplanner.web.share import mint_for_active_trip

    _set_request_user(request, req.user_id)
    token = mint_for_active_trip()
    if not token:
        return {"error": "no active trip to share"}
    base = str(request.base_url).rstrip("/")
    return {"token": token, "url": f"{base}/trip/shared/{token}"}


@router.get("/trip/shared/{token}")
async def trip_shared_view(token: str, request: Request) -> Response:
    """Public read-only HTML snapshot of a shared trip plan."""
    from tripplanner.web.share import render_public_html

    base = str(request.base_url).rstrip("/")
    html = render_public_html(token, current_origin=base)
    if html is None:
        return JSONResponse(
            {"error": "invalid or expired share link"}, status_code=404
        )
    return Response(content=html, media_type="text/html; charset=utf-8")


@router.get("/trip/shared/{token}.json")
async def trip_shared_json(token: str) -> dict:
    """Public JSON payload for a shared snapshot."""
    from tripplanner.web.share import resolve

    snapshot = resolve(token)
    if snapshot is None:
        return JSONResponse({"error": "invalid or expired share link"}, status_code=404)
    return snapshot


@router.post("/trip/shared/{token}/import")
async def trip_shared_import(token: str, req: UserRequest, request: Request) -> dict:
    """Import a shared snapshot into the caller's own editable trip space."""
    from tripplanner.tools import trip_planner
    from tripplanner.web import share, trip_view

    snapshot = share.resolve(token)
    if snapshot is None:
        return JSONResponse({"error": "invalid or expired share link"}, status_code=404)
    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        imported = await asyncio.to_thread(
            trip_planner.import_shared_trip_snapshot, snapshot.get("plan") or {}
        )
        view = await asyncio.to_thread(trip_view.build_view, imported, None)
        return {"ok": True, "view": view}
    finally:
        await release_workspace_exclusive(workspace)



