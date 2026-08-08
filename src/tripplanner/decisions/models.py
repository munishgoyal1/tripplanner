"""Schema for a recorded planning decision.

A decision keeps what was chosen, what was rejected, the rule that separated
them, and where every number came from. Prices are nullable by design: an
option with no reliable fare source carries no number at all rather than an
invented one.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

MAX_REJECTED_BECAUSE = 240
MAX_DETAIL = 120


class TransportMode(StrEnum):
    FLIGHT = "flight"
    TRAIN = "train"
    ROAD = "road"
    COACH = "coach"
    FERRY = "ferry"
    METRO = "metro"
    WALK = "walk"


class DecisionKind(StrEnum):
    TRANSPORT_MODE = "transport_mode"
    LODGING = "lodging"
    FLIGHT = "flight"
    DAY_SHAPE = "day_shape"


class DecisionState(StrEnum):
    AGENT = "agent"
    OVERRULED = "overruled"


class PricedState(StrEnum):
    """How much of a comparison carried a real fare."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class UnpricedReason(StrEnum):
    NO_SOURCE = "no_source"
    SOURCE_FAILED = "source_failed"
    OUT_OF_COVERAGE = "out_of_coverage"


class FareBasis(StrEnum):
    PER_TRAVELLER = "per_traveller"
    PER_PARTY = "per_party"


class Confidence(StrEnum):
    """There is deliberately no ``estimated`` tier. A price is real or absent."""

    LIVE = "live"
    CACHED = "cached"


class Price(BaseModel):
    amount: float
    currency: str
    basis: FareBasis = FareBasis.PER_TRAVELLER
    # Aggregators such as Rome2rio publish ranges, not points. A range must never
    # be rendered as a fixed price, so it stays distinguishable to the pixel.
    amount_max: float | None = None

    @property
    def is_range(self) -> bool:
        return self.amount_max is not None and self.amount_max > self.amount


class Source(BaseModel):
    provider: str | None = None
    url: str | None = None
    checked_at: datetime | None = None
    expires_at: datetime | None = None
    confidence: Confidence = Confidence.LIVE


class Option(BaseModel):
    id: str
    mode: TransportMode
    label: str
    detail: str = ""
    price: Price | None = None
    priced: bool = False
    unpriced_reason: UnpricedReason | None = None
    duration_min: int | None = None
    door_to_door_min: int | None = None
    # A time can be modelled from distance when no provider returns one; a price
    # can never be. The flag exists so the UI can say "about" and mean it.
    duration_estimated: bool = False
    day_cost: float = 0.0
    rejected_because: str | None = None
    source: Source = Field(default_factory=Source)

    def model_post_init(self, _context: Any) -> None:
        object.__setattr__(self, "priced", self.price is not None)
        if self.price is None and self.unpriced_reason is None:
            object.__setattr__(self, "unpriced_reason", UnpricedReason.NO_SOURCE)
        if self.price is not None:
            object.__setattr__(self, "unpriced_reason", None)
        if self.detail and len(self.detail) > MAX_DETAIL:
            object.__setattr__(self, "detail", self.detail[: MAX_DETAIL - 1] + "…")
        if self.rejected_because and len(self.rejected_because) > MAX_REJECTED_BECAUSE:
            object.__setattr__(
                self, "rejected_because", self.rejected_because[: MAX_REJECTED_BECAUSE - 1] + "…"
            )


class Rule(BaseModel):
    code: str
    text: str


class Effect(BaseModel):
    total_cost: float | None = None
    delta: float | None = None
    currency: str = ""


class OverrideRecord(BaseModel):
    option_id: str
    at: datetime
    previous_option_id: str
    effect: Effect = Field(default_factory=Effect)
    warnings: list[str] = Field(default_factory=list)


class DecisionScope(BaseModel):
    day: int | None = None
    from_place: str = ""
    to_place: str = ""
    date: str = ""


class Decision(BaseModel):
    id: str
    kind: DecisionKind = DecisionKind.TRANSPORT_MODE
    created_at: datetime
    scope: DecisionScope = Field(default_factory=DecisionScope)
    subject: str = ""
    rule: Rule
    chosen_option_id: str
    options: list[Option] = Field(default_factory=list)
    state: DecisionState = DecisionState.AGENT
    override: OverrideRecord | None = None
    effect: Effect = Field(default_factory=Effect)
    priced: PricedState = PricedState.NONE

    @property
    def chosen(self) -> Option | None:
        return self.option(self.active_option_id)

    @property
    def active_option_id(self) -> str:
        return self.override.option_id if self.override else self.chosen_option_id

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)


def priced_state(options: list[Option]) -> PricedState:
    priced = sum(1 for option in options if option.price is not None)
    if not options or priced == 0:
        return PricedState.NONE
    return PricedState.FULL if priced == len(options) else PricedState.PARTIAL


def make_decision_id(kind: str, *parts: str | int | None) -> str:
    """Deterministic id, so re-running a comparison updates rather than duplicates."""
    raw = "_".join(str(part).strip().lower() for part in parts if part not in (None, ""))
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return f"dec_{kind}_{slug}" if slug else f"dec_{kind}"


def decision_to_dict(decision: Decision) -> dict[str, Any]:
    return decision.model_dump(mode="json", exclude_none=False)


def decision_from_dict(raw: dict[str, Any]) -> Decision | None:
    """Tolerant read: a malformed record must never break loading a trip."""
    try:
        return Decision.model_validate(raw)
    except Exception:
        return None
