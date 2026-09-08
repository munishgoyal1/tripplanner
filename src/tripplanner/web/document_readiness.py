"""Deterministic document readiness for a trip.

Every check here is computed in code from stored fields and trip dates. None of
it is inferred by a model, and none of it claims a per-country entry rule that
would need grounding — that belongs to ``tools/visa.py``. A check therefore
either states arithmetic ("this expiry is 38 days after your return") or states
an absence ("nothing on this account records a passport for Aarav").

Two rules keep it from crying wolf:

- **Silent unless the trip is known to cross a border.** Passport, visa, and
  IDP checks need ``origin_country`` and ``destination_country``, resolved by
  the caller. If either is unknown, or they match, none of those checks run —
  a domestic weekend must never raise paperwork. Crossing a border is not the
  same as needing a passport (Schengen, the India–Nepal and UK–Ireland
  arrangements), so a check states what it knows, that the trip leaves the
  origin country, and never asserts a document is required.
- **Absence warns, arithmetic blocks.** "No passport on file" means this
  account has no record, not that the traveller has no passport, so it can
  never be a blocker. An expiry that falls before the return date is proven,
  and blocks.
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


def _same_country(left: Any, right: Any) -> bool:
    """Loose country match, tolerant of "USA" against "United States"."""
    a = str(left or "").strip().casefold()
    b = str(right or "").strip().casefold()
    if not a or not b:
        return False
    return a == b or a in b or b in a


# Which countries a single visa admits you to. Membership is a short, slowly
# changing fact we can hold honestly; what the bloc *requires* is not, and stays
# with the official source.
_SCHENGEN = frozenset(
    {
        "austria", "belgium", "bulgaria", "croatia", "czechia", "czech republic",
        "denmark", "estonia", "finland", "france", "germany", "greece", "hungary",
        "iceland", "italy", "latvia", "liechtenstein", "lithuania", "luxembourg",
        "malta", "netherlands", "norway", "poland", "portugal", "romania",
        "slovakia", "slovenia", "spain", "sweden", "switzerland",
    }
)


def _same_bloc(left: Any, right: Any) -> bool:
    a = str(left or "").strip().casefold().removeprefix("the ")
    b = str(right or "").strip().casefold().removeprefix("the ")
    return bool(a) and bool(b) and a in _SCHENGEN and b in _SCHENGEN


def _pick_passport(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The passport the traveller would actually travel on.

    A dual national holds two, and one being expired says nothing about the
    trip. Prefer the latest expiry so a lapsed second passport cannot raise a
    blocker on a journey the valid one covers.
    """
    if not records:
        return None
    dated = [(_parse((r.get("fields") or {}).get("expiry")), r) for r in records]
    with_expiry = [(expiry, record) for expiry, record in dated if expiry is not None]
    if with_expiry:
        return max(with_expiry, key=lambda pair: pair[0])[1]
    return records[0]


def _pick_visa(
    records: list[dict[str, Any]], destination_country: str
) -> tuple[dict[str, Any] | None, str]:
    """The visa that applies to this destination, and how it was matched.

    A Japanese visa says nothing about a trip to Brazil, so a visa naming
    another country is ignored entirely — unless both sit in the same travel
    bloc, because a Schengen visa issued by France really does admit you to
    Portugal. A visa naming no country at all is still read — the user saved it
    for a reason — but it is returned as ``untagged``, so the caller can say so
    instead of asserting it.

    ``(None, "")`` means silence: no visa record is not evidence that one is
    needed.
    """
    untagged: dict[str, Any] | None = None
    bloc_match: dict[str, Any] | None = None
    for record in records:
        fields = record.get("fields") or {}
        named = str(
            fields.get("destination_country") or fields.get("issuing_country") or ""
        ).strip()
        if _same_country(fields.get("destination_country"), destination_country) or _same_country(
            fields.get("issuing_country"), destination_country
        ):
            return record, "direct"
        if named and bloc_match is None and _same_bloc(named, destination_country):
            bloc_match = record
        if not named and untagged is None:
            untagged = record
    if bloc_match is not None:
        return bloc_match, "bloc"
    return untagged, "untagged" if untagged is not None else ""


