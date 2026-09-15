"""Booking research, reversible intent and externally reported purchases."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from tripplanner.decisions.store import list_decisions


class Cap(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    amount: float = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class ActualBooking(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    product: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=120)
    amount: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    start_date: str = Field(default="", max_length=10)
    end_date: str = Field(default="", max_length=10)
    time: str = Field(default="", pattern=r"^$|^([01]\d|2[0-3]):[0-5]\d$")
    reference: str = Field(default="", max_length=180)
    notes: str = Field(default="", max_length=500)
    url: str = Field(default="", max_length=2048)


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def safe_url(value: Any) -> str:
    text = str(value or "").strip()
    try:
        parts = urlsplit(text)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return ""
        if any(
            key.lower() in {"token", "api_key", "apikey", "key", "secret"}
            for key in parse_qs(parts.query)
        ):
            return ""
        return text
    except ValueError:
        return ""


def caps_for(plan: dict) -> dict[str, dict]:
    raw = plan.get("category_caps") or {}
    if not isinstance(raw, dict) or set(raw) - {"flights", "hotels", "tickets", "transport"}:
        raise ValueError("Category caps must use flights, hotels, tickets or transport.")
    return {
        key: Cap.model_validate(value).model_dump()
        for key, value in raw.items()
        if key in {"flights", "hotels", "tickets", "transport"}
    }


def _facts(raw: dict, plan: dict) -> dict:
    intent = raw.get("booking_intent_details") or {}
    if intent:
        raw = {
            **raw,
            "name": intent["product"],
            "price": intent.get("amount"),
            "total": None,
            "currency": intent["currency"],
            "time": intent.get("time") or raw.get("time"),
            "source": {"provider": intent["provider"]},
            "booking_url": intent.get("url") or "",
            "price_composition": {},
            "quoted_at": "",
            "expires_at": "",
        }
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    price = raw.get("price") if isinstance(raw.get("price"), dict) else {}
    if not price and isinstance(raw.get("total"), dict):
        price = raw["total"]
    composition = raw.get("price_composition") or price
    amount = next(
        (
            number(raw.get(k))
            for k in ("total", "price", "amount", "cost")
            if number(raw.get(k)) is not None
        ),
        number(price.get("amount")),
    )
    url = safe_url(
        source.get("url")
        or raw.get("booking_url")
        or raw.get("provider_url")
        or raw.get("url")
        or raw.get("website")
    )
    context = raw.get("search_context") or {}
    context_warning = ""
    if raw.get("checkin") or raw.get("departure_date"):
        counts = re.findall(r"\d+", str(plan.get("travelers") or ""))
        party = sum(map(int, counts)) if counts else None
        occupancy = (
            (
                (number(context.get("adults_per_room")) or 0) * (number(context.get("rooms")) or 0)
                + len(context.get("children_ages") or [])
            )
            if raw.get("checkin")
            else sum(number(context.get(k)) or 0 for k in ("adults", "children", "infants"))
        )
        if not party or occupancy != party:
            context_warning = "Quoted party/occupancy is missing or differs from the trip. Recheck for the correct travelers."
        elif raw.get("departure_date") and not raw.get("baggage"):
            context_warning = (
                "Baggage allowances and any required baggage charges need confirmation."
            )
    return {
        "name": str(
            raw.get("name")
            or raw.get("title")
            or raw.get("hotel_name")
            or raw.get("airline")
            or "Unspecified item"
        ),
        "amount": amount,
        "currency": str(
            raw.get("currency") or price.get("currency") or plan.get("currency") or "INR"
        ),
        "start_date": str(raw.get("checkin") or raw.get("departure_date") or raw.get("date") or ""),
        "end_date": str(raw.get("checkout") or raw.get("return_date") or ""),
        "time": str(raw.get("time") or ""),
        "provider": str(source.get("provider") or raw.get("provider") or ""),
        "checked_at": str(source.get("checked_at") or raw.get("quoted_at") or ""),
        "expires_at": str(source.get("expires_at") or raw.get("expires_at") or ""),
        "complete_cost": composition.get("mandatory_costs_complete") is True
        or composition.get("all_in") is True,
        "url": url,
        "handoff": "product_page" if url else "copy_details",
        "context_warning": context_warning,
        "details": {
            k: deepcopy(raw[k])
            for k in (
                "from",
                "to",
                "travel_class",
                "segments",
                "room_name",
                "board_name",
                "refundable",
                "cancellation_summary",
                "baggage",
                "terms",
                "price_composition",
                "search_context",
                "booking_variant",
            )
            if k in raw
        },
    }


def _option(option, decision, plan: dict) -> dict:
    from tripplanner.decisions.apply import _flight_item, _lodging_item

    raw = (
        _lodging_item(option, decision)
        if decision.kind == "lodging"
        else _flight_item(option, decision)
    )
    facts = _facts(raw, plan)
    return {
        "id": option.id,
        **facts,
        "reason": option.rejected_because or "",
        "recommended": option.id == decision.chosen_option_id,
    }


def units(plan: dict) -> list[dict]:
    """Group selections and repeated itinerary anchors into purchase units."""
    decisions = [d for d in list_decisions(plan) if d.kind in {"flight", "lodging"}]
    rows: list[dict] = []
    represented: set[str] = set()
    for bucket, category in (
        ("selected_flights", "flights"),
        ("selected_hotels", "hotels"),
        ("selected_activities", "tickets"),
    ):
        for index, raw in enumerate(plan.get(bucket) or []):
            if not isinstance(raw, dict):
                continue
            name = str(
                raw.get("name")
                or raw.get("title")
                or raw.get("hotel_name")
                or raw.get("airline")
                or ""
            )
            ref = raw.get("provider_ref") or {}
            decision = next((d for d in decisions if d.id == raw.get("decision_id")), None)
            if decision is None:
                decision = next(
                    (
                        d
                        for d in decisions
                        if d.id not in represented
                        and (
                            (
                                category == "hotels"
                                and d.kind == "lodging"
                                and any(
                                    o.label.casefold() == name.casefold()
                                    and o.lodging
                                    and (
                                        not raw.get("checkin")
                                        or raw["checkin"] == o.lodging.checkin
                                    )
                                    for o in d.options
                                )
                            )
                            or (
                                category == "flights"
                                and d.kind == "flight"
                                and ref.get("offer_id")
                                and any(
                                    o.flight
                                    and o.flight.provider_ref.get("offer_id") == ref["offer_id"]
                                    for o in d.options
                                )
                            )
                        )
                    ),
                    None,
                )
            identifier = str(
                raw.get("booking_item_id")
                or (
                    decision.id
                    if decision
                    else f"{category}:{digest([index, name, raw.get('checkin'), raw.get('departure_date')])[:16]}"
                )
            )
            row = {
                "id": identifier,
                "category": category,
                **_facts(raw, plan),
                "decision_id": decision.id if decision else "",
                "option_id": decision.active_option_id if decision else "",
                "alternatives": [_option(o, decision, plan) for o in decision.options]
                if decision
                else [],
                "_targets": [(bucket, index)],
                "booked": bool(raw.get("booked")),
                "selected": True,
            }
            if decision:
                represented.add(decision.id)
            rows.append(row)
    for decision in decisions:
        if decision.id in represented or not decision.chosen:
            continue
        rows.append(
            {
                "category": "hotels" if decision.kind == "lodging" else "flights",
                **_option(decision.chosen, decision, plan),
                "id": decision.id,
                "decision_id": decision.id,
                "option_id": decision.active_option_id,
                "alternatives": [_option(o, decision, plan) for o in decision.options],
                "_targets": [],
                "booked": False,
                "selected": False,
            }
        )
    for day_index, day in enumerate(plan.get("day_wise_itinerary") or []):
        if not isinstance(day, dict):
            continue
        for index, stop in enumerate(day.get("stops") or []):
            if not isinstance(stop, dict):
                continue
            kind = str(stop.get("kind") or "").lower()
            if kind in {"meal", "restaurant", "walk", "walking", "note"}:
                continue
            category = {"hotel": "hotels", "flight": "flights", "transport": "transport"}.get(
                kind, "tickets"
            )
            target = ("day_wise_itinerary", day_index, "stops", index)
            existing = next(
                (
                    row
                    for row in rows
                    if (
                        stop.get("booking_item_id") == row["id"]
                        or stop.get("decision_id")
                        and stop["decision_id"] == row.get("decision_id")
                        or category == "hotels"
                        and row["category"] == "hotels"
                        and row["name"].casefold() == str(stop.get("name") or "").casefold()
                        and (
                            not row["start_date"] or str(day.get("date") or "") >= row["start_date"]
                        )
                        and (not row["end_date"] or str(day.get("date") or "") <= row["end_date"])
                        or category == "tickets"
                        and row["category"] == "tickets"
                        and len(row["_targets"]) == 1
                        and row["_targets"][0][0] == "selected_activities"
                        and row["name"].casefold() == str(stop.get("name") or "").casefold()
                        and (not row["start_date"] or day.get("date") == row["start_date"])
                    )
                ),
                None,
            )
            if existing:
                existing["_targets"].append(target)
                if category == "tickets":
                    existing["start_date"] = existing["start_date"] or str(day.get("date") or "")
                    existing["time"] = existing["time"] or str(stop.get("time") or "")
                continue
            # Selected flight bundles already represent the journey's purchase;
            # itinerary flight anchors are scheduling views of those purchases.
            flight_rows = [r for r in rows if r["category"] == "flights" and r["selected"]]
            matching_flights = [
                r for r in flight_rows if day.get("date") in {r["start_date"], r["end_date"]}
            ]
            if category == "flights" and len(matching_flights) == 1:
                matching_flights[0]["_targets"].append(target)
                continue
            identifier = str(
                stop.get("booking_item_id")
                or f"stop:{digest([day.get('day', day_index + 1), index, stop.get('name')])[:16]}"
            )
            rows.append(
                {
                    "id": identifier,
                    "category": category,
                    **_facts({**stop, "date": day.get("date") or ""}, plan),
                    "decision_id": "",
                    "option_id": "",
                    "alternatives": [],
                    "_targets": [target],
                    "booked": bool(stop.get("booked")),
                    "selected": True,
                    "day": day.get("day", day_index + 1),
                }
            )
    records = (plan.get("booking_intent") or {}).get("records") or {}
    for row in rows:
        row["disposition"] = (records.get(row["id"]) or {}).get("disposition", "needs_booking")
    return rows


def fingerprint(plan: dict, row: dict) -> str:
    return digest(
        {
            k: row.get(k)
            for k in (
                "category",
                "name",
                "amount",
                "currency",
                "start_date",
                "end_date",
                "time",
                "option_id",
                "details",
            )
        }
        | {
            "party": plan.get("travelers"),
            "trip_dates": [plan.get("departure_date"), plan.get("return_date")],
            "schedule": [
                [
                    d.get("date"),
                    [
                        [s.get("name"), s.get("time"), s.get("duration_min")]
                        for s in d.get("stops") or []
                        if isinstance(s, dict)
                    ],
                ]
                for d in plan.get("day_wise_itinerary") or []
                if isinstance(d, dict)
            ],
        }
    )


def evidence(row: dict) -> str:
    if row.get("amount") is None or not row.get("checked_at"):
        return "unverified"
    try:
        expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return "checked" if expiry > datetime.now(UTC) else "stale"
    except (ValueError, TypeError, KeyError):
        return "recheck_required"


def budget_summary(plan: dict, rows: list[dict] | None = None) -> dict:
    rows = units(plan) if rows is None else rows
    result = {}
    for category, cap in caps_for(plan).items():
        selected = [
            r
            for r in rows
            if r["category"] == category
            and r.get("selected", True)
            and r.get("disposition") != "not_needed"
        ]
        comparable = [
            r for r in selected if r["amount"] is not None and r["currency"] == cap["currency"]
        ]
        total = round(sum(r["amount"] for r in comparable), 2)
        unknown = len(selected) - len(comparable)
        incomplete = sum(not r["complete_cost"] and not r.get("booked") for r in selected)
        status = (
            "over_cap"
            if total > cap["amount"]
            else (
                "unverified"
                if unknown
                or incomplete
                or not selected
                or any(
                    (evidence(r) != "checked" or r.get("context_warning")) and not r.get("booked")
                    for r in selected
                )
                else "within_cap"
            )
        )
        result[category] = {
            **cap,
            "known_total": total,
            "unknown_items": unknown,
            "incomplete_items": incomplete,
            "status": status,
        }
    return result


def build_booking_view(plan: dict | None, *, private: bool = True) -> dict:
    from tripplanner.decisions.booking_defaults import research_defaults

    plan = plan or {}
    records = (plan.get("booking_intent") or {}).get("records") or {}
    rows = units(plan)
    for row in rows:
        record = records.get(row["id"]) or {}
        lock = record.get("lock")
        actual = record.get("actual")
        row["disposition"] = record.get("disposition", "needs_booking")
        row["intent_state"] = (
            ("locked" if lock["fingerprint"] == fingerprint(plan, row) else "needs_review")
            if lock
            else "draft"
        )
        row["evidence"] = evidence(row)
        row["locked_at"] = lock.get("at") if lock else None
        row["intended"] = lock.get("snapshot") if lock else record.get("intended")
        row["actual"] = {
            k: v for k, v in (actual or {}).items() if private or k not in {"reference", "notes"}
        } or None
        row["booked"] = bool(actual) or row["booked"]
        row["research"] = record.get("research")
        row["warnings"] = record.get("warnings", [])
        row.pop("_targets", None)
    return {
        "trip_id": plan.get("trip_id") or "",
        "updated_at": plan.get("updated_at") or "",
        "destination": plan.get("destination") or "",
        "travelers": plan.get("travelers") or "",
        "research_defaults": research_defaults(plan) if private else None,
        "rows": rows,
        "budgets": budget_summary(plan, rows),
        "category_caps": caps_for(plan),
        "schedule": [
            {
                "date": day.get("date", ""),
                "stops": [
                    {
                        "name": stop.get("name", ""),
                        "time": stop.get("time", ""),
                        "booked": bool(stop.get("booked")),
                    }
                    for stop in day.get("stops") or []
                    if isinstance(stop, dict)
                ],
            }
            for day in plan.get("day_wise_itinerary") or []
            if isinstance(day, dict)
        ],
        "coverage": "LiteAPI flight/hotel research. Other items use saved evidence or your own research.",
        "booked_count": sum(r["booked"] for r in rows),
        "locked_count": sum(r["intent_state"] == "locked" for r in rows),
    }


def _target(plan: dict, path: tuple) -> dict:
    value = plan
    for key in path:
        value = value[key]
    return value


def _assign_identity(plan: dict, row: dict) -> None:
    for path in row["_targets"]:
        _target(plan, path)["booking_item_id"] = row["id"]
        if row["decision_id"]:
            _target(plan, path)["decision_id"] = row["decision_id"]


def _materialize(plan: dict, row: dict, option_id: str) -> None:
    from tripplanner.decisions.apply import _flight_item, _lodging_item
    from tripplanner.decisions.store import find_decision

    if row["_targets"]:
        return
    decision = find_decision(plan, row["decision_id"])
    option = decision.option(option_id) if decision else None
    if not decision or not option:
        raise ValueError("The intended option is no longer saved.")
    bucket = "selected_hotels" if row["category"] == "hotels" else "selected_flights"
    item = (
        _lodging_item(option, decision)
        if bucket == "selected_hotels"
        else _flight_item(option, decision)
    )
    item["booking_item_id"] = row["id"]
    plan.setdefault(bucket, []).append(item)


def _date(value: str) -> None:
    if value:
        datetime.strptime(value, "%Y-%m-%d")


def prepare_change(plan: dict, command: dict) -> tuple[dict, list[str]]:
    """Produce an isolated candidate; callers commit only after a bound preview."""
    candidate = deepcopy(plan)
    action = command["action"]
    warnings: list[str] = []
    if action == "caps":
        candidate["category_caps"] = caps_for({"category_caps": command.get("caps", {})})
        return candidate, warnings
    row = next((r for r in units(candidate) if r["id"] == command.get("item_id")), None)
    if not row:
        raise ValueError("This item no longer exists. Reload the trip.")
    _assign_identity(candidate, row)
    records = candidate.setdefault("booking_intent", {}).setdefault("records", {})
    record = records.setdefault(row["id"], {})
    if action in {"choose", "lock"}:
        choice = next((o for o in row["alternatives"] if o["id"] == command.get("option_id")), row)
        if (
            plan.get("departure_date")
            and choice["start_date"]
            and choice["start_date"] < plan["departure_date"]
            or plan.get("return_date")
            and (choice["end_date"] or choice["start_date"]) > plan["return_date"]
        ):
            raise ValueError(
                "This choice falls outside the trip dates. Adjust the itinerary dates first."
            )
    if action == "choose":
        if record.get("actual") or row["booked"]:
            raise ValueError("This item is already booked. Edit the reported booking instead.")
        from tripplanner.decisions.apply import apply_override

        if not row["decision_id"]:
            raise ValueError("No sourced alternatives are saved for this item.")
        selected = next(
            (o for o in row["alternatives"] if o["id"] == command.get("option_id")), None
        )
        if not selected:
            raise ValueError("That saved alternative is no longer available.")
        result = apply_override(candidate, row["decision_id"], selected["id"])
        if not result.ok:
            raise ValueError(result.message)
        warnings.extend(result.warnings)
        if selected["id"] == row["option_id"] and row["_targets"]:
            from tripplanner.decisions.apply import _apply_flight_shape, _apply_lodging_shape
            from tripplanner.decisions.store import find_decision

            decision = find_decision(candidate, row["decision_id"])
            shape = _apply_lodging_shape if row["category"] == "hotels" else _apply_flight_shape
            warnings.extend(shape(candidate, decision, decision.chosen, decision.chosen))
        total = number(plan.get("total_cost"))
        if (
            total is not None
            and row["selected"]
            and row["amount"] is not None
            and selected["amount"] is not None
        ):
            candidate["total_cost"] = round(total + selected["amount"] - row["amount"], 2)
        if (
            selected["currency"] != row["currency"]
            or selected["currency"] != plan.get("currency")
            or row["amount"] is None
            or selected["amount"] is None
            or not row["selected"]
        ):
            candidate["total_cost"] = plan.get("total_cost")
            candidate["cost_total_needs_review"] = True
            warnings.append(
                "Whole-trip total needs a sourced currency conversion; the previous total is retained for reference."
            )
        if not any(r["_targets"] for r in units(candidate) if r["id"] == row["id"]):
            _materialize(candidate, row, selected["id"])
        record.pop("lock", None)
        # Propagate the existing purchase identity through the replacement.
        for new in units(candidate):
            if new["decision_id"] == row["decision_id"]:
                for path in new["_targets"]:
                    _target(candidate, path)["booking_item_id"] = row["id"]
        over = [k for k, v in budget_summary(candidate).items() if v["status"] == "over_cap"]
        if over:
            raise ValueError(
                "Selection exceeds the "
                + ", ".join(over)
                + " cap. Adjust that cap explicitly first."
            )
        warnings.append("Recheck availability before booking; no price or inventory is held.")
    elif action == "lock":
        if row["booked"] or record.get("actual"):
            raise ValueError("This item is already booked. Its original intention is retained.")
        if not row["_targets"]:
            _materialize(candidate, row, row["option_id"])
            row = next(r for r in units(candidate) if r["id"] == row["id"])
            candidate["cost_total_needs_review"] = True
        if any(v["status"] == "over_cap" for v in budget_summary(candidate).values()):
            raise ValueError(
                "A category cap is exceeded. Adjust the choices or explicitly revise the cap before locking."
            )
        snapshot = {k: v for k, v in row.items() if k != "_targets"}
        record["lock"] = {
            "at": now(),
            "fingerprint": fingerprint(candidate, row),
            "snapshot": snapshot,
        }
        warnings.append("This saves your intention only. Prices and availability are not held.")
    elif action == "unlock":
        record.pop("lock", None)
    elif action == "disposition":
        if row["booked"] or record.get("actual"):
            raise ValueError("A reported booking cannot be marked as unnecessary.")
        value = command.get("disposition")
        if value not in {"needs_booking", "pay_locally", "not_needed"}:
            raise ValueError("Choose needs booking, pay locally or no booking needed.")
        record["disposition"] = value
    elif action in {"report", "manual"}:
        actual = ActualBooking.model_validate(command.get("actual") or {}).model_dump()
        if not actual["product"].strip() or not actual["provider"].strip():
            raise ValueError("Product and provider are required.")
        _date(actual["start_date"])
        _date(actual["end_date"])
        if (
            actual["start_date"]
            and actual["end_date"]
            and actual["start_date"] > actual["end_date"]
        ):
            raise ValueError("The end date must be on or after the start date.")
        if actual["url"] and not safe_url(actual["url"]):
            raise ValueError(
                "Use a public HTTPS provider link without credentials or access tokens."
            )
        if action == "manual":
            if row["booked"] or record.get("actual"):
                raise ValueError("Edit the reported booking for an already-booked item.")
            if not row["_targets"]:
                _materialize(candidate, row, row["option_id"])
                row = next(r for r in units(candidate) if r["id"] == row["id"])
            for path in row["_targets"]:
                target = _target(candidate, path)
                if (
                    actual["start_date"]
                    and actual["start_date"] != row["start_date"]
                    or actual["end_date"]
                    and actual["end_date"] != row["end_date"]
                ):
                    raise ValueError(
                        "Adjust the itinerary dates before changing this researched intention."
                    )
                target["booking_intent_details"] = {
                    k: v for k, v in actual.items() if k != "reference"
                }
                target["booking_variant"] = actual["notes"]
                target["booking_item_id"] = row["id"]
                target["note"] = (
                    f"Intended: {actual['product']} via {actual['provider']}. {actual['notes']}".strip()
                )
                for key in (
                    "total",
                    "price",
                    "amount",
                    "cost",
                    "price_composition",
                    "quoted_at",
                    "expires_at",
                    "baggage",
                    "terms",
                    "room_name",
                    "board_name",
                    "refundable",
                    "cancellation_summary",
                ):
                    target.pop(key, None)
                target["price"] = actual["amount"]
                target["currency"] = actual["currency"]
                target["source"] = {"provider": actual["provider"]}
                if actual["time"]:
                    target["time"] = actual["time"]
            record.pop("lock", None)
            if any(v["status"] == "over_cap" for v in budget_summary(candidate).values()):
                raise ValueError(
                    "These intent details exceed a category cap. Revise that cap explicitly first."
                )
            from tripplanner.tools.trip_guard import validate_plan

            existing = {v.message for v in validate_plan(plan)}
            conflicts = [v.message for v in validate_plan(candidate) if v.message not in existing]
            if conflicts:
                raise ValueError(
                    "These intent details conflict with the itinerary: " + " ".join(conflicts)
                )
            total = number(candidate.get("total_cost"))
            if (
                total is not None
                and row["amount"] is not None
                and actual["amount"] is not None
                and row["currency"] == actual["currency"] == plan.get("currency")
            ):
                candidate["total_cost"] = round(total + actual["amount"] - row["amount"], 2)
            else:
                candidate["cost_total_needs_review"] = True
            return candidate, ["Manually entered research is unverified. No purchase was recorded."]
        for other_id, other in records.items():
            reported = other.get("actual") or {}
            if (
                other_id != row["id"]
                and actual["reference"]
                and reported.get("reference") == actual["reference"]
                and reported.get("provider", "").casefold() == actual["provider"].casefold()
            ):
                raise ValueError("This confirmation is already attached to another purchase unit.")
        record.setdefault("intended", {k: v for k, v in row.items() if k != "_targets"})
        if not row["_targets"] and row["decision_id"]:
            _materialize(candidate, row, row["option_id"])
            row = next(r for r in units(candidate) if r["decision_id"] == row["decision_id"])
        changed_dates = any(
            actual[k] and actual[k] != row[k] for k in ("start_date", "end_date", "time")
        )
        if changed_dates:
            warnings.append(
                "Actual dates/times differ from the plan. Review connected transfers and stops."
            )
        old_amount = row["amount"]
        changed_days: set[int] = set()
        targets = [(path, _target(candidate, path)) for path in row["_targets"]]
        for path, target in targets:
            if row["category"] != "flights" and str(target.get("name") or "") != actual["product"]:
                for key in (
                    "lat",
                    "lng",
                    "latitude",
                    "longitude",
                    "place_id",
                    "google_place_id",
                    "address",
                    "location",
                    "place",
                    "place_summary",
                ):
                    target.pop(key, None)
            anchor_name = (
                target.get("name")
                if path[0] == "day_wise_itinerary" and row["category"] == "flights"
                else ""
            )
            target.update(
                {
                    "booking_item_id": row["id"],
                    "booked": True,
                    "name": actual["product"],
                    "booking_status": "user_reported",
                    "source": {"provider": actual["provider"], "confidence": "user_reported"},
                }
            )
            if anchor_name:
                target["name"] = anchor_name
                target["booked_product"] = actual["product"]
                target["note"] = (
                    f"User reported booking: {actual['product']} via {actual['provider']}."
                )
            for key in (
                "price",
                "total",
                "amount",
                "cost",
                "provider_ref",
                "price_composition",
                "quoted_at",
                "expires_at",
                "booking_intent_details",
                "booking_url",
                "provider_url",
                "url",
                "website",
            ):
                target.pop(key, None)
            target["price"] = actual["amount"]
            target["currency"] = actual["currency"]
            if actual["url"]:
                target["booking_url"] = actual["url"]
            if row["category"] == "hotels":
                for key in (
                    "room_name",
                    "board_name",
                    "refundable",
                    "cancellation_summary",
                    "search_context",
                    "rating",
                ):
                    target.pop(key, None)
                target["hotel_name"] = actual["product"]
                if actual["start_date"]:
                    target["checkin"] = actual["start_date"]
                if actual["end_date"]:
                    target["checkout"] = actual["end_date"]
            elif row["category"] == "flights":
                for key in ("segments", "baggage", "terms", "seats_remaining", "stops"):
                    target.pop(key, None)
                target["airline"] = actual["product"]
                if actual["start_date"]:
                    target["departure_date"] = actual["start_date"]
                if actual["end_date"]:
                    target["return_date"] = actual["end_date"]
                if anchor_name:
                    day = candidate["day_wise_itinerary"][path[1]]
                    booked_date = (
                        actual["end_date"]
                        if day.get("date") == row["end_date"]
                        else actual["start_date"]
                    )
                    if booked_date and booked_date != day.get("date"):
                        destination = next(
                            (
                                d
                                for d in candidate["day_wise_itinerary"]
                                if d.get("date") == booked_date
                            ),
                            None,
                        )
                        if destination is None:
                            raise ValueError(
                                "Add the booked flight date to the itinerary before recording it."
                            )
                        day["stops"].remove(target)
                        destination.setdefault("stops", []).append(target)
                        changed_days.add(candidate["day_wise_itinerary"].index(destination))
            elif actual["start_date"] and path[0] == "day_wise_itinerary":
                day = candidate["day_wise_itinerary"][path[1]]
                if str(day.get("date") or "") != actual["start_date"]:
                    destination = next(
                        (
                            d
                            for d in candidate["day_wise_itinerary"]
                            if d.get("date") == actual["start_date"]
                        ),
                        None,
                    )
                    if destination is None:
                        raise ValueError(
                            "Add the booked date to the itinerary before recording this booking."
                        )
                    day["stops"].remove(target)
                    destination.setdefault("stops", []).append(target)
                    changed_days.add(candidate["day_wise_itinerary"].index(destination))
            if actual["time"] and (
                path[0] != "day_wise_itinerary"
                or row["category"] not in {"flights", "hotels"}
                or candidate["day_wise_itinerary"][path[1]].get("date") == row["start_date"]
            ):
                target["time"] = actual["time"]
        for index in changed_days:
            candidate["day_wise_itinerary"][index]["stops"].sort(
                key=lambda stop: str(stop.get("time") or "23:59")
            )
        total = number(candidate.get("total_cost"))
        if (
            total is not None
            and old_amount is not None
            and actual["amount"] is not None
            and row["currency"] == actual["currency"] == candidate.get("currency")
        ):
            candidate["total_cost"] = round(total + actual["amount"] - old_amount, 2)
        elif old_amount != actual["amount"] or row["currency"] != actual["currency"]:
            candidate["cost_total_needs_review"] = True
            warnings.append(
                "Whole-trip total needs review: the actual amount or its currency is not comparable."
            )
        record["actual"] = {**actual, "reported_at": now(), "evidence": "user_reported"}
        if row["category"] == "flights":
            warnings.append(
                "Confirm the actual flight numbers, segments and arrival times in the itinerary; original offer terms are retained only in the saved intention."
            )
        warnings.extend(
            f"{k} is above its cap after this actual booking."
            for k, v in budget_summary(candidate).items()
            if v["status"] == "over_cap"
        )
    else:
        raise ValueError("Unsupported booking intent action.")
    if action in {"choose", "report"}:
        from tripplanner.tools.trip_guard import validate_plan

        existing = {v.message for v in validate_plan(plan)}
        conflicts = [v.message for v in validate_plan(candidate) if v.message not in existing]
        if conflicts and action == "choose":
            raise ValueError(
                "This choice creates itinerary conflicts. Adjust the affected stops first: "
                + " ".join(conflicts)
            )
        warnings.extend(conflicts)
    record["warnings"] = list(dict.fromkeys(warnings))
    return candidate, record["warnings"]


def constrain_recommendation(plan: dict, decision):
    """Apply a category's remaining allowance before convenience ranking."""
    from tripplanner.decisions.flights import rank_flights
    from tripplanner.decisions.lodging import rank_stays

    category = {"flight": "flights", "lodging": "hotels"}.get(decision.kind)
    cap = caps_for(plan).get(category)
    if not cap:
        return decision
    others = [
        r
        for r in units(plan)
        if r["category"] == category and r["decision_id"] != decision.id and r["selected"]
    ]
    remaining = cap["amount"] - sum(
        r["amount"] or 0 for r in others if r["currency"] == cap["currency"]
    )
    eligible = [
        o
        for o in decision.options
        if o.price and o.price.currency == cap["currency"] and o.price.amount <= remaining
    ]
    ranked = (
        (rank_flights(eligible) if category == "flights" else rank_stays(eligible))
        if eligible
        else None
    )
    if ranked:
        decision.chosen_option_id, decision.rule, reasons = ranked
        decision.rule.text = "Within the remaining category cap; " + decision.rule.text
        chosen = decision.option(decision.chosen_option_id)
        decision.effect.total_cost = chosen.price.amount
        decision.effect.currency = chosen.price.currency
        for option in eligible:
            option.rejected_because = reasons.get(option.id)
    else:
        decision.rule.text = (
            "No saved offer is known to fit the remaining category cap. Revise the search or cap."
        )
    for option in decision.options:
        if option not in eligible:
            option.rejected_because = (
                "Outside the remaining category cap, or currency/price is unverified."
            )
    return decision
