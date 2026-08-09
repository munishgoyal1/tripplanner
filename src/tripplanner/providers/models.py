"""Normalized live-inventory models shared by every travel provider."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class QuoteStatus(StrEnum):
    LIVE = "live"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    ESTIMATED = "estimated"
    PROVIDER_ERROR = "provider_error"


class Money(BaseModel):
    amount: float
    currency: str
    taxes: float | None = None
    fees: float | None = None
    due_at_property: float | None = None


class HotelSearchQuery(BaseModel):
    destination: str
    checkin: str
    checkout: str
    adults_per_room: int = Field(default=2, ge=1)
    rooms: int = Field(default=1, ge=1)
    children_ages: list[int] = Field(default_factory=list)
    currency: str = "INR"
    guest_nationality: str = "IN"
    refundable_only: bool = False
    max_results: int = Field(default=5, ge=1, le=20)


class HotelOffer(BaseModel):
    provider: str
    provider_ref: dict[str, str]
    hotel_name: str
    search_destination: str
    room_name: str
    board_name: str | None = None
    total: Money
    refundable: bool | None = None
    cancellation_summary: str | None = None
    quoted_at: datetime
    expires_at: datetime | None = None
    status: QuoteStatus = QuoteStatus.LIVE
    address: str | None = None
    rating: float | None = None


class FlightSearchQuery(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: str = ""
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    infants: int = Field(default=0, ge=0)
    cabin_class: str = "ECONOMY"
    currency: str = "INR"
    country: str = "IN"
    max_results: int = Field(default=5, ge=1, le=20)


class FlightOffer(BaseModel):
    provider: str
    provider_ref: dict[str, str]
    total: Money
    segments: list[dict[str, Any]]
    quoted_at: datetime
    expires_at: datetime | None = None
    status: QuoteStatus = QuoteStatus.LIVE
    seats_remaining: int | None = None
    baggage: dict[str, Any] | None = None
    terms: dict[str, Any] | None = None
    changes: dict[str, Any] | None = None


class ActivitySearchQuery(BaseModel):
    destination: str
    start_date: str = ""
    end_date: str = ""
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    currency: str = "INR"
    max_results: int = Field(default=10, ge=1, le=20)


class ActivityOffer(BaseModel):
    provider: str
    provider_ref: dict[str, str]
    title: str
    destination: str
    from_price: Money
    total: Money | None = None
    available: bool | None = None
    availability_ranges: list[dict[str, str]] = Field(default_factory=list)
    duration_minutes: dict[str, int] | None = None
    rating: float | None = None
    review_count: int | None = None
    cancellation_summary: str | None = None
    confirmation_type: str | None = None
    provider_url: str | None = None
    quoted_at: datetime
    status: QuoteStatus = QuoteStatus.LIVE


class HotelAvailabilityProvider(Protocol):
    name: str

    def search_hotels(self, query: HotelSearchQuery) -> list[HotelOffer]: ...


class FlightAvailabilityProvider(Protocol):
    name: str

    def search_flights(self, query: FlightSearchQuery) -> list[FlightOffer]: ...

    def verify_flight(self, offer_id: str) -> FlightOffer: ...


class ActivityAvailabilityProvider(Protocol):
    name: str

    def search_activities(self, query: ActivitySearchQuery) -> list[ActivityOffer]: ...


# Rail transport models (train, coach, ferry)
class RailSearchQuery(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: str = ""
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    currency: str = "INR"
    max_results: int = Field(default=5, ge=1, le=20)


class RailOffer(BaseModel):
    provider: str
    provider_ref: dict[str, str]
    total: Money
    segments: list[dict[str, Any]]
    quoted_at: datetime
    expires_at: datetime | None = None
    status: QuoteStatus = QuoteStatus.LIVE
    journey_duration_min: int | None = None
    changes: int | None = None
    direct: bool | None = None
    booking_url: str | None = None


# Coach/bus search and offer (extends rail models)
class CoachSearchQuery(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: str = ""
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    currency: str = "INR"
    max_results: int = Field(default=5, ge=1, le=20)


class CoachOffer(BaseModel):
    provider: str
    provider_ref: dict[str, str]
    total: Money
    segments: list[dict[str, Any]]
    quoted_at: datetime
    expires_at: datetime | None = None
    status: QuoteStatus = QuoteStatus.LIVE
    journey_duration_min: int | None = None
    operator_name: str | None = None
    amenities: list[str] = Field(default_factory=list)
    booking_url: str | None = None


# Ferry search and offer
class FerrySearchQuery(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: str = ""
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    currency: str = "INR"
    max_results: int = Field(default=5, ge=1, le=20)


class FerryOffer(BaseModel):
    provider: str
    provider_ref: dict[str, str]
    total: Money
    segments: list[dict[str, Any]]
    quoted_at: datetime
    expires_at: datetime | None = None
    status: QuoteStatus = QuoteStatus.LIVE
    journey_duration_min: int | None = None
    route_name: str | None = None
    cabin_options: list[str] = Field(default_factory=list)
    booking_url: str | None = None


# Provider protocols
class RailAvailabilityProvider(Protocol):
    """Protocol for rail (train) search providers."""

    name: str

    def search_rails(self, query: RailSearchQuery) -> list[RailOffer]: ...


class CoachAvailabilityProvider(Protocol):
    """Protocol for coach/bus search providers."""

    name: str

    def search_coaches(self, query: CoachSearchQuery) -> list[CoachOffer]: ...


class FerryAvailabilityProvider(Protocol):
    """Protocol for ferry search providers."""

    name: str

    def search_ferries(self, query: FerrySearchQuery) -> list[FerryOffer]: ...
