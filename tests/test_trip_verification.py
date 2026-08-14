"""The certificate must never claim more than the planner actually checked.

These tests exist for one failure mode: a check reported as passed when the fact
it depends on was never fetched. That is the failure the whole feature is meant
to make impossible, so most of what follows is about the unverified state rather
than the happy path.
"""

from __future__ import annotations

import pytest

from tripplanner.tools import trip_common, trip_effort, trip_guard
from tripplanner.web import trip_verification

_COORDS = {
    "Rajwada Palace": (22.7177, 75.8545),
    "Lal Bagh Palace": (22.6944, 75.8452),
    "Hotel Sayaji": (22.7250, 75.8800),
}

_EVERY_DAY = [f"{day}: 10:00 AM - 5:00 PM" for day in (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
)]
#: Rajwada keeps the Tuesday closure; everything else is open all week.
_CLOSED_TUESDAY = [
    "Tuesday: Closed" if line.startswith("Tuesday") else line for line in _EVERY_DAY
]

_HOURS = {
    "Rajwada Palace": _CLOSED_TUESDAY,
    "Lal Bagh Palace": _EVERY_DAY,
    "Hotel Sayaji": _EVERY_DAY,
}


def plan(days: list[list[dict[str, object]]], **extra: object) -> dict[str, object]:
    return {
        "origin": "Bengaluru",
        "destination": "Indore",
        "departure_date": "2026-08-10",  # a Monday
        "day_wise_itinerary": [
            {"day": index + 1, "stops": stops} for index, stops in enumerate(days)
        ],
        **extra,
    }


def stop(name: str, time: str, kind: str = "attraction", minutes: int = 90) -> dict[str, object]:
    return {"name": name, "kind": kind, "time": time, "duration_min": minutes}


def _use_summaries(
    monkeypatch: pytest.MonkeyPatch, summaries: dict[str, dict[str, object]]
) -> None:
    def summary(name: str, _destination: str = "") -> dict[str, object]:
        return dict(summaries.get(name, {}))

    for module in (trip_common, trip_guard, trip_effort):
        monkeypatch.setattr(module, "_summary_for_place", summary, raising=False)