def _visa_checks(
    person: dict[str, str],
    records: list[dict[str, Any]],
    start: date,
    end: date,
    destination: str,
    destination_country: str,
) -> list[dict[str, Any]]:
    """What a visa the traveller already holds does, and does not, cover.

    Everything here is arithmetic over the saved record: whether its validity
    window contains the trip, and whether the trip outlasts the stay it permits.
    Nothing here decides whether a visa is needed at all.
    """
    visa, match = _pick_visa(records, destination_country)
    if visa is None:
        return []

    fields = visa.get("fields") or {}
    first = _first_name(person)
    certain = match in {"direct", "bloc"}
    severity = _BLOCKER if certain else _WARNING
    caveat = (
        ""
        if certain
        else " The saved visa does not say which country it is for, so check this is the "
        f"visa that matters for {destination}."
    )
    # Extraction fills whichever of the two the foil actually prints.
    valid_from = _parse(fields.get("valid_from"))
    valid_to = _parse(fields.get("valid_to")) or _parse(fields.get("expiry"))

    if valid_to is not None and valid_to < start:
        return [
            _check(
                f"visa-expired-{person['key']}",
                severity,
                f"{first}'s {destination} visa has expired",
                f"It ran out {_human(valid_to)}, before this trip starts on {_human(start)}."
                + caveat,
                "valid_to ≥ departure_date",
                person=person,
                action="Apply again before travelling.",
            )
        ]
    if valid_to is not None and valid_to < end:
        return [
            _check(
                f"visa-window-{person['key']}",
                severity,
                f"{first}'s visa ends before the trip does",
                f"It runs to {_human(valid_to)}; the trip ends {_human(end)}." + caveat,
                "valid_to ≥ return_date",
                person=person,
                action="Extend the visa or shorten the trip.",
            )
        ]
    if valid_from is not None and valid_from > start:
        return [
            _check(
                f"visa-window-{person['key']}",
                severity,
                f"{first}'s visa starts after the trip does",
                f"It is valid from {_human(valid_from)}; the trip starts {_human(start)}."
                + caveat,
                "valid_from ≤ departure_date",
                person=person,
            )
        ]

    trip_days = (end - start).days + 1
    max_stay = fields.get("max_stay_days")
    if isinstance(max_stay, int) and 0 < max_stay < trip_days:
        return [
            _check(
                f"visa-stay-limit-{person['key']}",
                severity,
                f"{first}'s visa allows a shorter stay than this trip",
                f"This trip is {trip_days} days; the visa permits {max_stay} days per entry."
                + caveat,
                "trip_length ≤ max_stay_days",
                person=person,
                action="Shorten the trip or check whether the stay can be extended.",
            )
        ]

    if not certain:
        return []

    detail = "The saved validity window contains every day of this trip."
    if match == "bloc":
        named = str(
            fields.get("destination_country") or fields.get("issuing_country") or ""
        ).strip()
        detail += f" It is a Schengen visa issued for {named}, which admits you to {destination}."
    if "single" in str(fields.get("entry_type") or "").lower():
        detail += (
            " It is single-entry, so it is spent on leaving — this planner cannot tell whether "
            "an earlier trip already used it."
        )
    return [
        _check(
            f"visa-ok-{person['key']}",
            _OK,
            f"{first}'s visa covers the trip dates",
            detail,
            "valid_from ≤ departure_date and valid_to ≥ return_date",
            person=person,
        )
    ]


