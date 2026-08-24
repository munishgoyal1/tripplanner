"""What the planner checked, what it found, and what it could not check.

``trip_guard`` answers "is anything wrong". That is not the same question a
traveller asks, which is "did you actually look". Today silence means both
"verified fine" and "never fetched a fact", and those must not look alike: an
itinerary the planner could not evaluate is exactly the itinerary that earned
this category its reputation for confident nonsense.

So every check reports one of three states. ``failed`` comes straight from the
invariant. ``passed`` requires that the facts the invariant depends on were
present for every stop it applies to. Anything else is ``unverified``, named
down to the stop and the missing fact.

Derived on read, never persisted: a certificate stored beside a trip would
outlive the itinerary it describes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from tripplanner.tools import trip_guard
from tripplanner.tools.trip_common import _coords_from_summary, _stop_kind, _stop_name
from tripplanner.web import holidays, place_country

Status = Literal["passed", "failed", "unverified"]

_PLACE_KINDS = frozenset({"attraction", "meal"})
_VISITABLE_KINDS = frozenset({"attraction", "meal", "hotel"})
_TRANSPORT_KINDS = frozenset({"flight", "transport"})

#: Facts a stop can be missing, in the words used to tell the user about it.
_FACT_LABELS = {
    "location": "location",
    "hours": "opening hours",
    "status": "business status",
    "time": "a start time",
    "date": "a calendar date",
}

#: A finding is only as strong as what decided it. Contradictions come from a
#: fetched fact and are worth interrupting for. Advisories come from straight-
#: line distance and an assumed road speed, so they may speak but must not
#: accuse. Coverage is the guard reporting that it went blind, which is the
#: definition of unverified rather than a fault in the plan.
CONTRADICTION_CODES = frozenset({"I1", "I2", "I3", "I6", "I7", "I11", "I12", "I13"})
ADVISORY_CODES = frozenset({"I4", "I5", "I9"})
COVERAGE_CODES = frozenset({"I10"})

#: What each invariant needs before its silence may be read as a pass, and which
#: stops it applies to. Keeping this beside the guard rather than inside it is
#: deliberate: the guard decides truth, this decides how much to claim.
_REQUIREMENTS: dict[str, tuple[frozenset[str], frozenset[str] | None]] = {
    "I1": (frozenset({"envelope", "time"}), None),
    "I2": (frozenset({"envelope"}), None),
    "I3": (frozenset({"hours", "time"}), _PLACE_KINDS),
    "I4": (frozenset({"location", "time"}), None),
    "I5": (frozenset({"time"}), _TRANSPORT_KINDS),
    "I6": (frozenset({"envelope"}), None),
    "I7": (frozenset({"envelope"}), None),
    "I9": (frozenset({"location"}), None),
    "I10": (frozenset(), None),
    "I11": (frozenset({"hours", "date"}), _PLACE_KINDS),
    "I12": (frozenset({"status"}), _VISITABLE_KINDS),
    "I13": (frozenset(), None),
}


@dataclass(frozen=True)
class StopFacts:
    """Which facts one stop actually carries, for the day it sits on."""

    day: int
    name: str
    kind: str
    has_location: bool
    has_hours: bool
    has_status: bool
    has_time: bool
    has_date: bool
    holiday: str = ""

    def missing(self, needed: frozenset[str]) -> list[str]:
        present = {
            "location": self.has_location,
            "hours": self.has_hours,
            "status": self.has_status,
            "time": self.has_time,
            "date": self.has_date,
        }
        labels: list[str] = []
        for fact in sorted(needed):
            if fact not in present or present[fact]:
                continue
            if fact == "hours" and self.holiday:
                labels.append(f"opening hours on {self.holiday}")
            else:
                labels.append(_FACT_LABELS[fact])
        return labels


def _holiday_by_day(plan: dict[str, Any], dates: dict[int, str]) -> dict[int, str]:
    """Named public holidays among the trip's days, where they can be known.

    An unreadable calendar leaves the weekly hours standing. Retracting a fact
    we did fetch because a second source was unreachable would make every trip
    look unverified without telling the traveller anything.
    """
    destination = str(plan.get("destination") or "").strip()
    if not destination or not dates:
        return {}
    code = place_country.resolve_country_code(destination)
    if not code:
        return {}
    found: dict[int, str] = {}
    for day, day_iso in dates.items():
        name = holidays.holiday_on(code, day_iso)
        if name:
            found[day] = name
    return found


def _collect_stop_facts(plan: dict[str, Any]) -> tuple[list[StopFacts], dict[int, str]]:
    destination = str(plan.get("destination") or "")
    dates = trip_guard.day_dates(plan)
    holiday_by_day = _holiday_by_day(plan, dates)
    out: list[StopFacts] = []
    for day, _entry, stops in trip_guard.days_of(plan):
        day_iso = dates.get(day, "")
        holiday = holiday_by_day.get(day, "")
        for stop in stops:
            name = _stop_name(stop)
            if not name:
                continue
            kind = _stop_kind(stop)
            is_place = kind not in _TRANSPORT_KINDS
            summary = trip_guard._summary_for_place(name, destination) if is_place else {}
            facts = trip_guard.facts_for(name, destination) if is_place else None
            known_hours = facts is not None and facts.hours_on(day_iso) is not None
            out.append(
                StopFacts(
                    day=day,
                    name=name,
                    kind=kind,
                    has_location=bool(_coords_from_summary(summary)) if is_place else True,
                    has_hours=known_hours and not holiday,
                    has_status=bool(facts and facts.business_status),
                    has_time=trip_guard._time_of(stop) is not None,
                    has_date=bool(day_iso),
                    holiday=holiday if known_hours else "",
                )
            )
    return out, holiday_by_day


def _envelope_known(plan: dict[str, Any]) -> bool:
    env = trip_guard.envelope(plan)
    return env.bounded_start or env.bounded_end


def _gaps_for(
    code: str, stop_facts: list[StopFacts], envelope_known: bool
) -> list[dict[str, Any]]:
    needed, kinds = _REQUIREMENTS[code]
    if "envelope" in needed and not envelope_known:
        return [{"name": "", "day": None, "missing": ["the trip's arrival and departure"]}]
    gaps: list[dict[str, Any]] = []
    for stop in stop_facts:
        if kinds is not None and stop.kind not in kinds:
            continue
        missing = stop.missing(needed)
        if missing:
            gaps.append({"name": stop.name, "day": stop.day, "missing": missing})
    return gaps


def build_verification(plan: dict[str, Any] | None) -> dict[str, Any]:
    """The full certificate for one plan: per check, per day, and per stop."""
    plan = plan or {}
    if not trip_guard.days_of(plan):
        return {
            "verdict": "unverified",
            "counts": {"total": 0, "passed": 0, "failed": 0, "unverified": 0},
            "checks": [],
            "days": [],
            "unverified_stops": [],
            "freshness": None,
        }

    violations = trip_guard.validate_plan(plan)
    stop_facts, holiday_by_day = _collect_stop_facts(plan)
    envelope_known = _envelope_known(plan)

    by_code: dict[str, list[trip_guard.Violation]] = {}
    for violation in violations:
        by_code.setdefault(violation.code, []).append(violation)

    checks: list[dict[str, Any]] = []
    unverified_stops: dict[tuple[str, int | None], set[str]] = {}
    for code, rule, statement in trip_guard.INVARIANTS:
        if code not in _REQUIREMENTS:
            continue
        found = by_code.get(code, [])
        gaps = _gaps_for(code, stop_facts, envelope_known)
        if found and code in COVERAGE_CODES:
            # "I could not check" is not a fault in the itinerary.
            status: Status = "unverified"
            gaps = [
                {"name": "", "day": None, "missing": [violation.message]}
                for violation in found
            ]
            found = []
        elif found:
            status = "failed"
        elif gaps:
            status = "unverified"
        else:
            status = "passed"
        if status == "unverified":
            for gap in gaps:
                if not gap["name"]:
                    continue
                key = (str(gap["name"]), gap["day"])
                unverified_stops.setdefault(key, set()).update(gap["missing"])
        checks.append(
            {
                "code": code,
                "rule": rule,
                "statement": statement,
                "status": status,
                "severity": (
                    "advisory" if code in ADVISORY_CODES else "contradiction"
                ),
                "findings": [violation.message for violation in found],
                "gaps": gaps,
            }
        )

    counts = {
        "total": len(checks),
        "passed": sum(1 for check in checks if check["status"] == "passed"),
        "failed": sum(1 for check in checks if check["status"] == "failed"),
        "unverified": sum(1 for check in checks if check["status"] == "unverified"),
    }
    contradicted = any(
        check["status"] == "failed" and check["code"] in CONTRADICTION_CODES
        for check in checks
    )
    if contradicted:
        verdict = "issues"
    elif counts["failed"]:
        verdict = "advisories"
    elif counts["unverified"]:
        verdict = "partial"
    else:
        verdict = "clear"

    return {
        "verdict": verdict,
        "counts": counts,
        "checks": checks,
        "days": _day_rows(plan, violations, unverified_stops, holiday_by_day),
        "unverified_stops": [
            {"name": name, "day": day, "missing": sorted(missing)}
            for (name, day), missing in sorted(
                unverified_stops.items(), key=lambda item: (item[0][1] or 0, item[0][0])
            )
        ],
        "freshness": (
            dict(plan["place_facts_refresh"])
            if isinstance(plan.get("place_facts_refresh"), dict)
            else None
        ),
    }


def _day_rows(
    plan: dict[str, Any],
    violations: list[trip_guard.Violation],
    unverified_stops: dict[tuple[str, int | None], set[str]],
    holiday_by_day: dict[int, str],
) -> list[dict[str, Any]]:
    unverified_by_day: dict[int | None, set[str]] = {}
    for (name, day), _missing in unverified_stops.items():
        unverified_by_day.setdefault(day, set()).add(name)

    rows: list[dict[str, Any]] = []
    advisory_only = {
        item.message for item in violations if item.code in ADVISORY_CODES
    }
    for day, _entry, _stops in trip_guard.days_of(plan):
        findings = [
            item.message
            for item in violations
            if item.day == day and item.code in CONTRADICTION_CODES
        ]
        advisories = [
            item.message
            for item in violations
            if item.day == day and item.message in advisory_only
        ]
        unverified = sorted(unverified_by_day.get(day, set()))
        if findings:
            status: Status = "failed"
        elif unverified:
            status = "unverified"
        else:
            status = "passed"
        rows.append(
            {
                "day": day,
                "status": status,
                "findings": findings,
                "advisories": advisories,
                "unverified": unverified,
                "holiday": holiday_by_day.get(day, ""),
            }
        )
    return rows