@pytest.fixture
def fully_known(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every stop has coordinates, hours and a business status."""
    _use_summaries(
        monkeypatch,
        {
            name: {
                "lat": coords[0],
                "lng": coords[1],
                "business_status": "OPERATIONAL",
                "weekday_descriptions": _HOURS[name],
            }
            for name, coords in _COORDS.items()
        },
    )


@pytest.fixture
def nothing_known(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_summaries(monkeypatch, {})


_SOUND = plan(
    [
        [
            stop("Flight Bengaluru → Indore", "09:00", "flight", 120),
            stop("Hotel Sayaji", "13:00", "hotel", 45),
        ],
        [
            stop("Hotel Sayaji", "08:00", "hotel", 45),
            stop("Lal Bagh Palace", "11:00"),
        ],
        [
            stop("Rajwada Palace", "11:00"),
            stop("Flight Indore → Bengaluru", "18:00", "flight", 120),
        ],
    ]
)


def test_a_trip_with_no_itinerary_claims_nothing() -> None:
    report = trip_verification.build_verification({"destination": "Indore"})
    assert report["verdict"] == "unverified"
    assert report["checks"] == []
    assert report["counts"]["total"] == 0


def test_missing_facts_never_read_as_a_pass(nothing_known: None) -> None:
    report = trip_verification.build_verification(_SOUND)
    statuses = {check["code"]: check["status"] for check in report["checks"]}
    assert statuses["I3"] == "unverified"
    assert statuses["I11"] == "unverified"
    assert statuses["I12"] == "unverified"
    assert statuses["I4"] == "unverified"
    assert report["verdict"] == "partial"


def test_an_unverified_stop_says_which_fact_is_missing(nothing_known: None) -> None:
    report = trip_verification.build_verification(_SOUND)
    named = {row["name"]: row["missing"] for row in report["unverified_stops"]}
    assert "opening hours" in named["Rajwada Palace"]
    assert "location" in named["Rajwada Palace"]


def test_a_fully_known_sound_trip_reports_clear(fully_known: None) -> None:
    report = trip_verification.build_verification(_SOUND)
    assert report["verdict"] == "clear"
    assert report["counts"]["failed"] == 0
    assert report["counts"]["unverified"] == 0


def test_a_closed_weekday_is_reported_as_a_failed_check(fully_known: None) -> None:
    report = trip_verification.build_verification(_SOUND)
    closed = next(check for check in report["checks"] if check["code"] == "I11")
    assert closed["status"] == "passed"

    # Day 2 of a trip starting Monday 2026-08-10 is the Tuesday Rajwada shuts.
    moved = plan(
        [
            [stop("Hotel Sayaji", "09:00", "hotel", 45)],
            [stop("Rajwada Palace", "11:00")],
        ]
    )
    report = trip_verification.build_verification(moved)
    closed = next(check for check in report["checks"] if check["code"] == "I11")
    assert closed["status"] == "failed"
    assert "Tuesday" in closed["findings"][0]
    assert report["verdict"] == "issues"


def test_the_certificate_never_contradicts_the_guard(fully_known: None) -> None:
    broken = plan(
        [
            [stop("Hotel Sayaji", "09:00", "hotel", 45)],
            [stop("Rajwada Palace", "11:00")],
        ]
    )
    codes = {violation.code for violation in trip_guard.validate_plan(broken)}
    failed = {
        check["code"]
        for check in trip_verification.build_verification(broken)["checks"]
        if check["status"] == "failed"
    }
    assert failed == codes


def test_days_carry_their_own_verdict(fully_known: None) -> None:
    broken = plan(
        [
            [stop("Hotel Sayaji", "09:00", "hotel", 45)],
            [stop("Rajwada Palace", "11:00")],
        ]
    )
    rows = {row["day"]: row for row in trip_verification.build_verification(broken)["days"]}
    assert rows[2]["status"] == "failed"
    assert any("Rajwada Palace" in message for message in rows[2]["findings"])


# --------------------------------------------------------------------------- #
# public holidays                                                              #
# --------------------------------------------------------------------------- #


@pytest.fixture
def indian_holidays(monkeypatch: pytest.MonkeyPatch) -> None:
    """Day 2 of the sound trip falls on a named public holiday."""
    monkeypatch.setattr(
        trip_verification.place_country, "resolve_country_code", lambda _place: "IN"
    )
    monkeypatch.setattr(
        trip_verification.holidays,
        "holiday_on",
        lambda _code, day_iso: "Independence Day" if day_iso == "2026-08-11" else "",
    )


def test_a_holiday_retracts_the_weekly_hours_claim(
    fully_known: None, indian_holidays: None
) -> None:
    report = trip_verification.build_verification(_SOUND)
    hours = next(check for check in report["checks"] if check["code"] == "I3")
    assert hours["status"] == "unverified"
    assert any("Independence Day" in text for gap in hours["gaps"] for text in gap["missing"])


def test_the_holiday_is_named_on_its_day(fully_known: None, indian_holidays: None) -> None:
    rows = {row["day"]: row for row in trip_verification.build_verification(_SOUND)["days"]}
    assert rows[2]["holiday"] == "Independence Day"
    assert rows[3]["holiday"] == ""


def test_an_unreadable_calendar_leaves_known_hours_standing(
    fully_known: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        trip_verification.place_country, "resolve_country_code", lambda _place: "IN"
    )
    monkeypatch.setattr(
        trip_verification.holidays, "holiday_on", lambda _code, _day: None
    )
    report = trip_verification.build_verification(_SOUND)
    assert report["verdict"] == "clear"
