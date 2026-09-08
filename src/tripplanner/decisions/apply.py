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
    DecisionKind,
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


def _lodging_item(option: Option, decision: Decision) -> dict[str, Any]:
    lodging = option.lodging
    item: dict[str, Any] = {
        "name": option.label,
        "hotel_name": option.label,
        "decision_id": decision.id,
    }
    if option.price is not None:
        item.update({"total": option.price.amount, "currency": option.price.currency})
        item["price_composition"] = {
            key: value
            for key, value in (
                ("taxes", option.price.taxes),
                ("fees", option.price.fees),
                ("due_at_property", option.price.due_at_property),
                ("all_in", option.price.all_in),
                ("mandatory_costs_complete", option.price.mandatory_costs_complete),
                ("excluded", [dict(component) for component in option.price.excluded]),
            )
            if value not in (None, [])
        }
    if lodging is not None:
        for key, value in (
            ("checkin", lodging.checkin),
            ("checkout", lodging.checkout),
            ("room_name", lodging.room_name),
            ("board_name", lodging.board_name),
            ("refundable", lodging.refundable),
            ("cancellation_summary", lodging.cancellation_summary),
            ("address", lodging.address),
            ("rating", lodging.rating),
        ):
            if value not in (None, ""):
                item[key] = value
        if lodging.provider_ref:
            item["provider_ref"] = dict(lodging.provider_ref)
        if lodging.search_context:
            item["search_context"] = dict(lodging.search_context)
    source = option.source
    item["source"] = source.model_dump(mode="json", exclude_none=True)
    return item


def _apply_lodging_shape(
    plan: dict[str, Any], decision: Decision, previous: Option | None, chosen: Option
) -> list[str]:
    previous_name = (previous.label if previous else "").strip().lower()
    replacement = _lodging_item(chosen, decision)
    selected = plan.get("selected_hotels")
    replaced = False
    if isinstance(selected, list):
        for index, item in enumerate(selected):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("hotel_name") or "").strip().lower()
            if previous_name and name == previous_name:
                selected[index] = replacement
                replaced = True
                break
    else:
        selected = []
        plan["selected_hotels"] = selected
    if not replaced:
        selected.append(replacement)

    anchors = 0
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict) or not isinstance(day.get("stops"), list):
            continue
        for stop in day["stops"]:
            if not isinstance(stop, dict) or str(stop.get("kind") or "").lower() != "hotel":
                continue
            name = str(stop.get("name") or "").strip().lower()
            if previous_name and name != previous_name:
                continue
            stop.update(
                {
                    key: value
                    for key, value in replacement.items()
                    if key not in {"provider_ref", "source"}
                }
            )
            stop["kind"] = "hotel"
            anchors += 1
    return (
        []
        if anchors
        else ["The stay was updated, but its itinerary anchor was no longer present."]
    )


def _flight_item(option: Option, decision: Decision) -> dict[str, Any]:
    flight = option.flight
    item: dict[str, Any] = {
        "name": option.label,
        "airline": option.label,
        "decision_id": decision.id,
    }
    if option.price is not None:
        item.update({"price": option.price.amount, "currency": option.price.currency})
        item["price_composition"] = {
            key: value
            for key, value in (
                ("taxes", option.price.taxes),
                ("fees", option.price.fees),
                ("all_in", option.price.all_in),
                ("mandatory_costs_complete", option.price.mandatory_costs_complete),
                ("excluded", [dict(component) for component in option.price.excluded]),
            )
            if value not in (None, [])
        }
    if flight is not None:
        item.update(
            {
                "from": flight.origin,
                "to": flight.destination,
                "departure_date": flight.departure_date,
                "return_date": flight.return_date,
                "travel_class": flight.cabin_class,
                "segments": [dict(segment) for segment in flight.segments],
                "stops": flight.stops,
                "provider_ref": dict(flight.provider_ref),
            }
        )
        for key, value in (
            ("seats_remaining", flight.seats_remaining),
            ("baggage", flight.baggage),
            ("terms", flight.terms),
        ):
            if value is not None:
                item[key] = value
    item["source"] = option.source.model_dump(mode="json", exclude_none=True)
    return item


def _apply_flight_shape(
    plan: dict[str, Any], decision: Decision, previous: Option | None, chosen: Option
) -> list[str]:
    previous_ref = previous.flight.provider_ref if previous and previous.flight else {}
    previous_offer_id = str(previous_ref.get("offer_id") or "")
    replacement = _flight_item(chosen, decision)
    selected = plan.get("selected_flights")
    if not isinstance(selected, list):
        selected = []
        plan["selected_flights"] = selected
    for index, item in enumerate(selected):
        if not isinstance(item, dict):
            continue
        provider_ref = item.get("provider_ref")
        offer_id = (
            str(provider_ref.get("offer_id") or "")
            if isinstance(provider_ref, dict)
            else str(item.get("offer_id") or "")
        )
        if previous_offer_id and offer_id == previous_offer_id:
            selected[index] = replacement
            return []
    selected.append(replacement)
    return ["The prior flight offer was no longer selected, so this flight was added."]


def _settle_cost(
    plan: dict[str, Any],
    previous: Option | None,
    chosen: Option,
    travellers: int,
    *,
    lodging: bool = False,
) -> tuple[float | None, float, list[str]]:
    total = _to_number(plan.get("total_cost"))
    before = party_total(previous, travellers) if previous else None
    after = party_total(chosen, travellers)
    warnings: list[str] = []

    if after is None or before is None:
        unpriced = chosen if after is None else previous
        label = unpriced.label if unpriced else "this option"
        evidence = "verified price" if lodging else "fare source"
        warnings.append(
            f"No {evidence} covers {label}, so the trip total is unchanged."
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

    warnings: list[str] = []
    if decision.kind == DecisionKind.LODGING:
        warnings.extend(_apply_lodging_shape(plan, decision, previous, chosen))
    elif decision.kind == DecisionKind.FLIGHT:
        warnings.extend(_apply_flight_shape(plan, decision, previous, chosen))
    else:
        located = _locate_stop(plan, decision)
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

    total, delta, cost_warnings = _settle_cost(
        plan,
        previous,
        chosen,
        travellers,
        lodging=decision.kind == DecisionKind.LODGING,
    )
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
