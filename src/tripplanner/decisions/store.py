"""Where decisions live on the trip document, and how big they are allowed to get.

Decisions ride inside the existing trip plan rather than in a second store, so a
trip can never load with a plan from one write and a rationale from another. The
ceilings here keep the worst case well inside the Cosmos document limit.
"""

from __future__ import annotations

from typing import Any

from tripplanner.decisions.models import Decision, decision_from_dict, decision_to_dict

MAX_OPTIONS_PER_DECISION = 6
MAX_DECISIONS_PER_TRIP = 40

_FIELD = "decisions"


def list_decisions(plan: dict[str, Any] | None) -> list[Decision]:
    raw = (plan or {}).get(_FIELD) or []
    if not isinstance(raw, list):
        return []
    parsed = [decision_from_dict(item) for item in raw if isinstance(item, dict)]
    return [item for item in parsed if item is not None]


def find_decision(plan: dict[str, Any] | None, decision_id: str) -> Decision | None:
    return next((d for d in list_decisions(plan) if d.id == decision_id), None)


def prune_decisions(decisions: list[Decision]) -> list[Decision]:
    """Cap options per decision and decisions per trip, keeping the newest.

    An overruled decision is never dropped: it is the user's own edit, and losing
    it would silently undo them.
    """
    trimmed: list[Decision] = []
    for decision in decisions:
        if len(decision.options) > MAX_OPTIONS_PER_DECISION:
            keep = [o for o in decision.options if o.id == decision.active_option_id]
            rest = [o for o in decision.options if o.id != decision.active_option_id]
            decision = decision.model_copy(
                update={"options": keep + rest[: MAX_OPTIONS_PER_DECISION - len(keep)]}
            )
        trimmed.append(decision)

    if len(trimmed) <= MAX_DECISIONS_PER_TRIP:
        return trimmed

    overruled = [d for d in trimmed if d.override is not None]
    agent = [d for d in trimmed if d.override is None]
    room = max(0, MAX_DECISIONS_PER_TRIP - len(overruled))
    agent = sorted(agent, key=lambda d: d.created_at, reverse=True)[:room]
    kept = {d.id for d in overruled} | {d.id for d in agent}
    return [d for d in trimmed if d.id in kept]


def upsert_decision(plan: dict[str, Any], decision: Decision) -> dict[str, Any]:
    """Replace the decision with the same id, or append it, then prune.

    Ids are deterministic, so re-running the same comparison refreshes it instead
    of stacking duplicates. A user override on the existing record survives the
    refresh unless the option they picked no longer exists.
    """
    existing = list_decisions(plan)
    previous = next((d for d in existing if d.id == decision.id), None)
    if previous is not None and previous.override is not None:
        if decision.option(previous.override.option_id) is not None:
            decision = decision.model_copy(
                update={"override": previous.override, "state": previous.state}
            )

    merged = [d for d in existing if d.id != decision.id] + [decision]
    plan[_FIELD] = [decision_to_dict(d) for d in prune_decisions(merged)]
    return plan
