"""Tolerant contracts for persisted trips and mutation outcomes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TolerantModel(BaseModel):
    """Validate known fields without dropping fields written by older versions."""

    model_config = ConfigDict(extra="allow")


class Stop(TolerantModel):
    name: str = ""
    kind: str = ""
    time: str = ""
    duration_min: int | None = None
    note: str = ""


class ItineraryDay(TolerantModel):
    day: int | None = None
    date: str = ""
    title: str = ""
    summary: str = ""
    stops: list[Stop | str] = Field(default_factory=list)


class TripPlan(TolerantModel):
    trip_id: str = ""
    revision: int = 0
    destination: str = ""
    departure_date: str = ""
    return_date: str = ""
    status: str = "draft"
    updated_at: str = ""
    day_wise_itinerary: list[ItineraryDay] = Field(default_factory=list)


class TripPatch(TolerantModel):
    """A partial update; unset fields do not replace persisted values."""

    trip_id: str | None = None
    destination: str | None = None
    departure_date: str | None = None
    return_date: str | None = None
    status: str | None = None
    day_wise_itinerary: list[ItineraryDay] | None = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude_unset=True)


class UpdateOutcome(TolerantModel):
    ok: bool
    plan: TripPlan | None = None
    revision: int | None = None
    conflict: bool = False
    message: str = ""
