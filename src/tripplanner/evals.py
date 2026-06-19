"""Deterministic trip-plan evaluation scenarios.

These evals sit above unit tests and below full live-agent runs. They score a
completed trip plan against product expectations for common travel scenarios:
family fit, mobility, budget, visa/checklist coverage, closures, routing, and
grounded prices. The rules are intentionally deterministic so they can run in
CI without model or travel API calls.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import ToolMessage

from tripplanner.hallucination_critic import critique as critique_grounding
from tripplanner.tools.finalize_critic import critique as critique_finalize


@dataclass(frozen=True)
class EvalCheck:
    """One deterministic expectation for a trip plan."""

    id: str
    description: str
    weight: int = 1


@dataclass(frozen=True)
class EvalScenario:
    """A reusable travel-planning scenario with preferences and expectations."""

    id: str
    name: str
    prompt: str
    prefs: dict[str, Any]
    checks: tuple[EvalCheck, ...]
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    id: str
    description: str
    passed: bool
    reason: str
    weight: int = 1


@dataclass(frozen=True)
class EvalResult:
    scenario_id: str
    scenario_name: str
    score: float
    passed: bool
    checks: tuple[CheckResult, ...]

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)


def _text(blob: Any) -> str:
    if blob is None:
        return ""
    if isinstance(blob, str):
        return blob.lower()
    if isinstance(blob, (int, float, bool)):
        return str(blob).lower()
    if isinstance(blob, dict):
        return " ".join(_text(v) for v in blob.values())
    if isinstance(blob, (list, tuple)):
        return " ".join(_text(v) for v in blob)
    return str(blob).lower()


def _items(plan: dict[str, Any], *keys: str) -> list[Any]:
    out: list[Any] = []
    for key in keys:
        val = plan.get(key) or []
        if isinstance(val, list):
            out.extend(val)
    return out


def _has_any(blob: Any, terms: tuple[str, ...]) -> bool:
    haystack = _text(blob)
    return any(t.lower() in haystack for t in terms)


def _cost(plan: dict[str, Any]) -> float | None:
    raw = plan.get("total_cost")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        cleaned = re.sub(r"[^0-9.]", "", raw)
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


def _budget_limit(prefs: dict[str, Any]) -> float | None:
    raw = prefs.get("budget_limit")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        cleaned = re.sub(r"[^0-9.]", "", raw)
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


def _result(check: EvalCheck, passed: bool, reason: str) -> CheckResult:
    return CheckResult(
        id=check.id,
        description=check.description,
        passed=passed,
        reason=reason,
        weight=check.weight,
    )


def evaluate_plan(
    scenario: EvalScenario,
    plan: dict[str, Any],
    final_reply: str = "",
) -> EvalResult:
    """Score ``plan`` against ``scenario``.

    ``final_reply`` is optional. When provided with scenario evidence, concrete
    prices/times/URLs in the reply are checked against that evidence via the
    existing hallucination critic.
    """
    checks: list[CheckResult] = []

    for check in scenario.checks:
        checks.append(_evaluate_check(check, scenario, plan, final_reply))

    earned = sum(c.weight for c in checks if c.passed)
    possible = sum(c.weight for c in checks) or 1
    score = earned / possible
    return EvalResult(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        score=score,
        passed=all(c.passed for c in checks),
        checks=tuple(checks),
    )


def _evaluate_check(
    check: EvalCheck,
    scenario: EvalScenario,
    plan: dict[str, Any],
    final_reply: str,
) -> CheckResult:
    prefs = scenario.prefs
    cid = check.id

    if cid == "finalize_critic_clean":
        issues = critique_finalize(plan, prefs)
        return _result(check, not issues, "; ".join(issues) if issues else "plan passed critic")

    if cid == "has_flights":
        ok = bool(plan.get("selected_flights"))
        return _result(check, ok, "selected flights present" if ok else "missing selected flights")

    if cid == "has_hotels":
        ok = bool(plan.get("selected_hotels"))
        return _result(check, ok, "selected hotels present" if ok else "missing selected hotels")

    if cid == "has_day_itinerary":
        ok = bool(plan.get("day_wise_itinerary"))
        return _result(check, ok, "day-wise itinerary present" if ok else "missing itinerary")

    if cid == "kid_friendly":
        activities = _items(plan, "selected_activities", "day_wise_itinerary")
        ok = _has_any(
            activities,
            ("kid", "family", "child", "zoo", "park", "aquarium", "museum", "beach"),
        )
        return _result(check, ok, "kid-friendly cue found" if ok else "no kid-friendly cue")

    if cid == "mobility_accessible":
        choices = _items(plan, "selected_hotels", "selected_activities", "day_wise_itinerary")
        ok = _has_any(choices, ("accessible", "wheelchair", "elevator", "lift", "step-free"))
        return _result(check, ok, "accessibility cue found" if ok else "no accessibility cue")

    if cid == "dietary_covered":
        itinerary = plan.get("day_wise_itinerary") or []
        ok = _has_any(itinerary, ("vegetarian", "vegan", "jain", "halal", "kosher", "gluten-free"))
        return _result(check, ok, "dietary cue found" if ok else "dietary needs absent")

    if cid == "visa_checked":
        ok = _has_any(plan, ("visa", "entry requirement", "passport", "embassy", "iata"))
        return _result(check, ok, "visa/entry cue found" if ok else "missing visa/entry check")

    if cid == "closures_checked":
        ok = _has_any(plan, ("closed", "opening hours", "open hours", "hours checked"))
        return _result(check, ok, "opening-hours cue found" if ok else "missing closure check")

    if cid == "route_optimized":
        ok = _has_any(plan, ("optimized", "route", "travel time", "drive", "walk", "transit"))
        return _result(check, ok, "routing cue found" if ok else "missing routing/travel-time cue")

    if cid == "within_budget":
        limit = _budget_limit(prefs)
        cost = _cost(plan)
        ok = limit is not None and cost is not None and cost <= limit
        if limit is None:
            reason = "scenario has no budget limit"
        elif cost is None:
            reason = "plan has no numeric total_cost"
        else:
            reason = f"total_cost {cost:g} <= budget {limit:g}" if ok else f"total_cost {cost:g} > budget {limit:g}"
        return _result(check, ok, reason)

    if cid == "grounded_reply":
        if not final_reply:
            return _result(check, False, "missing final reply to ground")
        messages = [
            ToolMessage(content=content, tool_call_id=f"eval-{i}")
            for i, content in enumerate(scenario.evidence)
        ]
        issues = critique_grounding(final_reply, messages)
        return _result(check, not issues, "; ".join(issues) if issues else "reply grounded")

    return _result(check, False, f"unknown eval check id: {cid}")


SCENARIOS: tuple[EvalScenario, ...] = (
    EvalScenario(
        id="family_dubai_accessible",
        name="Dubai family trip with elderly parent",
        prompt=(
            "Plan a five-day Dubai trip for two adults, one seven-year-old, "
            "and my mother who needs elevators and short walks."
        ),
        prefs={
            "family_members": [
                {"relationship": "child", "age": 7},
                {"relationship": "parent", "age": 72, "mobility": "needs elevator"},
            ],
            "food_preferences": {"dietary": ["vegetarian"]},
        },
        checks=(
            EvalCheck("has_flights", "Includes flight selections"),
            EvalCheck("has_hotels", "Includes hotel selections"),
            EvalCheck("has_day_itinerary", "Includes a day-wise itinerary"),
            EvalCheck("kid_friendly", "Includes kid-friendly activities"),
            EvalCheck("mobility_accessible", "Addresses mobility/accessibility needs", weight=2),
            EvalCheck("dietary_covered", "Reflects dietary needs"),
            EvalCheck("route_optimized", "Includes travel-time or route planning"),
            EvalCheck("finalize_critic_clean", "Passes finalized-plan critic", weight=2),
        ),
    ),
    EvalScenario(
        id="visa_sensitive_paris",
        name="International trip requiring entry checks",
        prompt=(
            "Plan Paris from Mumbai for an Indian passport holder. Include "
            "entry requirements and avoid closed attractions."
        ),
        prefs={"profile": {"home_country": "India"}, "passport_country": "India"},
        checks=(
            EvalCheck("has_flights", "Includes flight selections"),
            EvalCheck("has_hotels", "Includes hotel selections"),
            EvalCheck("visa_checked", "Checks visa/entry requirements", weight=2),
            EvalCheck("closures_checked", "Checks attraction opening hours"),
            EvalCheck("has_day_itinerary", "Includes a day-wise itinerary"),
            EvalCheck("finalize_critic_clean", "Passes finalized-plan critic", weight=2),
        ),
    ),
    EvalScenario(
        id="budget_grounding_goa",
        name="Budget-capped Goa plan with grounded prices",
        prompt=(
            "Plan a Goa beach trip under INR 80000. Use only prices returned "
            "by tools in the final summary."
        ),
        prefs={"budget_level": "budget", "budget_limit": 80000},
        evidence=(
            "IndiGo DEL-GOI round trip: INR 18500",
            "Family Beach Resort Goa: INR 42000 total",
            "Spice plantation tour: INR 3500",
            "Airport transfer: INR 2500",
            "Trip total cost: INR 66500",
        ),
        checks=(
            EvalCheck("has_flights", "Includes flight selections"),
            EvalCheck("has_hotels", "Includes hotel selections"),
            EvalCheck("within_budget", "Keeps total cost within budget", weight=2),
            EvalCheck("grounded_reply", "Final reply only cites evidenced prices/times/URLs", weight=2),
            EvalCheck("finalize_critic_clean", "Passes finalized-plan critic"),
        ),
    ),
)


def scenario_by_id(scenario_id: str) -> EvalScenario:
    """Return a built-in scenario by id."""
    for scenario in SCENARIOS:
        if scenario.id == scenario_id:
            return scenario
    known = ", ".join(s.id for s in SCENARIOS)
    raise KeyError(f"Unknown eval scenario '{scenario_id}'. Known: {known}")


def format_result(result: EvalResult) -> str:
    """Render an eval result as compact human-readable text."""
    status = "PASS" if result.passed else "FAIL"
    lines = [
        f"{status} {result.scenario_id} — {result.scenario_name}",
        f"score: {result.score:.0%}",
    ]
    for check in result.checks:
        mark = "PASS" if check.passed else "FAIL"
        lines.append(f"- {mark} {check.id}: {check.reason}")
    return "\n".join(lines)


def _load_json_file(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Plan JSON must be an object.")
    return data


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for evaluating a saved plan JSON.

    Examples:
        python -m tripplanner.evals --list
        python -m tripplanner.evals family_dubai_accessible plan.json
    """
    parser = argparse.ArgumentParser(description="Evaluate a trip plan against built-in scenarios.")
    parser.add_argument("scenario", nargs="?", help="Scenario id to run.")
    parser.add_argument("plan_json", nargs="?", help="Path to a saved trip plan JSON file.")
    parser.add_argument(
        "--reply-file",
        default="",
        help="Optional file containing the final assistant reply to check for grounded claims.",
    )
    parser.add_argument("--list", action="store_true", help="List built-in scenario ids.")
    args = parser.parse_args(argv)

    if args.list:
        for scenario in SCENARIOS:
            print(f"{scenario.id}\t{scenario.name}")
        return 0

    if not args.scenario or not args.plan_json:
        parser.error("scenario and plan_json are required unless --list is used")

    try:
        scenario = scenario_by_id(args.scenario)
        plan = _load_json_file(args.plan_json)
        reply = ""
        if args.reply_file:
            with open(args.reply_file, encoding="utf-8") as f:
                reply = f.read()
        result = evaluate_plan(scenario, plan, final_reply=reply)
    except Exception as exc:
        print(f"eval error: {exc}", file=sys.stderr)
        return 2

    print(format_result(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
