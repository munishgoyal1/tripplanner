"""Checks over a stored plan, run with the facts that plan was rendered from.

Every check is the production rule, not a copy of it. The audit's job is to run
the real guard over far more trips than a person can open, so a rule that lives
here and nowhere else would be testing itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from tripplanner.validation.corpus import CorpusRecord
from tripplanner.validation.findings import Finding, symptom_of

GAP_RULE = "gap"


def _place_lookup(places: dict[str, Any]):
    """Serve cached ``name|city`` entries as the guard's place-summary source."""
    by_name: dict[str, Any] = {}
    for key, entry in places.items():
        name, _, _city = str(key).partition("|")
        by_name.setdefault(name.strip().lower(), entry or {})

    def summary(name: str, city: str = "", **_kwargs: Any) -> dict[str, Any]:
        wanted = str(name or "").strip().lower()
        exact = places.get(f"{wanted}|{str(city or '').strip().lower()}")
        return dict(exact or by_name.get(wanted) or {})

    return summary


@contextmanager
def place_facts(places: dict[str, Any]) -> Iterator[None]:
    """Answer place lookups from the record instead of a provider.

    Always patched, even when the record carries no facts: leaving the real
    lookup in place sent the audit to the provider over the network, which is
    slow, costs money, and is the opposite of an offline check. With no facts
    the geography rules degrade to silence, which is what they are meant to do.
    """
    from tripplanner.tools import trip_common, trip_effort, trip_guard

    modules = (trip_common, trip_guard, trip_effort)
    lookup = _place_lookup(places)
    originals = [getattr(module, "_summary_for_place", None) for module in modules]
    for module in modules:
        if hasattr(module, "_summary_for_place"):
            module._summary_for_place = lookup  # type: ignore[attr-defined]
    try:
        yield
    finally:
        for module, original in zip(modules, originals):
            if original is not None:
                module._summary_for_place = original  # type: ignore[attr-defined]


def plan_names(plan: dict[str, Any]) -> list[str]:
    """Every proper name in the plan, so a symptom can be stripped of them."""
    names = {str(plan.get("destination") or ""), str(plan.get("origin") or "")}
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                names.add(str(stop.get("name") or ""))
            elif isinstance(stop, str):
                names.add(stop)
    for bucket in ("selected_hotels", "selected_activities", "selected_flights"):
        for item in plan.get(bucket) or []:
            if isinstance(item, dict):
                names.add(str(item.get("name") or ""))
    return [name for name in names if name]


def check_record(record: CorpusRecord) -> list[Finding]:
    """Every rule the production system would apply to this plan."""
    from tripplanner.tools.trip_guard import validate_plan
    from tripplanner.tools.trip_validation import planning_completion_gaps

    names = plan_names(record.plan)
    findings: list[Finding] = []
    with place_facts(record.places):
        violations = validate_plan(record.plan)
        gaps = planning_completion_gaps(record.plan)

    for violation in violations:
        findings.append(
            Finding(
                rule=violation.code,
                symptom=symptom_of(violation.message, names),
                message=violation.message,
                record_id=record.id,
                provenance=record.provenance,
                day=violation.day,
            )
        )
    # The completion gate quotes the invariants back at the model, so reporting
    # both would count one defect twice and bury the rest.
    reported = [violation.message for violation in violations]
    for gap in gaps:
        if any(message and message in gap for message in reported):
            continue
        findings.append(
            Finding(
                rule=GAP_RULE,
                symptom=symptom_of(gap, names),
                message=gap,
                record_id=record.id,
                provenance=record.provenance,
            )
        )
    return findings
