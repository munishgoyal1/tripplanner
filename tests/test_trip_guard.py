"""The guard and the effort model, tested as pure arithmetic over a plan.

The two rules under test are the ones the layer exists for: an invariant may
block but never speaks in numbers, and the effort model may speak but never
blocks. No place lookups are stubbed except where a test is specifically about
coordinates, so the modules are exercised in their degraded, fact-poor mode too.
"""

from __future__ import annotations

import pytest

from tripplanner.tools import trip_common, trip_effort, trip_guard

_COORDS = {
    "Rajwada Palace": (22.7177, 75.8545),
    "Sarafa Bazaar": (22.7150, 75.8570),
    "Lal Bagh Palace": (22.6944, 75.8452),
    "Mandu Fort": (22.3700, 75.4000),
    "Hotel Sayaji": (22.7250, 75.8800),
}


@pytest.fixture
def located(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every known place a coordinate, and everything else none."""

    def summary(name: str, _destination: str = "") -> dict[str, object]:
        coords = _COORDS.get(name)
        return {"lat": coords[0], "lng": coords[1]} if coords else {}

    for module in (trip_common, trip_guard, trip_effort):
        monkeypatch.setattr(module, "_summary_for_place", summary, raising=False)


def plan(days: list[list[dict[str, object]]], **extra: object) -> dict[str, object]:
    return {
        "origin": "Bengaluru",
        "destination": "Indore",
        "day_wise_itinerary": [
            {"day": index + 1, "stops": stops} for index, stops in enumerate(days)
        ],
        **extra,
    }


def stop(name: str, time: str, kind: str = "attraction", minutes: int = 90) -> dict[str, object]:
    return {"name": name, "kind": kind, "time": time, "duration_min": minutes}


ROUND_TRIP = plan(
    [
        [
            stop("Flight Bengaluru → Indore", "09:00", "flight", 120),
            stop("Hotel Sayaji", "13:00", "hotel", 45),
            stop("Rajwada Palace", "15:00"),
        ],
        [
            stop("Lal Bagh Palace", "10:00"),
            stop("Sarafa Bazaar", "19:00", "meal", 90),
        ],
        [
            stop("Mandu Fort", "09:00", "attraction", 180),
            stop("Flight Indore → Bengaluru", "18:00", "flight", 120),
        ],
    ]
)


# --------------------------------------------------------------------------- #
# the envelope                                                                  #
# --------------------------------------------------------------------------- #


def test_envelope_reads_both_legs_from_stop_names() -> None:
    env = trip_guard.envelope(ROUND_TRIP)
    assert env.arrival_day == 1
    assert env.departure_day == 3
    assert env.bounded_start and env.bounded_end


def test_a_sound_plan_reports_no_envelope_violation(located: None) -> None:
    codes = {violation.code for violation in trip_guard.validate_plan(ROUND_TRIP)}
    assert "I1" not in codes
    assert "I2" not in codes


def test_a_stop_after_the_flight_home_breaks_the_envelope(located: None) -> None:
    broken = plan(
        [
            [stop("Flight Bengaluru → Indore", "09:00", "flight", 120)],
            [stop("Rajwada Palace", "10:00")],
            [
                stop("Flight Indore → Bengaluru", "14:00", "flight", 120),
                stop("Mandu Fort", "17:00"),
            ],
        ]
    )
    violations = trip_guard.validate_plan(broken)
    assert {violation.code for violation in violations} >= {"I1", "I2"}
    assert any("Mandu Fort" in violation.message for violation in violations)


def test_an_outbound_leg_without_a_return_is_reported() -> None:
    one_way = plan([[stop("Flight Bengaluru → Indore", "09:00", "flight", 120)]])
    assert any(violation.code == "I7" for violation in trip_guard.validate_plan(one_way))


def test_no_violation_ever_reports_a_number_as_a_verdict(located: None) -> None:
    broken = plan(
        [
            [stop("Flight Bengaluru → Indore", "09:00", "flight", 120)],
            [
                stop("Rajwada Palace", "10:00"),
                stop("Mandu Fort", "11:00"),
            ],
            [stop("Flight Indore → Bengaluru", "14:00", "flight", 120)],
        ]
    )
    for violation in trip_guard.validate_plan(broken):
        assert not any(
            token in violation.message.lower()
            for token in ("score", "rating", "/100", "out of 10", "%")
        )


# --------------------------------------------------------------------------- #
# guarded placement — the defect this layer exists to close                     #
# --------------------------------------------------------------------------- #


def test_best_day_never_lands_a_new_place_after_the_flight_home(located: None) -> None:
    placement, _rejections = trip_guard.choose_placement(
        ROUND_TRIP, "Patalpani Falls", "attraction", duration_min=120
    )
    assert placement is not None
    assert placement.day != 3 or placement.time < "16:00"


def test_a_day_outside_the_envelope_is_not_a_candidate_at_all(located: None) -> None:
    late = plan(
        [
            [stop("Flight Bengaluru → Indore", "09:00", "flight", 120)],
            [stop("Flight Indore → Bengaluru", "10:00", "flight", 120)],
            [stop("Rest at home", "12:00", "other", 60)],
        ]
    )
    placement, _rejections = trip_guard.choose_placement(late, "Rajwada Palace", "attraction")
    assert placement is None or placement.day <= 2


def test_placement_explains_itself_without_reporting_a_score(located: None) -> None:
    placement, _rejections = trip_guard.choose_placement(
        ROUND_TRIP, "Patalpani Falls", "attraction", duration_min=60
    )
    assert placement is not None and placement.reasons
    joined = " ".join(placement.reasons).lower()
    assert "score" not in joined and "rating" not in joined


def test_a_preferred_day_restricts_the_search_to_that_day(located: None) -> None:
    placement, _rejections = trip_guard.choose_placement(
        ROUND_TRIP, "Patalpani Falls", "attraction", duration_min=60, preferred_day=2
    )
    assert placement is not None and placement.day == 2


# --------------------------------------------------------------------------- #
# blast radius                                                                  #
# --------------------------------------------------------------------------- #


def test_the_diff_names_a_removed_leg_the_request_never_mentioned() -> None:
    after = plan(
        [
            ROUND_TRIP["day_wise_itinerary"][0]["stops"],
            ROUND_TRIP["day_wise_itinerary"][1]["stops"],
            [stop("Mandu Fort", "09:00", "attraction", 180)],
        ]
    )
    changes = trip_guard.diff_stops(ROUND_TRIP, after)
    stray = trip_guard.unexpected_changes(changes, {"Hotel Sayaji"})
    assert any(change.name == "Flight Indore → Bengaluru" for change in stray)
    assert "Flight Indore → Bengaluru" in trip_guard.receipt(stray)


def test_an_unchanged_plan_produces_an_empty_receipt() -> None:
    assert trip_guard.receipt(trip_guard.diff_stops(ROUND_TRIP, ROUND_TRIP)).startswith("Nothing")


# --------------------------------------------------------------------------- #
# the effort model                                                              #
# --------------------------------------------------------------------------- #


def test_capacity_is_the_minimum_across_the_party_not_the_average() -> None:
    solo = trip_effort.capacity_for(plan([], family={"adults": 1, "child_ages": []}))
    with_child = trip_effort.capacity_for(
        plan([], family={"adults": 2, "children": 1, "child_ages": [7]})
    )
    assert with_child.minutes < solo.minutes
    assert "7-year-old" in with_child.limited_by


def test_effort_is_monotone_in_the_time_a_day_asks_for(located: None) -> None:
    light = plan([[stop("Rajwada Palace", "10:00", "attraction", 60)]])
    heavy = plan([[stop("Rajwada Palace", "10:00", "attraction", 240)]])
    assert trip_effort.day_efforts(heavy)[0].total > trip_effort.day_efforts(light)[0].total


def test_a_solo_traveller_on_a_gentle_trip_hears_nothing_about_pacing(located: None) -> None:
    gentle = plan(
        [[stop("Rajwada Palace", "10:00", "attraction", 90)] for _ in range(5)],
        family={"adults": 1, "child_ages": []},
    )
    assert trip_effort.pacing_statement(gentle) is None


def test_at_most_one_pacing_statement_reaches_the_trip(located: None) -> None:
    relentless = plan(
        [
            [
                stop("Rajwada Palace", "06:00", "attraction", 240),
                stop("Mandu Fort", "12:00", "attraction", 300),
                stop("Sarafa Bazaar", "22:00", "meal", 120),
            ]
            for _ in range(6)
        ],
        family={"adults": 2, "children": 1, "child_ages": [7]},
    )
    statement = trip_effort.pacing_statement(relentless)
    assert statement is not None
    assert isinstance(statement["statement"], str)


def test_nothing_the_effort_model_says_contains_a_composite(located: None) -> None:
    relentless = plan(
        [
            [
                stop("Rajwada Palace", "06:00", "attraction", 240),
                stop("Mandu Fort", "12:00", "attraction", 300),
                stop("Sarafa Bazaar", "22:00", "meal", 120),
            ]
            for _ in range(6)
        ],
        family={"adults": 2, "children": 1, "child_ages": [7]},
    )
    said = " ".join(
        [
            trip_effort.pacing_statement(relentless)["statement"],
            trip_effort.pacing_statement(relentless)["remedy"],
            trip_effort.describe_day(relentless, 2),
            *trip_effort.coherence_notes(relentless),
        ]
    ).lower()
    for token in ("score", "rating", "/100", "out of 10", "effort:", "%"):
        assert token not in said


def test_a_day_that_runs_through_lunch_is_worth_mentioning(located: None) -> None:
    hungry = plan(
        [
            [
                stop("Rajwada Palace", "09:00", "attraction", 180),
                stop("Lal Bagh Palace", "12:00", "attraction", 240),
            ]
        ]
    )
    assert any("lunch" in note for note in trip_effort.coherence_notes(hungry))


def test_a_late_night_into_an_early_start_is_worth_mentioning(located: None) -> None:
    stacked = plan(
        [
            [stop("Sarafa Bazaar", "21:00", "meal", 150)],
            [stop("Rajwada Palace", "07:00", "attraction", 120)],
        ]
    )
    notes = trip_effort.coherence_notes(stacked)
    assert any("07:00" in note for note in notes)


def test_the_effort_model_cannot_refuse_anything() -> None:
    public = {
        name
        for name in dir(trip_effort)
        if not name.startswith("_") and callable(getattr(trip_effort, name))
    }
    assert not {name for name in public if "valid" in name or "block" in name}
