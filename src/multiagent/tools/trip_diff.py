"""Compact structural diff between two trip-plan dicts.

Used by `update_trip_plan` to tell the agent (and the user) *what changed*
in plain English instead of just returning "Trip plan updated.". Pure
functions, no I/O.
"""

from __future__ import annotations

from typing import Any

# Fields the user actually cares about hearing changes for.
_LIST_FIELDS = (
    ("selected_flights", "flight"),
    ("selected_hotels", "hotel"),
    ("selected_activities", "activity"),
    ("day_wise_itinerary", "day"),
)


def _label(item: Any) -> str:
    """Best-effort short label for a flight/hotel/activity/day dict."""
    if isinstance(item, str):
        return item.strip()[:80]
    if not isinstance(item, dict):
        return str(item)[:80]
    for key in (
        "name",
        "title",
        "hotel_name",
        "activity",
        "airline",
        "carrier",
        "summary",
        "label",
        "description",
    ):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:80]
    # Day-wise itinerary entries.
    if "day" in item:
        plan = item.get("plan") or item.get("summary") or ""
        return f"Day {item['day']}: {str(plan)[:60]}".strip()
    # Fall back to first stringy value.
    for v in item.values():
        if isinstance(v, str) and v.strip():
            return v.strip()[:80]
    return "(unnamed item)"


def _ids(items: list[Any]) -> list[str]:
    return [_label(i) for i in items or []]


def _set_diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    """Order-preserving multiset diff. Returns (added, removed)."""
    after_remaining = list(after)
    removed: list[str] = []
    for b in before:
        if b in after_remaining:
            after_remaining.remove(b)
        else:
            removed.append(b)
    return after_remaining, removed


def _fmt_money(n: Any) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}"


def diff_plans(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[str]:
    """Return a short list of "what changed" bullets, or [] when nothing material changed."""
    if not before:
        return ["new plan created"] if after else []
    if not after:
        return []

    bullets: list[str] = []

    # Destination / dates / origin.
    for key, label in (
        ("destination", "destination"),
        ("origin", "origin"),
        ("departure_date", "departure"),
        ("return_date", "return"),
        ("travelers", "travelers"),
    ):
        b = before.get(key) or ""
        a = after.get(key) or ""
        if b != a and (b or a):
            bullets.append(f"{label}: {b or '(none)'} \u2192 {a or '(none)'}")

    # List fields.
    for field, noun in _LIST_FIELDS:
        b_ids = _ids(before.get(field) or [])
        a_ids = _ids(after.get(field) or [])
        if b_ids == a_ids:
            continue
        added, removed = _set_diff(b_ids, a_ids)
        # Single swap: 1 removed + 1 added => phrase as swap.
        if len(added) == 1 and len(removed) == 1:
            bullets.append(f"swapped {noun}: '{removed[0]}' \u2192 '{added[0]}'")
            continue
        for r in removed:
            bullets.append(f"removed {noun}: '{r}'")
        for a in added:
            bullets.append(f"added {noun}: '{a}'")

    # Total cost delta.
    b_total = before.get("total_cost") or 0
    a_total = after.get("total_cost") or 0
    try:
        delta = float(a_total) - float(b_total)
    except (TypeError, ValueError):
        delta = 0
    if delta:
        sign = "+" if delta > 0 else "-"
        bullets.append(
            f"total cost: {_fmt_money(b_total)} \u2192 {_fmt_money(a_total)} ({sign}{_fmt_money(abs(delta))})"
        )

    # Status transition.
    b_status = before.get("status") or ""
    a_status = after.get("status") or ""
    if b_status != a_status and a_status:
        bullets.append(f"status: {b_status or '(unset)'} \u2192 {a_status}")

    return bullets


def format_diff(bullets: list[str]) -> str:
    """Render bullets as a single multi-line string for tool return values."""
    if not bullets:
        return "no material changes"
    return "\n".join(f"  \u2022 {b}" for b in bullets)
