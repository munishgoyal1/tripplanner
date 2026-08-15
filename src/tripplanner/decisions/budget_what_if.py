"""On-demand budget proposals grounded in alternatives already compared."""

from __future__ import annotations

from typing import Any

from tripplanner.decisions.models import DecisionKind, Option
from tripplanner.decisions.rules import party_total
from tripplanner.decisions.store import list_decisions
from tripplanner.decisions.trip_cost import build_cost_ledger

_SUPPORTED_KINDS = {DecisionKind.FLIGHT, DecisionKind.LODGING}


def _total(option: Option) -> float | None:
    if option.price is None:
        return None
    return party_total(option, 1)


def build_budget_what_if(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Cheaper exact alternatives, generated only when this function is called."""
    ledger = build_cost_ledger(plan)
    proposals: list[dict[str, Any]] = []
    for decision in list_decisions(plan):
        if decision.kind not in _SUPPORTED_KINDS or decision.chosen is None:
            continue
        current_total = _total(decision.chosen)
        if current_total is None:
            continue
        for option in decision.options:
            option_total = _total(option)
            if option.id == decision.active_option_id or option_total is None:
                continue
            savings = round(current_total - option_total, 2)
            if savings <= 0:
                continue
            proposals.append(
                {
                    "id": f"what_if:{decision.id}:{option.id}",
                    "decision_id": decision.id,
                    "option_id": option.id,
                    "kind": decision.kind.value,
                    "subject": decision.subject,
                    "label": option.label,
                    "savings": savings,
                    "currency": option.price.currency,
                    "tradeoff": option.rejected_because or decision.rule.text,
                    "personalized": False,
                }
            )

    proposals.sort(key=lambda proposal: proposal["savings"], reverse=True)
    return {
        "generated_on_demand": True,
        "estimated": not ledger.complete,
        "evidence_coverage_pct": ledger.as_dict()["coverage_pct"],
        "currency": ledger.currency,
        "proposals": proposals,
    }
