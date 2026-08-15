"""Bring a saved trip to the state today's checks would have produced.

Two questions have to stay apart. "Is anything wrong" is the guard's, and it
answers from facts. "May I fix it" is this module's, and it answers from who
chose the stop. A contradiction among the planner's own suggestions is the
planner's to clear; a contradiction inside something the traveller booked is a
conversation, because every legal repair would move what they committed to.

So a repair pass returns one of three things: nothing to do, a rearrangement it
made and can explain, or a finding it is not allowed to touch. It never returns
a silent partial fix.
"""

from __future__ import annotations

from typing import Any

from tripplanner import authorship
from tripplanner.decisions.store import list_decisions
from tripplanner.tools import trip_guard, trip_rebalance
from tripplanner.web.place_confidence import confirmed_bindings


def _overridden_decisions(plan: dict[str, Any]) -> set[str]:
    return {
        decision.id for decision in list_decisions(plan) if decision.override is not None
    }


def pinned_for(plan: dict[str, Any]) -> dict[tuple[int, str], authorship.Ownership]:
    """Stops a repair must leave exactly where they are."""
    return authorship.pinned_stops(
        plan,
        confirmed_places=set(confirmed_bindings(plan)),
        overridden_decisions=_overridden_decisions(plan),
    )


def blocked_findings(
    plan: dict[str, Any], pinned: dict[tuple[int, str], authorship.Ownership]
) -> list[dict[str, Any]]:
    """Contradictions the planner is not allowed to repair on its own."""
    out: list[dict[str, Any]] = []
    for violation in trip_guard.validate_plan(plan):
        if violation.code not in trip_guard.KNOWN_FACT_CODES:
            continue
        key = (violation.day, violation.stop or "")
        owned = pinned.get(key)  # type: ignore[arg-type]
        if owned is None:
            continue
        out.append(
            {
                "code": violation.code,
                "day": violation.day,
                "stop": violation.stop,
                "message": violation.message,
                "reason": owned.reason,
            }
        )
    return out


def repair(plan: dict[str, Any], *, budget_ms: int = 400) -> dict[str, Any]:
    """Rearrange what the planner owns; report what it may not touch."""
    pinned = pinned_for(plan)
    result = trip_rebalance.rebalance(
        plan, pinned=set(pinned), budget_ms=budget_ms
    )
    blocked = blocked_findings(result.plan, pinned)
    return {
        "plan": result.plan,
        "changed": result.changed,
        "moves": [
            {
                "name": move.name,
                "from_day": move.from_day,
                "to_day": move.to_day,
                "time": move.time,
            }
            for move in result.moves
        ],
        "sentences": result.sentences(),
        "blocked": blocked,
        "before": {
            "contradictions": result.before.contradictions,
            "travel_min": result.before.travel_min,
        },
        "after": {
            "contradictions": result.after.contradictions,
            "travel_min": result.after.travel_min,
        },
    }
