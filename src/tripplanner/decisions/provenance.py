"""When we last looked, and at what.

A price on a plan is a claim about the world at a moment. Recording the moment
is what makes it checkable; without it a figure is only confident typography.
This module keeps that record and, once it has gone stale, refuses to let the
number be described as current.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

MAX_CHECKS = 12
_FIELD = "price_checks"

# How long a quote from each kind of source is worth calling current. Airfares
# move within the hour; a nightly rate does not.
_TTL_MINUTES = {"flights": 30, "lodging": 720}
_DEFAULT_TTL_MINUTES = 60

_KIND_LABEL = {"flights": "Flights", "lodging": "Stays", "transport": "Ground transport"}


@dataclass(frozen=True)
class PriceCheck:
    kind: str
    provider: str
    checked_at: str
    expires_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "provider": self.provider,
            "checked_at": self.checked_at,
            "expires_at": self.expires_at,
        }


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def make_check(kind: str, provider: str, *, now: datetime | None = None) -> PriceCheck:
    at = now or datetime.now()
    ttl = _TTL_MINUTES.get(kind, _DEFAULT_TTL_MINUTES)
    return PriceCheck(
        kind=kind,
        provider=provider,
        checked_at=at.isoformat(timespec="seconds"),
        expires_at=(at + timedelta(minutes=ttl)).isoformat(timespec="seconds"),
    )


def record_check(plan: dict[str, Any], check: PriceCheck) -> None:
    """Keep the most recent look per source. Older ones tell us nothing new."""
    existing = [
        row
        for row in plan.get(_FIELD) or []
        if isinstance(row, dict)
        and not (row.get("kind") == check.kind and row.get("provider") == check.provider)
    ]
    existing.append(check.as_dict())
    plan[_FIELD] = existing[-MAX_CHECKS:]


def is_expired(check: dict[str, Any], *, now: datetime | None = None) -> bool:
    expires = _parse(check.get("expires_at"))
    if expires is None:
        # No expiry recorded means we cannot vouch for it. Say so.
        return True
    return (now or datetime.now()) >= expires


def describe(check: dict[str, Any], *, now: datetime | None = None) -> str:
    kind = _KIND_LABEL.get(str(check.get("kind") or ""), "Prices")
    provider = str(check.get("provider") or "a provider")
    checked = _parse(check.get("checked_at"))
    when = checked.strftime("%d %b %H:%M") if checked else "at an unrecorded time"
    if is_expired(check, now=now):
        return f"{kind} last priced from {provider} on {when} — may have changed."
    return f"{kind} priced from {provider} on {when}."


def build_provenance(plan: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    """The provenance rows a surface may render. Empty when we looked at nothing."""
    rows: list[dict[str, Any]] = []
    for check in plan.get(_FIELD) or []:
        if not isinstance(check, dict) or not check.get("provider"):
            continue
        rows.append(
            {
                "kind": str(check.get("kind") or ""),
                "provider": str(check["provider"]),
                "checked_at": str(check.get("checked_at") or ""),
                "expires_at": str(check.get("expires_at") or ""),
                "current": not is_expired(check, now=now),
                "text": describe(check, now=now),
            }
        )
    return rows


def note_price_check(kind: str, provider: str) -> None:
    """Record a look from inside a search tool.

    Provenance is a courtesy to the traveller, not part of the search contract:
    if it cannot be written, the search must still return its answer.
    """
    from tripplanner.tools import trip_planner

    try:
        trip_planner.record_price_check(kind, provider)
    except Exception:
        pass
