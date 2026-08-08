"""Applying a traveller's overrule to the plan. Deterministic — no model call.

The traveller asked for this, so it is applied even when it creates a problem.
What we owe them is the consequence, stated plainly, not a silent refusal and
not a silently hidden casualty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from tripplanner.decisions.models import (
    Decision,
    DecisionState,
    Effect,
    Option,
    OverrideRecord,
    TransportMode,
)
from tripplanner.decisions.rules import money, party_total
from tripplanner.decisions.store import find_decision, upsert_decision

_STOP_KIND = {
    TransportMode.FLIGHT: "flight",
    TransportMode.TRAIN: "transport",
    TransportMode.COACH: "transport",
    TransportMode.ROAD: "transport",
    TransportMode.FERRY: "transport",
    TransportMode.METRO: "transport",
    TransportMode.WALK: "transport",
}

# These words are what `web/transport.py` reads back out of a stop name, so the
# label is the mode as far as every other surface is concerned.
_STOP_PREFIX = {
    TransportMode.FLIGHT: "Flight",
    TransportMode.TRAIN: "Train",
    TransportMode.COACH: "Bus",
    TransportMode.ROAD: "Drive",
    TransportMode.FERRY: "Ferry",
    TransportMode.METRO: "Metro",
    TransportMode.WALK: "Walk",
}

_PRICE_KEYS = ("price", "total_price", "total", "cost", "amount", "fare")


@dataclass
class ApplyResult:
    ok: bool
    message: str
    decision_id: str = ""
    option_id: str | None = None
    previous_option_id: str | None = None
    total_cost: float | None = None
    delta: float = 0.0
    currency: str = "EUR"
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "decision_id": self.decision_id,
            "option_id": self.option_id,
            "previous_option_id": self.previous_option_id,
            "total_cost": self.total_cost,
            "delta": self.delta,
            "currency": self.currency,
            "warnings": list(self.warnings),
        }


def _travellers(plan: dict[str, Any]) -> int:
    raw = plan.get("travelers") or plan.get("travellers") or ""
    if isinstance(raw, int):
        return max(1, raw)
    numbers = [int(n) for n in re.findall(r"\d+", str(raw))]
    return max(1, sum(numbers)) if numbers else 1


def _to_number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    text = re.sub(r"[^\d.]", "", str(value or ""))
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _stop_name(option: Option, from_place: str, to_place: str) -> str:
    prefix = _STOP_PREFIX.get(option.mode, "Transfer")
    if from_place and to_place:
        return f"{prefix}: {from_place} to {to_place}"
    return option.label or prefix


def _minutes(text: Any) -> int | None:
    match = re.match(r"^\s*(\d{1,2}):(\d{2})", str(text or ""))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _clock(minutes: int) -> str:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _matches_scope(stop: dict[str, Any], decision: Decision) -> bool:
    from tripplanner.web.transport import _intercity_transfer_mode, _transport_route_endpoints

    name, kind = str(stop.get("name") or ""), str(stop.get("kind") or "")
    if not _intercity_transfer_mode(name, kind):
        return False
    endpoints = _transport_route_endpoints(name)
    if not endpoints:
        return True
    origin, destination = (part.strip().lower() for part in endpoints)
    scope_from = (decision.scope.from_place or "").strip().lower()
    scope_to = (decision.scope.to_place or "").strip().lower()
    if not scope_from or not scope_to:
        return True
    return scope_from in origin or origin in scope_from or (
        scope_to in destination or destination in scope_to
    )


def _locate_stop(
    plan: dict[str, Any], decision: Decision
) -> tuple[list[dict[str, Any]], int] | None:
    """The transfer this decision is about, or nothing if the plan moved on."""
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return None
    wanted_day = decision.scope.day
    for index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        day_number = entry.get("day") if isinstance(entry.get("day"), int) else index + 1
        if wanted_day and day_number != wanted_day:
            continue
        stops = entry.get("stops")
        if not isinstance(stops, list):
            continue
        for position, stop in enumerate(stops):
            if isinstance(stop, dict) and _matches_scope(stop, decision):
                return stops, position
    return None


def _write_stop(stop: dict[str, Any], option: Option, decision: Decision) -> None:
    stop["name"] = _stop_name(option, decision.scope.from_place, decision.scope.to_place)
    stop["kind"] = _STOP_KIND.get(option.mode, "transport")
    duration = option.duration_min or option.door_to_door_min
    if duration:
        stop["duration_min"] = int(duration)
    stop["decision_id"] = decision.id
    for key in _PRICE_KEYS:
        stop.pop(key, None)
    if option.price is not None:
        stop["price"] = option.price.amount
        stop["currency"] = option.price.currency


def _shift_following(stops: list[dict[str, Any]], position: int, delta_min: int) -> None:
    if not delta_min:
        return
    for stop in stops[position + 1 :]:
        if not isinstance(stop, dict):
            continue
        start = _minutes(stop.get("time"))
        if start is None:
            continue
        stop["time"] = _clock(start + delta_min)


def _guard_warnings(plan: dict[str, Any]) -> list[str]:
    from tripplanner.tools import trip_guard

    try:
        violations = trip_guard.validate_plan(plan)
    except Exception:  # a guard failure must not block a traveller's own choice
        return []
    return [v.message for v in violations if getattr(v, "message", "")]


def _settle_cost(
    plan: dict[str, Any], previous: Option | None, chosen: Option, travellers: int
) -> tuple[float | None, float, list[str]]:
    total = _to_number(plan.get("total_cost"))
    before = party_total(previous, travellers) if previous else None
    after = party_total(chosen, travellers)
    warnings: list[str] = []

    if after is None or before is None:
        unpriced = chosen if after is None else previous
        label = unpriced.label if unpriced else "this option"
        warnings.append(
            f"No fare source covers {label}, so the trip total is unchanged."
        )
        return total, 0.0, warnings

    delta = round(after - before, 2)
    if total is not None:
        total = round(total + delta, 2)
        plan["total_cost"] = total
    return total, delta, warnings


def _update_baseline(
    plan: dict[str, Any], before: float | None, total: float | None, currency: str
) -> None:
    if total is None:
        return
    baseline = plan.get("cost_baseline")
    if not isinstance(baseline, dict) or not isinstance(baseline.get("first"), int | float):
        # `first` is what the agent's own plan cost, captured the moment the
        # traveller first departs from it. It never moves again.
        baseline = {"first": before if before is not None else total, "currency": currency}
    baseline["current"] = total
    baseline["saved"] = round(float(baseline["first"]) - total, 2)
    baseline["currency"] = currency
    plan["cost_baseline"] = baseline


def _effect(total: float | None, delta: float, currency: str) -> Effect:
    return Effect(total_cost=total or 0.0, delta=delta, currency=currency)


def _apply(plan: dict[str, Any], decision: Decision, chosen: Option) -> ApplyResult:
    travellers = _travellers(plan)
    currency = (chosen.price.currency if chosen.price else None) or str(
        plan.get("currency") or "EUR"
    )
    previous = decision.option(decision.active_option_id)
    before_total = _to_number(plan.get("total_cost"))

    located = _locate_stop(plan, decision)
    warnings: list[str] = []
    if located is None:
        warnings.append(
            "This leg is no longer in the itinerary, so only the decision was updated."
        )
    else:
        stops, position = located
        stop = stops[position]
        before_min = int(stop.get("duration_min") or 0)
        _write_stop(stop, chosen, decision)
        after_min = int(stop.get("duration_min") or 0)
        _shift_following(stops, position, after_min - before_min)

    total, delta, cost_warnings = _settle_cost(plan, previous, chosen, travellers)
    warnings.extend(cost_warnings)
    _update_baseline(plan, before_total, total, currency)
    warnings.extend(_guard_warnings(plan))

    effect = _effect(total, delta, currency)
    if chosen.id == decision.chosen_option_id:
        updated = decision.model_copy(
            update={"override": None, "state": DecisionState.AGENT, "effect": effect}
        )
        message = f"Restored {chosen.label}."
    else:
        updated = decision.model_copy(
            update={
                "override": OverrideRecord(
                    option_id=chosen.id,
                    at=datetime.now(UTC),
                    previous_option_id=decision.active_option_id,
                    effect=effect,
                    warnings=list(warnings),
                ),
                "state": DecisionState.OVERRULED,
                "effect": effect,
            }
        )
        message = f"Switched to {chosen.label}."
    upsert_decision(plan, updated, preserve_override=False)

    if delta:
        direction = "more" if delta > 0 else "less"
        message += f" {money(abs(delta), currency)} {direction}."

    return ApplyResult(
        ok=True,
        message=message,
        decision_id=decision.id,
        option_id=chosen.id,
        previous_option_id=previous.id if previous else None,
        total_cost=total,
        delta=delta,
        currency=currency,
        warnings=warnings,
    )


def apply_override(plan: dict[str, Any], decision_id: str, option_id: str) -> ApplyResult:
    """Swap the plan onto the option the traveller picked."""
    decision = find_decision(plan, decision_id)
    if decision is None:
        return ApplyResult(ok=False, message="That comparison is no longer on this trip.")
    chosen = decision.option(option_id)
    if chosen is None:
        return ApplyResult(
            ok=False,
            message="That option is not one of the ways we compared.",
            decision_id=decision_id,
        )
    if chosen.id == decision.active_option_id:
        currency = chosen.price.currency if chosen.price else str(plan.get("currency") or "EUR")
        return ApplyResult(
            ok=True,
            message=f"{chosen.label} was already the plan.",
            decision_id=decision.id,
            option_id=chosen.id,
            previous_option_id=chosen.id,
            total_cost=_to_number(plan.get("total_cost")),
            currency=currency,
        )
    return _apply(plan, decision, chosen)


def restore(plan: dict[str, Any], decision_id: str) -> ApplyResult:
    """Undo an overrule and put the agent's own choice back."""
    decision = find_decision(plan, decision_id)
    if decision is None:
        return ApplyResult(ok=False, message="That comparison is no longer on this trip.")
    if decision.override is None:
        return ApplyResult(
            ok=True,
            message="Nothing to undo — this is still the plan we made.",
            decision_id=decision.id,
            option_id=decision.chosen_option_id,
        )
    original = decision.option(decision.chosen_option_id)
    if original is None:
        return ApplyResult(
            ok=False,
            message="The original option is no longer available to restore.",
            decision_id=decision.id,
        )
    return _apply(plan, decision, original)
