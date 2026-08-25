"""Deliberate damage, and the way the report must answer it.

A rule set can only be trusted if breaking a trip makes it say more. These
mutations are the break, and the relations below are the answer they demand.
Nothing here asserts what a plan *should* report -- only how the report must
move when the plan gets worse, which is a property we can check without knowing
the right answer for any particular trip.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from tripplanner.tools.trip_guard import leg_touches_home
from tripplanner.validation.checks import check_record
from tripplanner.validation.corpus import MUTATED, CorpusRecord
from tripplanner.validation.findings import Finding, symptom_of
from tripplanner.web.transport import _transport_route_endpoints

#: Makes the plan contradict itself without taking anything out of it.
DEGRADING = "degrading"
#: Takes something out, so its own complaints legitimately go with it.
REMOVAL = "removal"
#: Changes nothing a rule may depend on.
NEUTRAL = "neutral"

RULE_QUIETER = "M1"
RULE_UNNOTICED = "M2"
RULE_UNSTABLE = "M3"

METAMORPHIC_RULES: tuple[tuple[str, str], ...] = (
    (RULE_QUIETER, "Making a trip worse must never make the report quieter."),
    (RULE_UNNOTICED, "Removing part of a trip must be noticed by some rule."),
    (RULE_UNSTABLE, "An edit that changes nothing must change no finding."),
)


@dataclass(frozen=True)
class Mutation:
    name: str
    kind: str
    plan: dict[str, Any]


def _days(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [day for day in plan.get("day_wise_itinerary") or [] if isinstance(day, dict)]


def _is_leg(stop: Any) -> bool:
    if not isinstance(stop, dict) or str(stop.get("kind") or "") not in {
        "flight",
        "transport",
    }:
        return False
    return _transport_route_endpoints(str(stop.get("name") or "")) is not None


def _home_leg(
    plan: dict[str, Any], *, leaves_home: bool
) -> tuple[list[Any], int] | None:
    origin = str(plan.get("origin") or "").strip()
    matches: list[tuple[list[Any], int]] = []
    for day in _days(plan):
        stops = day.get("stops")
        if not isinstance(stops, list):
            continue
        for index, stop in enumerate(stops):
            if not _is_leg(stop):
                continue
            outbound, homebound = leg_touches_home(stop, origin)
            if outbound if leaves_home else homebound:
                matches.append((stops, index))
    return matches[0] if len(matches) == 1 else None


def blank_origin(plan: dict[str, Any]) -> Mutation | None:
    """The mutation that caught a guard going dark on 2026-08-13."""
    if not str(plan.get("origin") or "").strip():
        return None
    mutated = copy.deepcopy(plan)
    mutated["origin"] = ""
    return Mutation("blank-origin", REMOVAL, mutated)


def drop_first_leg(plan: dict[str, Any]) -> Mutation | None:
    mutated = copy.deepcopy(plan)
    match = _home_leg(mutated, leaves_home=True)
    if match is None:
        return None
    stops, index = match
    stops.pop(index)
    return Mutation("drop-first-leg", REMOVAL, mutated)


def drop_last_leg(plan: dict[str, Any]) -> Mutation | None:
    mutated = copy.deepcopy(plan)
    match = _home_leg(mutated, leaves_home=False)
    if match is None:
        return None
    stops, index = match
    stops.pop(index)
    return Mutation("drop-last-leg", REMOVAL, mutated)


def reverse_days(plan: dict[str, Any]) -> Mutation | None:
    """Keep every day, run the trip backwards: the same content, incoherent."""
    days = _days(plan)
    if len(days) < 3:
        return None
    mutated = copy.deepcopy(plan)
    entries = _days(mutated)
    stops = [day.get("stops") for day in entries]
    for day, reversed_stops in zip(entries, reversed(stops)):
        day["stops"] = reversed_stops
    return Mutation("reverse-days", DEGRADING, mutated)


def break_time_order(plan: dict[str, Any]) -> Mutation | None:
    """Send the day's last stop back to dawn, before everything it follows."""
    mutated = copy.deepcopy(plan)
    for day in _days(mutated):
        stops = [stop for stop in (day.get("stops") or []) if isinstance(stop, dict)]
        timed = [stop for stop in stops if str(stop.get("time") or "").strip()]
        if len(timed) < 3:
            continue
        timed[-1]["time"] = "00:05"
        return Mutation("break-time-order", DEGRADING, mutated)
    return None


