"""Validated request and response contracts for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12_000)
    user_id: str = "local"
    proposal_only: bool = False
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class ChatResponse(BaseModel):
    reply: str
    agent: str
    trip_id: str | None = None


class SelectRequest(BaseModel):
    kind: str
    name: str
    user_id: str = "local"
    start_day: int | None = None
    end_day: int | None = None
    day: int | None = None
    source_day: int | None = None
    source_stop: int | None = None
    replace_stay: bool = True


class DeselectRequest(BaseModel):
    kind: str
    name: str
    user_id: str = "local"
    day: int | None = None
    stop: int | None = None
    all_occurrences: bool = True


class DecisionOverrideRequest(BaseModel):
     option_id: str
     user_id: str = "local"
     updated_at: str = ""


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


class ConfirmPlaceRequest(BaseModel):
    name: str
    user_id: str = "local"


class PreferencesRequest(BaseModel):
    user_id: str = "local"
    display_name: str | None = None
    home_city: str | None = None
    home_country: str | None = None
    display_region: str | None = None
    display_language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    display_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    trip_style: str | None = None
    budget_level: str | None = None
    flight_class: str | None = None
    prefer_direct_flights: bool | None = None
    hotel_star_rating_min: int | None = None
    dietary: list[str] | None = None
    interests: list[str] | None = None
    dislikes: list[str] | None = None
    planning_mode: Literal["direct", "interactive"] | None = None
    about_me: str | None = None
    profile_summary: str | None = None
    profile_summary_updated_at: str | None = None


class PrivacyActionRequest(BaseModel):
    user_id: str = "local"
    action: Literal["delete_trip_history", "clear_all_data", "delete_account"]
    confirm_text: str = ""


class DocumentExtractRequest(BaseModel):
    user_id: str = "local"
    type: str
    content_base64: str = ""
    text: str = ""


class DocumentSaveRequest(BaseModel):
    user_id: str = "local"
    id: str = ""
    type: str
    scope: Literal["traveler", "trip"] = "traveler"
    traveller_key: str = "self"
    traveller_name: str = ""
    trip_id: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class DocumentDeleteRequest(BaseModel):
    user_id: str = "local"
    id: str


class GuestMigrateRequest(BaseModel):
    user_id: str
    guest_id: str


class ExportEmailRequest(BaseModel):
    user_id: str = "local"
    email: str
    include_photos: bool = True
    include_map_circuit: bool = True
    template: Literal["minimal", "detailed", "family"] = "detailed"
    request_id: str = Field(min_length=1, max_length=128)
