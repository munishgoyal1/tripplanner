"""Identity-bound booking intent reads, previews, mutations and research."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from tripplanner.decisions.booking_intent import (
    ActualBooking,
    Cap,
    build_booking_view,
    digest,
    prepare_change,
)
from tripplanner.request_limits import acquire_workspace_exclusive, release_workspace_exclusive
from tripplanner.tools import trip_planner
from tripplanner.web.http_context import set_request_user

router = APIRouter()


class BookingExportRequest(BaseModel):
    user_id: str = "local"
    trip_id: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


@router.post("/trip/bookings/share")
async def share_bookings(req: BookingExportRequest, request: Request):
    from tripplanner.web.share import mint_booking_intent

    set_request_user(request, req.user_id)
    plan = await asyncio.to_thread(checked_plan, req.trip_id, req.updated_at)
    token = await asyncio.to_thread(mint_booking_intent, plan)
    return {"url": f"{str(request.base_url).rstrip('/')}/trip/shared/{token}"}


@router.get("/trip/bookings/export.json")
async def export_bookings(request: Request, trip_id: str, updated_at: str, user_id: str = "local"):
    from tripplanner.web.booking_export import snapshot

    set_request_user(request, user_id)
    plan = await asyncio.to_thread(checked_plan, trip_id, updated_at)
    return JSONResponse(
        snapshot(plan),
        headers={"Content-Disposition": 'attachment; filename="booking-intent.json"'},
    )


class Search(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["flights", "hotels"]
    origin: str = Field(default="", max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(default="", max_length=10)
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    infants: int = Field(default=0, ge=0, le=8)
    children_ages: list[int] = Field(default_factory=list, max_length=8)
    rooms: int = Field(default=1, ge=1, le=8)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    nationality: str = Field(default="", pattern=r"^(?:[A-Z]{2})?$")
    cabin: Literal["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"] = "ECONOMY"
    refundable_only: bool = False


class BookingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = "local"
    trip_id: str = Field(min_length=1, max_length=240)
    updated_at: str = Field(min_length=1, max_length=80)
    action: Literal[
        "choose", "lock", "unlock", "report", "manual", "caps", "disposition", "research"
    ]
    item_id: str = Field(default="", max_length=240)
    option_id: str = Field(default="", max_length=240)
    caps: dict[str, Cap] = Field(default_factory=dict)
    actual: ActualBooking | None = None
    disposition: str = ""
    search: Search | None = None
    preview: bool = True
    preview_token: str = Field(default="", max_length=64)


def checked_plan(
    trip_id: str = "", updated_at: str = "", *, require_revision: bool = False
) -> dict:
    if require_revision and (not trip_id or not updated_at):
        raise HTTPException(
            422, "Booking intent exports require the trip and revision being reviewed."
        )
    plan = trip_planner.load_active_trip_dict()
    if not plan:
        raise HTTPException(404, "There is no active trip. Open a trip in the planner first.")
    if trip_id and plan.get("trip_id") != trip_id:
        raise HTTPException(
            409, "The active trip changed. Return to the planner and open the intended trip."
        )
    if updated_at and plan.get("updated_at") != updated_at:
        raise HTTPException(409, "The trip changed. Reload and preview the adjustment again.")
    return plan


@router.get("/trip/bookings")
async def bookings(request: Request, user_id: str = "local", trip_id: str = "") -> dict:
    set_request_user(request, user_id)
    return await asyncio.to_thread(lambda: build_booking_view(checked_plan(trip_id)))


@trip_planner._serialized_mutation
def execute_command(req: BookingCommand) -> dict:
    plan = checked_plan(req.trip_id, req.updated_at)
    command = req.model_dump(exclude={"user_id", "preview", "preview_token"})
    if req.action == "research":
        if req.search is None:
            raise ValueError("Supply exact search dates and party details.")
        search = req.search
        date.fromisoformat(search.start_date)
        if search.end_date:
            date.fromisoformat(search.end_date)
            if search.end_date < search.start_date:
                raise ValueError("The end date must follow the start date.")
        if search.category == "flights":
            if not search.origin.strip():
                raise ValueError("Flight origin is required.")
            from tripplanner.tools.flight_search import search_flights

            result = search_flights.invoke(
                {
                    "origin": search.origin,
                    "destination": search.destination,
                    "departure_date": search.start_date,
                    "return_date": search.end_date,
                    "adults": search.adults,
                    "children": search.children,
                    "infants": search.infants,
                    "travel_class": search.cabin,
                    "currency": search.currency,
                    "refresh": True,
                }
            )
        else:
            if not search.end_date or search.end_date <= search.start_date:
                raise ValueError("Hotel checkout must follow check-in.")
            if any(age < 0 or age > 17 for age in search.children_ages):
                raise ValueError("Child ages must be between 0 and 17.")
            if len(search.children_ages) != search.children + search.infants:
                raise ValueError("Supply one age for every child and infant in the hotel search.")
            if not search.nationality:
                raise ValueError("Supply the guest nationality for hotel research.")
            from tripplanner.tools.hotel_search import search_hotels

            result = search_hotels.invoke(
                {
                    "city": search.destination,
                    "checkin": search.start_date,
                    "checkout": search.end_date,
                    "adults": search.adults,
                    "rooms": search.rooms,
                    "currency": search.currency,
                    "refresh": True,
                    "children_ages": search.children_ages,
                    "guest_nationality": search.nationality,
                    "refundable_only": search.refundable_only,
                }
            )
        import json

        try:
            payload = json.loads(str(result))
            summary = str(
                payload.get("notice")
                or payload.get("guidance")
                or f"Provider response: {payload.get('quote_status', 'received')}. Saved options are shown below."
            )
        except (ValueError, AttributeError):
            summary = str(result)
        return {
            "ok": True,
            "message": "Research completed. Review the saved options and evidence.",
            "research_result": summary,
            "bookings": build_booking_view(checked_plan(req.trip_id)),
        }
    candidate, warnings = prepare_change(plan, command)
    token = digest(command)
    if req.preview:
        return {
            "ok": True,
            "preview": True,
            "preview_token": token,
            "warnings": warnings,
            "before": build_booking_view(plan),
            "bookings": build_booking_view(candidate),
            "message": "Review this adjustment before saving.",
        }
    if req.preview_token != token:
        raise ValueError("Preview this exact adjustment before applying it.")
    trip_planner._save_active_trip(candidate)
    return {
        "ok": True,
        "message": "Booking intent updated.",
        "warnings": warnings,
        "bookings": build_booking_view(candidate),
    }


@router.post("/trip/bookings")
async def change_bookings(req: BookingCommand, request: Request):
    resolved = set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(resolved)
    try:
        try:
            return await asyncio.to_thread(execute_command, req)
        except ValueError as exc:
            return JSONResponse({"ok": False, "message": str(exc)}, status_code=422)
    finally:
        await release_workspace_exclusive(workspace)
