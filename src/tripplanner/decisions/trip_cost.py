"""What a trip costs according to evidence we can name.

The planner's ``total_cost`` is a working figure the model maintains. This module
does something narrower and stricter: it walks the selected flights, stays and
activities, matches each against the price checks actually recorded on the plan,
and reports what is genuinely backed by a provider quote.

A line is priced only when a real check stands behind it. A number with no check
is reported as unverified, an expired check as stale, and a missing number as
unpriced. Two currencies are never added together without a published rate.
Nothing here estimates a fare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tripplanner.decisions.provenance import is_expired
from tripplanner.providers.fx import convert_with_provenance

# Kinds map to the price-check kinds recorded by the search tools.
_BUCKETS: tuple[tuple[str, str, str], ...] = (
    ("selected_flights", "flights", "Flights"),
    ("selected_hotels", "lodging", "Stays"),
    ("selected_activities", "activities", "Activities"),
)
_PRICE_KEYS = ("total_price", "price", "total", "cost", "amount", "fare")
_NAME_KEYS = ("name", "hotel_name", "title", "label", "airline", "description")
_CURRENCY_KEYS = ("currency", "currency_code")
_REQUIRED_COMPONENTS = {
    "flights": ("taxes and mandatory carrier fees", "baggage charges"),
    "lodging": ("taxes and mandatory property fees",),
    "activities": ("taxes and mandatory booking fees",),
}

LIVE = "live"
STALE = "stale"
UNVERIFIED = "unverified"
UNPRICED = "unpriced"

_NUMERIC = re.compile(r"[-+]?\d[\d,]*\.?\d*")


@dataclass(frozen=True)
class CostLine:
    kind: str
    label: str
    status: str
    amount: float | None = None
    currency: str = ""
    provider: str = ""
    checked_at: str = ""
    expires_at: str = ""
    reason: str = ""
    fx: dict[str, Any] | None = None
    components: tuple[dict[str, Any], ...] = ()
    required_unknown: tuple[str, ...] = ()
    all_in_amount: float | None = None

    @property
    def all_in_complete(self) -> bool:
        return self.status == LIVE and not self.required_unknown

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
        }
        if self.amount is not None:
            payload["amount"] = round(self.amount, 2)
            payload["currency"] = self.currency
        for key, value in (
            ("provider", self.provider),
            ("checked_at", self.checked_at),
            ("expires_at", self.expires_at),
            ("reason", self.reason),
        ):
            if value:
                payload[key] = value
        if self.fx:
            payload["fx"] = self.fx
        payload["components"] = list(self.components)
        payload["required_unknown"] = list(self.required_unknown)
        payload["all_in_complete"] = self.all_in_complete
        if self.all_in_amount is not None:
            payload["all_in_amount"] = round(self.all_in_amount, 2)
        return payload


@dataclass(frozen=True)
class CostLedger:
    currency: str
    lines: list[CostLine] = field(default_factory=list)
    priced_total: float | None = None
    priced_count: int = 0
    stale_count: int = 0
    unverified_count: int = 0
    unpriced_count: int = 0
    all_in_total: float | None = None
    required_unknown: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """True only when every mandatory cost is known from a live quote."""
        return (
            bool(self.lines)
            and self.priced_count == len(self.lines)
            and not self.required_unknown
        )

    def as_dict(self) -> dict[str, Any]:
        coverage_pct = round(self.priced_count / len(self.lines) * 100) if self.lines else 0
        all_in_count = sum(1 for line in self.lines if line.all_in_complete)
        all_in_coverage_pct = round(all_in_count / len(self.lines) * 100) if self.lines else 0
        return {
            "currency": self.currency,
            "lines": [line.as_dict() for line in self.lines],
            "priced_total": None if self.priced_total is None else round(self.priced_total, 2),
            "all_in_total": None if self.all_in_total is None else round(self.all_in_total, 2),
            "priced_count": self.priced_count,
            "stale_count": self.stale_count,
            "unverified_count": self.unverified_count,
            "unpriced_count": self.unpriced_count,
            "complete": self.complete,
            "coverage_pct": coverage_pct,
            "all_in_count": all_in_count,
            "all_in_coverage_pct": all_in_coverage_pct,
            "required_unknown": list(self.required_unknown),
            "summary": self.summary,
        }

    @property
    def summary(self) -> str:
        """One line a traveller can read, or empty when there is nothing to say."""
        if not self.lines:
            return ""
        unbacked = self.stale_count + self.unverified_count + self.unpriced_count
        if not unbacked and not self.required_unknown:
            noun = "item" if self.priced_count == 1 else "items"
            return f"All-in total confirmed for {self.priced_count} {noun}."
        if not unbacked:
            count = len(self.required_unknown)
            return (
                f"{self.priced_count} live quote{'s' if self.priced_count != 1 else ''}"
                f" · final total not confirmed ({count} unknown cost "
                f"categor{'ies' if count != 1 else 'y'})"
            )
        parts = []
        if self.priced_count:
            parts.append(f"{self.priced_count} priced")
        if self.stale_count:
            parts.append(f"{self.stale_count} needs re-checking")
        if self.unverified_count:
            parts.append(f"{self.unverified_count} unverified")
        if self.unpriced_count:
            parts.append(f"{self.unpriced_count} unpriced")
        return " · ".join(parts)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) or None
    if isinstance(value, str):
        match = _NUMERIC.search(value.replace(",", ""))
        if not match:
            return None
        try:
            return float(match.group()) or None
        except ValueError:
            return None
    return None


def _amount_of(item: dict[str, Any]) -> float | None:
    for key in _PRICE_KEYS:
        if key in item:
            amount = _number(item[key])
            if amount is not None:
                return amount
    return None


def _currency_of(item: dict[str, Any], fallback: str) -> str:
    for key in _CURRENCY_KEYS:
        value = str(item.get(key) or "").strip().upper()
        if len(value) == 3 and value.isalpha():
            return value
    return fallback


def _label_of(item: dict[str, Any], default: str) -> str:
    for key in _NAME_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _latest_check(
    plan: dict[str, Any], kind: str, provider: str = ""
) -> dict[str, Any] | None:
    """The most recent recorded look at this kind of source."""
    checks = [
        row
        for row in plan.get("price_checks") or []
        if (
            isinstance(row, dict)
            and row.get("kind") == kind
            and row.get("provider")
            and (not provider or row.get("provider") == provider)
        )
    ]
    if not checks:
        return None
    return max(checks, key=lambda row: str(row.get("checked_at") or ""))


def _price_composition(
    item: dict[str, Any], kind: str, amount: float, currency: str, *, trusted: bool
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...], float]:
    raw = item.get("price_composition")
    composition = raw if isinstance(raw, dict) else {}
    complete = (
        trusted
        and (
            composition.get("all_in") is True
            or composition.get("mandatory_costs_complete") is True
        )
    )
    components: list[dict[str, Any]] = []
    for key, label in (
        ("taxes", "Taxes"),
        ("fees", "Fees"),
        ("due_at_property", "Due at property"),
    ):
        value = _number(composition.get(key))
        if value is not None:
            components.append(
                {
                    "kind": key,
                    "label": label,
                    "amount": round(value, 2),
                    "currency": currency,
                    "inclusion": "included" if complete else "unknown",
                }
            )

    excluded_total = 0.0
    excluded = composition.get("excluded")
    if isinstance(excluded, list):
        for component in excluded:
            if not isinstance(component, dict):
                continue
            value = _number(component.get("amount"))
            label = str(component.get("label") or component.get("kind") or "Mandatory charge")
            if value is None:
                continue
            excluded_total += value
            components.append(
                {
                    "kind": str(component.get("kind") or "mandatory_charge"),
                    "label": label,
                    "amount": round(value, 2),
                    "currency": currency,
                    "inclusion": "excluded",
                }
            )

    required_unknown = () if complete else _REQUIRED_COMPONENTS.get(kind, ())
    return tuple(components), tuple(required_unknown), amount + excluded_total


def build_cost_ledger(
    plan: dict[str, Any] | None, *, now: datetime | None = None
) -> CostLedger:
    """Cost lines for one plan, each classified by the evidence behind it."""
    if not plan:
        return CostLedger(currency="")

    currency = str(plan.get("currency") or "").strip().upper() or "INR"
    lines: list[CostLine] = []

    for bucket, check_kind, default_label in _BUCKETS:
        items = plan.get(bucket)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            label = _label_of(item, f"{default_label} {index}")
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            item_provider = str(source.get("provider") or "")
            check = _latest_check(plan, check_kind, item_provider)
            expired = is_expired(check, now=now) if check else True
            amount = _amount_of(item)
            if amount is None:
                lines.append(
                    CostLine(
                        kind=check_kind,
                        label=label,
                        status=UNPRICED,
                        reason="no price recorded for this item",
                    )
                )
                continue

            item_currency = _currency_of(item, currency)
            conversion = convert_with_provenance(amount, item_currency, currency)
            if conversion is None:
                lines.append(
                    CostLine(
                        kind=check_kind,
                        label=label,
                        status=UNPRICED,
                        amount=amount,
                        currency=item_currency,
                        reason=f"no published {item_currency}->{currency} rate",
                    )
                )
                continue

            if check is None:
                status, reason = UNVERIFIED, "no provider check recorded for this kind"
            elif expired:
                status, reason = STALE, "the provider check has expired"
            else:
                status, reason = LIVE, ""

            components, required_unknown, item_all_in = _price_composition(
                item,
                check_kind,
                amount,
                item_currency,
                trusted=bool(item_provider and check and check.get("provider") == item_provider),
            )
            all_in_conversion = convert_with_provenance(item_all_in, item_currency, currency)

            lines.append(
                CostLine(
                    kind=check_kind,
                    label=label,
                    status=status,
                    amount=conversion.amount,
                    currency=currency,
                    provider=str((check or {}).get("provider") or ""),
                    checked_at=str((check or {}).get("checked_at") or ""),
                    expires_at=str((check or {}).get("expires_at") or ""),
                    reason=reason,
                    fx=(
                        conversion.provenance()
                        if conversion.from_currency != conversion.to_currency
                        else None
                    ),
                    components=components,
                    required_unknown=required_unknown,
                    all_in_amount=(
                        all_in_conversion.amount
                        if status == LIVE and not required_unknown and all_in_conversion
                        else None
                    ),
                )
            )

    priced = [line for line in lines if line.status == LIVE and line.amount is not None]
    required_unknown = tuple(
        dict.fromkeys(component for line in lines for component in line.required_unknown)
    )
    all_in = [line for line in lines if line.all_in_amount is not None]
    return CostLedger(
        currency=currency,
        lines=lines,
        priced_total=round(sum(line.amount or 0.0 for line in priced), 2) if priced else None,
        priced_count=len(priced),
        stale_count=sum(1 for line in lines if line.status == STALE),
        unverified_count=sum(1 for line in lines if line.status == UNVERIFIED),
        unpriced_count=sum(1 for line in lines if line.status == UNPRICED),
        all_in_total=(
            round(sum(line.all_in_amount or 0.0 for line in all_in), 2)
            if lines and len(all_in) == len(lines)
            else None
        ),
        required_unknown=required_unknown,
    )
