"""Explicit provider-backed rechecks for finalized, unbooked trip prices."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tripplanner.decisions.provenance import make_check, record_check
from tripplanner.decisions.trip_cost import plan_price_rechecks
from tripplanner.providers.models import HotelSearchQuery
from tripplanner.providers.registry import get_flight_providers, get_hotel_providers

MAX_RECHECKS = 12


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _provider_name(provider: object) -> str:
    return str(getattr(provider, "name", provider.__class__.__name__)).strip()


def _provider(providers: list[object], name: str) -> object | None:
    target = name.strip().casefold()
    return next(
        (candidate for candidate in providers if _provider_name(candidate).casefold() == target),
        None,
    )


def _selected_for_kind(plan: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    bucket = "selected_flights" if kind == "flights" else "selected_hotels"
    return [item for item in plan.get(bucket) or [] if isinstance(item, dict)]


def _source_provider(item: dict[str, Any]) -> str:
    source = item.get("source")
    return str(source.get("provider") or "") if isinstance(source, dict) else ""


def _flight_result(item: dict[str, Any], provider: object) -> dict[str, Any]:
    reference = item.get("provider_ref")
    offer_id = str(reference.get("offer_id") or "") if isinstance(reference, dict) else ""
    if not offer_id:
        return {"status": "unavailable", "reason": "selected flight has no provider offer ID"}
    offer = provider.verify_flight(offer_id)  # type: ignore[attr-defined]
    previous = _number(item.get("price") or item.get("total"))
    current = float(offer.total.amount)
    return {
        "status": "live",
        "label": str(item.get("airline") or item.get("name") or "Selected flight"),
        "previous_total": previous,
        "current_total": current,
        "delta": round(current - previous, 2) if previous is not None else None,
        "currency": offer.total.currency,
        "checked_at": offer.quoted_at.isoformat(),
        "expires_at": offer.expires_at.isoformat() if offer.expires_at else None,
    }


def _hotel_query(item: dict[str, Any], plan: dict[str, Any]) -> HotelSearchQuery | None:
    context = item.get("search_context")
    if not isinstance(context, dict):
        return None
    required = ("adults_per_room", "rooms", "guest_nationality")
    if any(context.get(key) in (None, "") for key in required):
        return None
    return HotelSearchQuery(
        destination=str(context.get("destination") or plan.get("destination") or ""),
        checkin=str(item.get("checkin") or ""),
        checkout=str(item.get("checkout") or ""),
        adults_per_room=int(context["adults_per_room"]),
        rooms=int(context["rooms"]),
        children_ages=[int(age) for age in context.get("children_ages") or []],
        currency=str(item.get("currency") or plan.get("currency") or "INR"),
        guest_nationality=str(context["guest_nationality"]),
        refundable_only=bool(context.get("refundable_only", False)),
        max_results=20,
    )


def _same_hotel_offer(item: dict[str, Any], offer: Any) -> bool:
    reference = item.get("provider_ref")
    selected_hotel_id = (
        str(reference.get("hotel_id") or "").strip().casefold()
        if isinstance(reference, dict)
        else ""
    )
    offer_hotel_id = str(offer.provider_ref.get("hotel_id") or "").strip().casefold()
    same_property = (
        bool(selected_hotel_id and offer_hotel_id and selected_hotel_id == offer_hotel_id)
        or str(item.get("name") or item.get("hotel_name") or "").strip().casefold()
        == str(offer.hotel_name or "").strip().casefold()
    )
    return (
        same_property
        and str(item.get("room_name") or "").strip().casefold()
        == str(offer.room_name or "").strip().casefold()
        and str(item.get("board_name") or "").strip().casefold()
        == str(offer.board_name or "").strip().casefold()
        and item.get("refundable") == offer.refundable
    )


def _hotel_result(item: dict[str, Any], plan: dict[str, Any], provider: object) -> dict[str, Any]:
    query = _hotel_query(item, plan)
    if query is None:
        return {
            "status": "unavailable",
            "reason": "selected stay lacks its original occupancy and nationality context",
        }
    offers = provider.search_hotels(query)  # type: ignore[attr-defined]
    offer = next((candidate for candidate in offers if _same_hotel_offer(item, candidate)), None)
    if offer is None:
        return {"status": "unavailable", "reason": "the exact selected room was not returned"}
    previous = _number(item.get("total") or item.get("price"))
    current = float(offer.total.amount)
    return {
        "status": "live",
        "label": str(item.get("name") or item.get("hotel_name") or "Selected stay"),
        "previous_total": previous,
        "current_total": current,
        "delta": round(current - previous, 2) if previous is not None else None,
        "currency": offer.total.currency,
        "checked_at": offer.quoted_at.isoformat(),
        "expires_at": offer.expires_at.isoformat() if offer.expires_at else None,
    }


def recheck_prices(plan: dict[str, Any]) -> dict[str, Any]:
    """Recheck stale exact selections and persist observations, never selections."""
    tasks = plan_price_rechecks(plan)
    flight_providers = list(get_flight_providers())
    hotel_providers = list(get_hotel_providers())
    results: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()

    for task in tasks:
        kind = task["kind"]
        provider_name = task["provider"]
        providers = flight_providers if kind == "flights" else hotel_providers
        provider = _provider(providers, provider_name)
        items = [
            item
            for item in _selected_for_kind(plan, kind)
            if _source_provider(item).casefold() == provider_name.casefold()
        ]
        if provider is None:
            results.append(
                {
                    **task,
                    "status": "unavailable",
                    "reason": "the recorded provider is not currently configured",
                    "observed_at": now,
                }
            )
            continue
        if not items:
            results.append(
                {
                    **task,
                    "status": "unavailable",
                    "reason": "no matching selected item retains this provider identity",
                    "observed_at": now,
                }
            )
            continue
        for item in items:
            try:
                result = (
                    _flight_result(item, provider)
                    if kind == "flights"
                    else _hotel_result(item, plan, provider)
                )
            except Exception:
                result = {
                    "status": "provider_error",
                    "reason": "the provider could not recheck this selection just now",
                }
            observation = {**task, **result, "observed_at": now}
            results.append(observation)
            if result.get("status") == "live":
                record_check(plan, make_check(kind, provider_name))

    history = [row for row in plan.get("price_recheck_results") or [] if isinstance(row, dict)]
    plan["price_recheck_results"] = [*history, *results][-MAX_RECHECKS:]
    return {"plan": plan, "results": results, "rechecked": len(results)}