def strand_a_stop(plan: dict[str, Any]) -> Mutation | None:
    """Move a stop to a day it cannot be reached from."""
    days = _days(plan)
    if len(days) < 3:
        return None
    mutated = copy.deepcopy(plan)
    entries = _days(mutated)
    source = entries[0].get("stops")
    target = entries[-1].get("stops")
    if not isinstance(source, list) or not isinstance(target, list):
        return None
    for index, stop in enumerate(source):
        if isinstance(stop, dict) and str(stop.get("kind") or "") == "attraction":
            target.append(source.pop(index))
            return Mutation("strand-a-stop", DEGRADING, mutated)
    return None


def reorder_keys(plan: dict[str, Any]) -> Mutation | None:
    """Same plan, different key order: no rule may notice."""
    mutated = {key: copy.deepcopy(plan[key]) for key in sorted(plan, reverse=True)}
    return Mutation("reorder-keys", NEUTRAL, mutated)


def add_unrelated_note(plan: dict[str, Any]) -> Mutation | None:
    mutated = copy.deepcopy(plan)
    mutated["audit_scratch_field"] = "ignored by every rule"
    return Mutation("add-unrelated-note", NEUTRAL, mutated)


MUTATORS: tuple[Callable[[dict[str, Any]], Mutation | None], ...] = (
    blank_origin,
    drop_first_leg,
    drop_last_leg,
    reverse_days,
    break_time_order,
    strand_a_stop,
    reorder_keys,
    add_unrelated_note,
)


def mutations_of(plan: dict[str, Any]) -> list[Mutation]:
    """Every mutation this plan can carry, in a fixed order."""
    produced: list[Mutation] = []
    for mutate in MUTATORS:
        mutation = mutate(plan)
        if mutation is not None:
            produced.append(mutation)
    return produced


def _shapes(findings: list[Finding]) -> set[str]:
    return {finding.key for finding in findings}


def check_metamorphic(record: CorpusRecord) -> list[Finding]:
    """Break this trip every way we know, and hold the report to its answer."""
    before = check_record(record)
    reported: list[Finding] = []

    for mutation in mutations_of(record.plan):
        mutant = replace(
            record,
            id=f"{record.id}~{mutation.name}",
            provenance=MUTATED,
            plan=mutation.plan,
        )
        after = check_record(mutant)
        names = [record.destination, str(record.plan.get("origin") or "")]

        if mutation.kind == DEGRADING and len(after) < len(before):
            message = (
                f"{mutation.name} made the trip worse, and the report went from "
                f"{len(before)} to {len(after)} findings."
            )
            reported.append(
                Finding(RULE_QUIETER, symptom_of(message, names), message,
                        record.id, record.provenance)
            )
        if mutation.kind == REMOVAL and not (_shapes(after) - _shapes(before)):
            message = f"{mutation.name} removed part of the trip and no rule noticed."
            reported.append(
                Finding(RULE_UNNOTICED, symptom_of(message, names), message,
                        record.id, record.provenance)
            )
        if mutation.kind == NEUTRAL and _shapes(after) != _shapes(before):
            changed = sorted(_shapes(after) ^ _shapes(before))[:1]
            message = (
                f"{mutation.name} changed nothing that matters, yet the report "
                f"moved on {changed[0] if changed else 'a rule'}."
            )
            reported.append(
                Finding(RULE_UNSTABLE, symptom_of(message, names), message,
                        record.id, record.provenance)
            )
    return reported
