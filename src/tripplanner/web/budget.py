"""Budget and money helpers for the trip-panel view-model.

Pure aggregation over the active trip dict — no network, no UI concerns.
Split out of ``trip_view`` (tech-debt #7) to keep one concern per file;
``trip_view`` re-exports these names so existing callers are unaffected.
"""

from __future__ import annotations

import re
from typing import Any

# ISO code → display symbol. Anything not listed is shown verbatim (already a
# symbol, or an exotic code we just print as-is).
_CURRENCY_SYMBOLS = {
    "INR": "\u20b9",
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "JPY": "\u00a5",
    "THB": "\u0e3f",
    "AED": "AED ",
    "AUD": "A$",
    "SGD": "S$",
    "CAD": "C$",
    "CHF": "CHF ",
}
_PRICE_KEYS = ("price", "total_price", "total", "cost", "amount", "fare")
_TRAVELER_RE = re.compile(
    r"(\d+)\s*(adults?|children|child|kids?|elderly|seniors?|infants?|people|travell?ers?|pax)",
    re.I,
)


def fmt_money(value: Any, symbol: str = "\u20b9") -> str:
    if isinstance(value, (int, float)) and value:
        return f"{symbol}{value:,.0f}"
    return "\u2014"


def currency_symbol(trip: dict[str, Any] | None) -> str:
    """Resolve the plan's sticky display currency to a render-ready symbol.

    The trip agent stores its chosen currency on the plan (``currency``) as
    either an ISO code (``"USD"``) or a symbol (``"$"``). Defaults to ₹ to match
    the agent's domestic-India default.
    """
    raw = str((trip or {}).get("currency") or "").strip()
    if not raw:
        return "\u20b9"
    return _CURRENCY_SYMBOLS.get(raw.upper(), raw)


def _to_number(value: Any) -> float:
    """Best-effort numeric coercion ("₹8,500", "8500", 8500.0 → 8500.0)."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.]", "", value.replace(",", ""))
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    return 0.0


def _sum_item_prices(items: Any) -> float:
    """Sum the first price-like field on each selected item dict."""
    total = 0.0
    for it in items or []:
        if not isinstance(it, dict):
            continue
        for k in _PRICE_KEYS:
            if k in it:
                n = _to_number(it[k])
                if n:
                    total += n
                    break
    return total


def traveler_count(travelers: Any) -> int:
    """Headcount from a free-form travelers string ("2 adults, 1 child" → 3).

    Only counts numbers that precede a traveler word so trailing ages
    ("(ages 5)") don't inflate the total. Falls back to 1.
    """
    if isinstance(travelers, (int, float)) and not isinstance(travelers, bool):
        return int(travelers) or 1
    matches = _TRAVELER_RE.findall(str(travelers or ""))
    count = sum(int(m[0]) for m in matches)
    return count or 1


def build_budget(trip: dict[str, Any] | None) -> dict[str, Any] | None:
    """Live budget meter view-model: spend, per-traveler split, remaining-vs-target.

    Pure aggregation over the active trip — no network. Returns ``None`` when
    there's nothing to show (no spend recorded and no target set), so the
    frontend can hide the meter entirely.

    ``spent`` prefers the agent-maintained ``total_cost`` (authoritative) and
    falls back to summing per-item prices. ``target`` comes from the optional
    ``budget`` field the agent sets when the user states a budget for the trip.
    """
    if not trip:
        return None

    symbol = currency_symbol(trip)
    breakdown = {
        "flights": round(_sum_item_prices(trip.get("selected_flights")), 2),
        "hotels": round(_sum_item_prices(trip.get("selected_hotels")), 2),
        "activities": round(_sum_item_prices(trip.get("selected_activities")), 2),
    }
    from_items = sum(breakdown.values())
    total_cost = _to_number(trip.get("total_cost"))
    spent = round(total_cost if total_cost else from_items, 2)
    target = _to_number(trip.get("budget"))

    if spent <= 0 and target <= 0:
        return None

    heads = traveler_count(trip.get("travelers"))
    per_traveler = round(spent / heads, 2) if heads else spent

    out: dict[str, Any] = {
        "currency": symbol,
        "spent": spent,
        "spent_display": fmt_money(spent, symbol),
        "travelers": heads,
        "per_traveler": per_traveler,
        "per_traveler_display": fmt_money(per_traveler, symbol),
        "breakdown": {k: v for k, v in breakdown.items() if v > 0},
        "target": None,
        "target_display": "",
        "remaining": None,
        "remaining_display": "",
        "pct_used": None,
        "over_budget": False,
    }

    if target > 0:
        remaining = round(target - spent, 2)
        out.update(
            {
                "target": round(target, 2),
                "target_display": fmt_money(target, symbol),
                "remaining": remaining,
                "remaining_display": fmt_money(abs(remaining), symbol),
                "pct_used": int(round(min(spent / target, 9.99) * 100)),
                "over_budget": spent > target,
            }
        )
    return out
