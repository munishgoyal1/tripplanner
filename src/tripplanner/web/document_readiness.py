"""Deterministic document readiness for a trip.

Every check here is computed in code from stored fields and trip dates. None of
it is inferred by a model, and none of it claims a per-country entry rule that
would need grounding — that belongs to ``tools/visa.py``. A check therefore
either states arithmetic ("this expiry is 38 days after your return") or states
an absence ("nothing on this account records a passport for Aarav").
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# The conservative validity margin applied to every destination. The exact
# requirement varies (Schengen asks for three months, many others for six), so
# the check states the margin it used and points at the official source rather
# than pretending to know the rule for this destination.
PASSPORT_VALIDITY_MONTHS = 6

_BLOCKER = "blocker"
_WARNING = "warning"
_OK = "ok"


def _parse(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _add_months(anchor: date, months: int) -> date:
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
                           31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _human(value: date) -> str:
    return value.strftime("%d %b %Y")


def trip_travellers(trip: dict[str, Any], prefs: dict[str, Any]) -> list[dict[str, str]]:
    """Who this trip's paperwork is checked against.

    The account holder is always included. A family member joins only when the
    trip's ``travelers`` text names them, so a solo trip is never blocked on a
    relative's missing passport.
    """
    from tripplanner.web.travel_documents import traveller_key

    profile = prefs.get("profile") if isinstance(prefs.get("profile"), dict) else {}
    people = [
        {
            "key": "self",
            "name": str(profile.get("display_name") or "You").strip() or "You",
            "relationship": "You",
        }
    ]
    named = str(trip.get("travelers") or "").lower()
    for member in prefs.get("family_members") or []:
        if not isinstance(member, dict):
            continue
        name = str(member.get("name") or "").strip()
        if not name or name.lower().split()[0] not in named:
            continue
        people.append(
            {
                "key": traveller_key(member.get("relationship"), name),
                "name": name,
                "relationship": str(member.get("relationship") or "").strip(),
            }
        )
    return people


def _check(
    check_id: str,
    severity: str,
    title: str,
    detail: str,
    rule: str,
    *,
    person: dict[str, str] | None = None,
    action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "severity": severity,
        "traveller_key": (person or {}).get("key", ""),
        "traveller_name": (person or {}).get("name", ""),
        "title": title,
        "detail": detail,
        "rule": rule,
        "origin": "computed",
        "action": action,
    }


def _first_name(person: dict[str, str]) -> str:
    return person["name"].split()[0] if person["name"] else "This traveller"


def _passport_checks(
    person: dict[str, str], passport: dict[str, Any] | None, exit_date: date, destination: str
) -> list[dict[str, Any]]:
    first = _first_name(person)
    if passport is None:
        return [
            _check(
                f"passport-missing-{person['key']}",
                _BLOCKER,
                f"{first} has no passport on file",
                "Nothing on this account records a passport for this traveller, "
                "so no entry check can run for them.",
                "every traveller on the trip has a passport record",
                person=person,
                action="Add their passport details.",
            )
        ]

    expiry = _parse((passport.get("fields") or {}).get("expiry"))
    if expiry is None:
        return [
            _check(
                f"passport-expiry-unknown-{person['key']}",
                _WARNING,
                f"{first}'s passport has no expiry date",
                "The saved passport record has no expiry, so its validity cannot be checked.",
                "passport record has an expiry date",
                person=person,
                action="Add the expiry date.",
            )
        ]

    margin_days = (expiry - exit_date).days
    required = _add_months(exit_date, PASSPORT_VALIDITY_MONTHS)
    if expiry <= exit_date:
        return [
            _check(
                f"passport-expired-{person['key']}",
                _BLOCKER,
                f"{first}'s passport expires before the trip ends",
                f"It expires {_human(expiry)}, {abs(margin_days)} days before you return "
                f"on {_human(exit_date)}.",
                "expiry > return_date",
                person=person,
                action="Renew it before travelling.",
            )
        ]
    if expiry < required:
        return [
            _check(
                f"passport-margin-{person['key']}",
                _BLOCKER,
                f"{first}'s passport is close to expiry for {destination}",
                f"It expires {_human(expiry)}, which is {margin_days} days after you return on "
                f"{_human(exit_date)}. Most destinations ask for "
                f"{PASSPORT_VALIDITY_MONTHS} months of validity beyond your return; confirm "
                f"the exact rule with the {destination} mission.",
                f"expiry − return_date ≥ {PASSPORT_VALIDITY_MONTHS} months",
                person=person,
                action="Renewal takes weeks. Start it now or move the trip.",
            )
        ]
    return [
        _check(
            f"passport-ok-{person['key']}",
            _OK,
            f"{first}'s passport is valid for this trip",
            f"It expires {_human(expiry)}, {margin_days} days after you return.",
            f"expiry − return_date ≥ {PASSPORT_VALIDITY_MONTHS} months",
            person=person,
        )
    ]


def _window_check(
    check_id: str,
    person: dict[str, str],
    record: dict[str, Any],
    start: date,
    end: date,
    *,
    label: str,
    severity: str,
) -> dict[str, Any] | None:
    fields = record.get("fields") or {}
    valid_from = _parse(fields.get("valid_from"))
    valid_to = _parse(fields.get("valid_to"))
    first = _first_name(person)
    if valid_to is not None and valid_to < end:
        return _check(
            check_id,
            severity,
            f"{first}'s {label} ends before the trip does",
            f"Cover runs to {_human(valid_to)}; the trip ends {_human(end)}.",
            "valid_to ≥ return_date",
            person=person,
            action=f"Extend the {label} or shorten the trip.",
        )
    if valid_from is not None and valid_from > start:
        return _check(
            check_id,
            severity,
            f"{first}'s {label} starts after the trip does",
            f"Cover starts {_human(valid_from)}; the trip starts {_human(start)}.",
            "valid_from ≤ departure_date",
            person=person,
            action=f"Move the {label} start date.",
        )
    return None


def evaluate(
    trip: dict[str, Any], documents: list[dict[str, Any]], prefs: dict[str, Any]
) -> dict[str, Any]:
    """Compute every deterministic readiness check for one trip."""
    start = _parse(trip.get("departure_date"))
    end = _parse(trip.get("return_date")) or start
    destination = str(trip.get("destination") or "your destination").strip()
    people = trip_travellers(trip, prefs)

    by_person: dict[str, list[dict[str, Any]]] = {}
    for record in documents:
        by_person.setdefault(str(record.get("traveller_key") or "self"), []).append(record)

    checks: list[dict[str, Any]] = []
    if start is None or end is None:
        return {
            "destination": destination,
            "travellers": people,
            "checks": [],
            "blockers": 0,
            "warnings": 0,
            "badge": "",
            "reason": "trip_dates_missing",
        }

    for person in people:
        owned = by_person.get(person["key"], [])
        of_type = {record.get("type"): record for record in owned}

        checks.extend(_passport_checks(person, of_type.get("passport"), end, destination))

        visa = of_type.get("visa")
        if visa is not None:
            window = _window_check(
                f"visa-window-{person['key']}",
                person,
                visa,
                start,
                end,
                label="visa",
                severity=_BLOCKER,
            )
            checks.append(
                window
                or _check(
                    f"visa-ok-{person['key']}",
                    _OK,
                    f"{_first_name(person)}'s visa covers the trip dates",
                    "The saved validity window contains every day of this trip.",
                    "valid_from ≤ departure_date and valid_to ≥ return_date",
                    person=person,
                )
            )

        insurance = of_type.get("insurance")
        if insurance is not None:
            window = _window_check(
                f"insurance-window-{person['key']}",
                person,
                insurance,
                start,
                end,
                label="insurance",
                severity=_WARNING,
            )
            if window is not None:
                checks.append(window)

        if of_type.get("licence") is not None and of_type.get("idp") is None:
            checks.append(
                _check(
                    f"idp-missing-{person['key']}",
                    _WARNING,
                    f"{_first_name(person)} has a licence but no International Driving Permit",
                    "An IDP is issued separately from the licence. Where it is required, a rental "
                    "desk refuses the car without it.",
                    "licence record without a matching IDP record",
                    person=person,
                    action="Check whether "
                    f"{destination} requires one, and add it if you hold it.",
                )
            )

        for record in owned:
            if record.get("type") in {"passport", "visa", "insurance"}:
                continue
            expiry = _parse((record.get("fields") or {}).get("expiry"))
            if expiry is not None and expiry < end:
                from tripplanner.web.travel_documents import TYPE_LABELS

                label = TYPE_LABELS.get(str(record.get("type")), "document")
                checks.append(
                    _check(
                        f"expiring-{record.get('id')}",
                        _WARNING,
                        f"{_first_name(person)}'s {label.lower()} expires during the trip",
                        f"It expires {_human(expiry)}, before you return on {_human(end)}.",
                        "expiry ≥ return_date",
                        person=person,
                    )
                )

    blockers = sum(1 for check in checks if check["severity"] == _BLOCKER)
    warnings = sum(1 for check in checks if check["severity"] == _WARNING)
    if blockers:
        badge = f"{blockers} document{'s' if blockers != 1 else ''} to fix"
    elif warnings:
        badge = f"{warnings} document{'s' if warnings != 1 else ''} to check"
    else:
        badge = ""

    return {
        "destination": destination,
        "travellers": people,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "badge": badge,
    }