def _passport_checks(
    person: dict[str, str],
    passport: dict[str, Any] | None,
    exit_date: date,
    destination: str,
    origin_country: str,
) -> list[dict[str, Any]]:
    first = _first_name(person)
    if passport is None:
        return [
            _check(
                f"passport-missing-{person['key']}",
                _WARNING,
                f"{first} has no passport on file",
                f"This trip leaves {origin_country}, and nothing on this account records a "
                "passport for this traveller, so no expiry check can run for them.",
                "trip leaves the origin country and no passport record exists",
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


def _is_official(source_domain: Any) -> bool:
    """Whether a finding is grounded well enough to stop a trip over."""
    domain = str(source_domain or "").strip().casefold()
    if not domain:
        return False
    if domain.endswith(".gov") or ".gov." in domain or domain.endswith(".gob.mx"):
        return True
    return any(
        trusted in domain
        for trusted in ("gov.uk", "canada.ca", "europa.eu", "iatatravelcentre.com")
    )


def _visa_lead_time_checks(
    trip: dict[str, Any],
    start: date,
    today: date,
    destination: str,
    covered: bool,
) -> list[dict[str, Any]]:
    """The one visa check that can honestly block: not enough time to apply.

    This is arithmetic between the processing time a source stated and the days
    left before departure, not a claim about whether a visa is required. When
    the traveller already holds a visa that covers the trip, none of it applies.
    """
    finding = trip.get("visa")
    if not isinstance(finding, dict) or not finding:
        return []

    status = str(finding.get("status") or "").strip().lower()
    checked_on = _parse(finding.get("checked_on"))
    stamp = f" Checked {_human(checked_on)}." if checked_on else ""
    url = str(finding.get("official_url") or "").strip()
    action = f"Apply here: {url}" if url else "Start the application."

    if status == "visa_free" and not covered:
        return [
            _check(
                "visa-not-needed",
                _OK,
                f"No visa needed for {destination}",
                str(finding.get("note") or "").strip()
                or f"The source checked says this passport enters {destination} visa-free."
                + stamp,
                "saved visa finding says visa_free",
            )
        ]

    if covered or status not in {"required", "e_visa"}:
        return []

    days_left = (start - today).days
    processing = finding.get("processing_days_typical")
    if not isinstance(processing, int) or processing <= 0:
        return [
            _check(
                "visa-needed",
                _WARNING,
                f"{destination} needs a visa you do not have on file",
                f"No processing time was recorded, so how long it takes is unknown.{stamp}",
                "visa finding says required, with no processing time to compare",
                action=action,
            )
        ]

    severity = _BLOCKER if _is_official(finding.get("source_domain")) else _WARNING
    if processing > days_left:
        return [
            _check(
                "visa-lead-time",
                severity,
                f"A {destination} visa takes longer than you have",
                f"It typically takes about {processing} days and you leave in {days_left}."
                + stamp,
                "processing_days_typical ≤ days_until_departure",
                action=action,
            )
        ]
    if processing * 3 > days_left * 2:
        return [
            _check(
                "visa-lead-time",
                _WARNING,
                f"The {destination} visa leaves little margin",
                f"It typically takes about {processing} days and you leave in {days_left}."
                + stamp,
                "processing_days_typical ≤ days_until_departure",
                action=action,
            )
        ]
    return [
        _check(
            "visa-needed",
            _WARNING,
            f"{destination} needs a visa you do not have on file",
            f"About {processing} days to process, and you leave in {days_left}.{stamp}",
            "visa finding says required, with time still in hand",
            action=action,
        )
    ]


def evaluate(
    trip: dict[str, Any],
    documents: list[dict[str, Any]],
    prefs: dict[str, Any],
    *,
    origin_country: str = "",
    destination_country: str = "",
    today: date | None = None,
) -> dict[str, Any]:
    """Compute every deterministic readiness check for one trip.

    ``origin_country`` and ``destination_country`` are resolved by the caller so
    this module stays pure and offline. Leaving them empty is safe: the checks
    that depend on crossing a border simply do not run.
    """
    from tripplanner.web.place_country import crosses_border

    start = _parse(trip.get("departure_date"))
    end = _parse(trip.get("return_date")) or start
    destination = str(trip.get("destination") or "your destination").strip()
    people = trip_travellers(trip, prefs)
    international = crosses_border(origin_country, destination_country)
    geography = {
        "origin_country": origin_country,
        "destination_country": destination_country,
        "crosses_border": international,
    }

    by_person: dict[str, list[dict[str, Any]]] = {}
    for record in documents:
        by_person.setdefault(str(record.get("traveller_key") or "self"), []).append(record)

    checks: list[dict[str, Any]] = []
    covered_keys: set[str] = set()
    if start is None or end is None:
        return {
            "destination": destination,
            "travellers": people,
            "checks": [],
            "blockers": 0,
            "warnings": 0,
            "badge": "",
            "badge_tone": "",
            "reason": "trip_dates_missing",
            **geography,
        }

    for person in people:
        owned = by_person.get(person["key"], [])
        by_type: dict[str, list[dict[str, Any]]] = {}
        for record in owned:
            by_type.setdefault(str(record.get("type") or ""), []).append(record)

        if international:
            checks.extend(
                _passport_checks(
                    person,
                    _pick_passport(by_type.get("passport", [])),
                    end,
                    destination,
                    origin_country,
                )
            )

        if international:
            visa_checks = _visa_checks(
                person,
                by_type.get("visa", []),
                start,
                end,
                destination,
                destination_country,
            )
            if any(check["id"].startswith("visa-ok-") for check in visa_checks):
                covered_keys.add(person["key"])
            checks.extend(visa_checks)

        for insurance in by_type.get("insurance", [])[:1]:
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

        licences = by_type.get("licence", [])
        licence_is_local = any(
            _same_country((record.get("fields") or {}).get("issuing_country"), destination_country)
            for record in licences
        )
        if international and licences and not licence_is_local and not by_type.get("idp"):
            checks.append(
                _check(
                    f"idp-missing-{person['key']}",
                    _WARNING,
                    f"{_first_name(person)} has a licence but no International Driving Permit",
                    "An IDP is issued separately from the licence. Where it is required, a rental "
                    "desk refuses the car without it.",
                    "licence issued outside the destination country, with no IDP record",
                    person=person,
                    action="Check whether "
                    f"{destination} requires one, and add it if you hold it.",
                )
            )

        # A stored expiry is arithmetic we can prove, so it is reported whether
        # or not the trip crosses a border. Loyalty tiers lapse without
        # consequence for travel, so they are not worth a badge.
        for record in owned:
            if record.get("type") in {"passport", "visa", "insurance", "loyalty"}:
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

    if international:
        checks.extend(
            _visa_lead_time_checks(
                trip,
                start,
                today or date.today(),
                destination,
                covered=bool(people) and covered_keys >= {person["key"] for person in people},
            )
        )

    blockers = sum(1 for check in checks if check["severity"] == _BLOCKER)
    warnings = sum(1 for check in checks if check["severity"] == _WARNING)
    if blockers:
        badge = f"{blockers} document{'s' if blockers != 1 else ''} to fix"
        badge_tone = _BLOCKER
    elif warnings:
        badge = f"{warnings} document{'s' if warnings != 1 else ''} to check"
        badge_tone = _WARNING
    else:
        badge = ""
        badge_tone = ""

    return {
        "destination": destination,
        "travellers": people,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "badge": badge,
        "badge_tone": badge_tone,
        **geography,
    }
