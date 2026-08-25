"""The guard and the effort model, tested as pure arithmetic over a plan.

The two rules under test are the ones the layer exists for: an invariant may
block but never speaks in numbers, and the effort model may speak but never
blocks. No place lookups are stubbed except where a test is specifically about
coordinates, so the modules are exercised in their degraded, fact-poor mode too.
"""

from __future__ import annotations

import pytest

from tripplanner.tools import trip_common, trip_effort, trip_guard, trip_validation

_COORDS = {
    "Rajwada Palace": (22.7177, 75.8545),
    "Sarafa Bazaar": (22.7150, 75.8570),
    "Lal Bagh Palace": (22.6944, 75.8452),
    "Mandu Fort": (22.3700, 75.4000),
    "Hotel Sayaji": (22.7250, 75.8800),
    # ~500 km from Indore: far enough that only a named journey explains it.
    "Gateway of India": (18.9220, 72.8347),
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


def test_a_home_arrival_endpoint_is_not_destination_activity_after_departure() -> None:
    returned = plan(
        [
            [stop("Drive: Bengaluru to Indore", "08:00", "transport", 600)],
            [
                stop("Rajwada Palace", "09:00"),
                stop("Drive: Indore to Bengaluru", "12:00", "transport", 600),
                stop("Bengaluru", "22:00", "other"),
            ],
        ]
    )

    violations = trip_guard.validate_plan(returned)

    assert not [
        violation
        for violation in violations
        if violation.code == "I1" and violation.stop == "Bengaluru"
    ]


def test_an_outbound_leg_without_a_return_is_reported() -> None:
    one_way = plan([[stop("Flight Bengaluru → Indore", "09:00", "flight", 120)]])
    assert any(violation.code == "I7" for violation in trip_guard.validate_plan(one_way))


# A regional destination names its real cities, so the envelope has to anchor on
# the traveller's home city rather than the destination string.
REGION_TRIP = plan(
    [
        [
            stop("Flight Bengaluru → Jaipur", "09:00", "flight", 150),
            stop("Hotel Sayaji", "14:00", "hotel", 45),
        ],
        [stop("Rajwada Palace", "10:00")],
        [
            stop("Mandu Fort", "09:00", "attraction", 180),
            stop("Flight Udaipur → Bengaluru", "18:00", "flight", 150),
        ],
    ],
    destination="Rajasthan",
)


def test_envelope_reads_a_regional_trip_from_its_home_city() -> None:
    env = trip_guard.envelope(REGION_TRIP)
    assert env.arrival_day == 1
    assert env.departure_day == 3
    assert env.bounded_start and env.bounded_end


def test_a_regional_outbound_without_a_return_is_reported() -> None:
    one_way = plan(
        [[stop("Flight Bengaluru → Jaipur", "09:00", "flight", 150)]],
        destination="Rajasthan",
    )
    assert any(violation.code == "I7" for violation in trip_guard.validate_plan(one_way))


def test_a_regional_return_without_an_outbound_is_reported() -> None:
    return_only = plan(
        [[stop("Flight Udaipur → Bengaluru", "18:00", "flight", 150)]],
        destination="Rajasthan",
    )

    assert any(violation.code == "I7" for violation in trip_guard.validate_plan(return_only))


def test_a_leg_between_two_destination_cities_never_bounds_the_trip() -> None:
    internal = plan(
        [
            [stop("Flight Bengaluru → Jaipur", "09:00", "flight", 150)],
            [stop("Drive Jaipur → Udaipur", "09:00", "transport", 300)],
            [stop("Flight Udaipur → Bengaluru", "18:00", "flight", 150)],
        ],
        destination="Rajasthan",
    )
    env = trip_guard.envelope(internal)
    assert env.arrival_day == 1
    assert env.departure_day == 3


def test_a_regional_round_trip_is_not_reported_as_missing_its_legs() -> None:
    complete = plan(
        [
            [
                stop("Flight Bengaluru → Jaipur", "09:00", "flight", 150),
                stop("Hotel Sayaji", "14:00", "hotel", 45),
            ],
            [
                stop("Hotel Sayaji", "08:00", "hotel", 30),
                stop("Flight Udaipur → Bengaluru", "18:00", "flight", 150),
            ],
        ],
        destination="Rajasthan",
    )
    assert trip_validation._round_trip_transport_warnings(complete) == []


def test_a_regional_trip_missing_its_return_is_still_reported() -> None:
    one_way = plan(
        [
            [
                stop("Flight Bengaluru → Jaipur", "09:00", "flight", 150),
                stop("Hotel Sayaji", "14:00", "hotel", 45),
            ],
            [stop("Hotel Sayaji", "08:00", "hotel", 30)],
        ],
        destination="Rajasthan",
    )
    warnings = trip_validation._round_trip_transport_warnings(one_way)
    assert len(warnings) == 1
    assert "back to Bengaluru" in warnings[0]


def test_missing_departure_journey_is_a_core_completion_gap() -> None:
    missing_return = plan(
        [
            [
                stop("Flight Bengaluru -> Indore", "09:00", "flight", 120),
                stop("Hotel Sayaji", "14:00", "hotel", 45),
            ],
            [
                stop("Hotel Sayaji", "08:00", "hotel", 30),
                stop("Rajwada Palace", "10:00"),
            ],
        ]
    )

    gaps = trip_validation.core_planning_completion_gaps(missing_return)

    assert any("Departure day has no explicit" in gap for gap in gaps)


def test_a_stop_stranded_after_the_flight_home_blocks_completion(located: None) -> None:
    """A turn may not report success while the itinerary contradicts itself."""
    broken = plan(
        [
            [stop("Flight Bengaluru → Indore", "09:00", "flight", 120)],
            [stop("Rajwada Palace", "10:00")],
            [
                stop("Flight Indore → Bengaluru", "11:00", "flight", 120),
                stop("Mandu Fort", "15:00"),
            ],
        ]
    )
    gaps = trip_validation.itinerary_coherence_gaps(broken)
    assert any("Mandu Fort" in gap for gap in gaps)
    assert any(
        "Itinerary is not coherent" in gap
        for gap in trip_validation.planning_completion_gaps(broken)
    )


def test_a_coherent_itinerary_reports_no_coherence_gap(located: None) -> None:
    assert trip_validation.itinerary_coherence_gaps(ROUND_TRIP) == []


def test_zero_stay_coverage_fails_for_every_round_trip_night() -> None:
    no_stay = plan(
        [
            [stop("Flight Bengaluru → Indore", "09:00", "flight", 120)],
            [stop("Rajwada Palace", "10:00")],
            [stop("Flight Indore → Bengaluru", "18:00", "flight", 120)],
        ]
    )

    violations = [item for item in trip_guard.validate_plan(no_stay) if item.code == "I6"]

    assert [item.day for item in violations] == [1, 2]
    assert all("concrete lodging anchor" in item.message for item in violations)


def test_destination_only_trip_requires_stays_before_its_final_day() -> None:
    destination_only = plan(
        [
            [stop("Hotel Sayaji", "13:00", "hotel", 45)],
            [stop("Rajwada Palace", "10:00")],
            [stop("Lal Bagh Palace", "10:00")],
        ],
        origin="",
        travel_scope="destination_only",
    )

    violations = [item for item in trip_guard.validate_plan(destination_only) if item.code == "I6"]

    assert [item.day for item in violations] == [2]


def test_multi_city_trip_requires_a_lodging_anchor_for_each_overnight_city() -> None:
    regional = plan(
        [
            [
                stop("Flight Bengaluru → Jaipur", "09:00", "flight", 120),
                stop("Rambagh Palace", "13:00", "hotel", 45),
            ],
            [
                stop("Drive Jaipur to Udaipur", "09:00", "transport", 360),
                stop("City Palace Udaipur", "16:00"),
            ],
            [stop("Flight Udaipur → Bengaluru", "18:00", "flight", 120)],
        ],
        destination="Rajasthan",
    )

    violations = [item for item in trip_guard.validate_plan(regional) if item.code == "I6"]

    assert [item.day for item in violations] == [2]


def test_overnight_transfer_covers_the_night_without_a_hotel() -> None:
    transfer = plan(
        [
            [
                stop("Flight Bengaluru → Indore", "09:00", "flight", 120),
                stop("Hotel Sayaji", "13:00", "hotel", 45),
            ],
            [stop("Overnight sleeper train Indore to Jaipur", "21:00", "transport", 600)],
            [
                stop("Hotel Rambagh Palace", "08:00", "hotel", 45),
                stop("Flight Jaipur → Bengaluru", "18:00", "flight", 120),
            ],
        ]
    )

    assert not any(item.code == "I6" for item in trip_guard.validate_plan(transfer))


def test_generic_stay_anchor_does_not_cover_a_night() -> None:
    generic = plan(
        [
            [
                stop("Flight Bengaluru → Indore", "09:00", "flight", 120),
                stop("Premium Hotel in Indore", "13:00", "hotel", 45),
            ],
            [stop("Flight Indore → Bengaluru", "18:00", "flight", 120)],
        ]
    )

    violations = [item for item in trip_guard.validate_plan(generic) if item.code == "I6"]

    assert len(violations) == 1
    assert "bookable stay" in violations[0].message


def test_substantial_day_requires_specific_preference_matched_meal() -> None:
    itinerary = [
        {
            "day": 1,
            "stops": [
                stop("Sabarmati Ashram", "09:00"),
                stop("Adalaj Stepwell", "12:00"),
                {
                    "name": "Jain Restaurant (Ahmedabad)",
                    "kind": "meal",
                    "note": "Jain food",
                },
            ],
        }
    ]
    warnings = trip_validation._restaurant_itinerary_warnings(
        itinerary,
        cities={"ahmedabad"},
        dietary=["jain"],
    )
    assert any("meal placeholder" in warning for warning in warnings)

    itinerary[0]["stops"][-1] = {
        "name": "Agashiye - The House of MG",
        "kind": "meal",
        "note": "Confirmed Jain thali available",
    }
    assert trip_validation._restaurant_itinerary_warnings(
        itinerary,
        cities={"ahmedabad"},
        dietary=["jain"],
    ) == []


@pytest.mark.parametrize(
    ("day", "stop_name"),
    [
        ({"title": "Free day", "summary": "Day at leisure"}, ""),
        ({"title": "Old City", "summary": "Meals are open for the traveller to choose"}, ""),
        ({"title": "Transfer to Jaipur", "summary": ""}, "Train Indore to Jaipur"),
    ],
)
def test_explicit_open_meal_exceptions_preserve_substantial_days(
    day: dict[str, object], stop_name: str
) -> None:
    stops = [stop("Rajwada Palace", "09:00"), stop("Lal Bagh Palace", "12:00")]
    if stop_name:
        stops.append(stop(stop_name, "16:00", "transport", 180))
    itinerary = [{"day": 1, **day, "stops": stops}]

    assert trip_validation._restaurant_itinerary_warnings(itinerary) == []


def test_core_completion_requires_cost_evidence_only_for_requested_budget() -> None:
    complete = {
        "destination": "Ahmedabad",
        "origin": "Ahmedabad",
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "House of MG", "kind": "hotel"},
                stop("Sabarmati Ashram", "09:00"),
                stop("Adalaj Stepwell", "12:00"),
                {"name": "Agashiye", "kind": "meal"},
            ],
        }],
        "selected_hotels": [{"name": "House of MG"}],
        "total_cost": 0,
    }

    assert trip_validation.core_planning_completion_gaps(complete) == []

    complete["budget"] = {"amount": 50_000, "currency": "INR", "owner": "user"}
    gaps = trip_validation.core_planning_completion_gaps(complete)
    assert len(gaps) == 1
    assert "positive cost evidence" in gaps[0]

    complete["total_cost"] = 42_000
    assert trip_validation.core_planning_completion_gaps(complete) == []


def test_core_completion_rejects_a_hotel_only_day() -> None:
    plan = {
        "destination": "Bali",
        "origin": "Bali",
        "day_wise_itinerary": [{
            "day": 7,
            "stops": [{"name": "Maya Sanur Resort", "kind": "hotel"}],
        }],
        "selected_hotels": [{"name": "Maya Sanur Resort"}],
    }

    assert trip_validation.core_planning_completion_gaps(plan) == [
        "Day 7 has no planned places beyond the hotel."
    ]


def test_a_day_cannot_begin_where_the_trip_never_travelled(located: None) -> None:
    stranded = plan(
        [
            [stop("Rajwada Palace", "10:00")],
            [stop("Gateway of India", "10:00")],
        ]
    )
    codes = {violation.code for violation in trip_guard.validate_plan(stranded)}
    assert "I9" in codes


def test_a_journey_between_the_days_explains_the_move(located: None) -> None:
    connected = plan(
        [
            [
                stop("Rajwada Palace", "10:00"),
                stop("Drive Indore → Mumbai", "15:00", "transport", 180),
            ],
            [stop("Gateway of India", "10:00")],
        ]
    )
    codes = {violation.code for violation in trip_guard.validate_plan(connected)}
    assert "I9" not in codes


def test_a_nearby_day_trip_is_never_reported_as_a_gap(located: None) -> None:
    nearby = plan(
        [
            [stop("Rajwada Palace", "10:00")],
            [stop("Mandu Fort", "10:00")],
        ]
    )
    codes = {violation.code for violation in trip_guard.validate_plan(nearby)}
    assert "I9" not in codes


def test_continuity_stays_silent_when_a_place_has_no_coordinates() -> None:
    unlocated = plan(
        [
            [stop("Somewhere Unknown", "10:00")],
            [stop("Another Unknown", "10:00")],
        ]
    )
    codes = {violation.code for violation in trip_guard.validate_plan(unlocated)}
    assert "I9" not in codes


def test_continuity_ignores_coordinates_from_a_different_provider_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summaries = {
        "Coorg Wilderness Resort": {
            "name": "Coorg Wilderness Resort",
            "lat": 12.3375,
            "lng": 75.8069,
        },
        "Dubare Elephant Camp": {
            "name": "Booking Office of Coorg Dubare Elephant camp",
            "lat": 12.9710,
            "lng": 77.6004,
        },
    }

    def summary(name: str, _destination: str = "") -> dict[str, object]:
        return summaries.get(name, {})

    for module in (trip_common, trip_guard):
        monkeypatch.setattr(module, "_summary_for_place", summary, raising=False)

    coorg_day = plan(
        [[
            stop("Coorg Wilderness Resort", "07:30", "hotel"),
            stop("Dubare Elephant Camp", "09:00"),
        ]],
        destination="Coorg",
    )

    assert not [v for v in trip_guard.validate_plan(coorg_day) if v.code == "I9"]


def test_a_stop_far_from_the_one_before_it_is_a_gap_within_the_day(located: None) -> None:
    """The Paris shape: a stay in the destination listed after landing back home."""
    stranded = plan(
        [
            [
                stop("Rajwada Palace", "09:00"),
                stop("Gateway of India", "20:00", "hotel", 45),
            ],
        ]
    )
    violations = [v for v in trip_guard.validate_plan(stranded) if v.code == "I9"]
    assert violations
    assert "Gateway of India" in violations[0].message
    assert "no journey connects them" in violations[0].message


def test_two_terminals_in_a_row_are_the_journey_the_plan_did_not_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Kempegowda International Airport": (13.1986, 77.7066),
        "Zayed International Airport": (24.4330, 54.6511),
        "Charles de Gaulle Airport": (49.0097, 2.5479),
    }

    def summary(name: str, _destination: str = "") -> dict[str, object]:
        pair = coords.get(name)
        return {"lat": pair[0], "lng": pair[1]} if pair else {}

    for module in (trip_common, trip_guard):
        monkeypatch.setattr(module, "_summary_for_place", summary, raising=False)

    connecting = plan(
        [
            [
                stop("Kempegowda International Airport", "04:35", "transport", 60),
                stop("Zayed International Airport", "07:00", "transport", 60),
                stop("Charles de Gaulle Airport", "19:20", "transport", 60),
            ],
        ]
    )
    codes = {violation.code for violation in trip_guard.validate_plan(connecting)}
    assert "I9" not in codes


def test_a_continuity_gap_blocks_completion(located: None) -> None:
    stranded = plan(
        [
            [
                stop("Rajwada Palace", "09:00"),
                stop("Gateway of India", "20:00", "hotel", 45),
            ],
        ]
    )
    assert any(
        "Gateway of India" in gap for gap in trip_validation.itinerary_coherence_gaps(stranded)
    )


def test_a_few_minutes_late_for_something_that_waits_is_not_a_violation(
    located: None,
) -> None:
    """Arriving a little after an ordinary sight costs nothing and reports nothing."""
    tight = plan(
        [
            [
                stop("Rajwada Palace", "10:00", "attraction", 60),
                stop("Sarafa Bazaar", "11:05", "meal", 60),
            ]
        ]
    )

    assert not [v for v in trip_guard.validate_plan(tight) if v.code == "I4"]


def test_the_same_few_minutes_late_for_a_booked_stop_is_a_violation(
    located: None,
) -> None:
    booked = plan(
        [
            [
                stop("Rajwada Palace", "10:00", "attraction", 60),
                {**stop("Sarafa Bazaar", "11:05", "meal", 60), "booked": True},
            ]
        ]
    )

    assert [v for v in trip_guard.validate_plan(booked) if v.code == "I4"]


def test_a_plan_without_an_origin_reports_that_the_guard_cannot_run() -> None:
    blind = plan([[stop("Rajwada Palace", "10:00")]], origin="")
    violations = [v for v in trip_guard.validate_plan(blind) if v.code == "I10"]
    assert violations
    assert "Ask the traveller" in violations[0].message
    assert any(
        "does not say where it starts from" in gap
        for gap in trip_validation.planning_completion_gaps(blind)
    )


def test_a_traveller_arranging_their_own_arrival_is_not_asked_again() -> None:
    """A destination-only trip has answered the question; it is not a defect."""
    own_arrival = plan(
        [[stop("Rajwada Palace", "10:00")]], origin="", travel_scope="destination_only"
    )

    assert not [v for v in trip_guard.validate_plan(own_arrival) if v.code == "I10"]
    assert not [
        gap
        for gap in trip_validation.planning_completion_gaps(own_arrival)
        if "starts from" in gap
    ]
    assert trip_validation.persistence_sanity_errors(own_arrival) == []


def test_timeline_includes_hotel_and_transport_duration() -> None:
    broken = plan(
        [
            [
                stop("Hotel Sayaji checkout", "08:00", "hotel", 45),
                stop("Rajwada Palace", "10:00"),
                stop("Drive Indore → Ujjain", "08:30", "transport", 120),
            ]
        ]
    )

    errors = trip_validation._itinerary_time_errors(broken["day_wise_itinerary"])

    assert any("Drive Indore" in error and "not chronological" in error for error in errors)


def test_intentional_overnight_journey_remains_chronological() -> None:
    overnight = plan(
        [
            [
                stop("Night train Indore → Mumbai", "22:00", "transport", 480),
                stop("Mumbai hotel arrival", "06:00", "hotel", 30),
            ]
        ]
    )

    assert trip_validation._itinerary_time_errors(overnight["day_wise_itinerary"]) == []


@pytest.mark.parametrize("mode", ["Train", "Ferry", "Drive"])
def test_complete_ground_round_trip_needs_no_selected_flight_inventory(mode: str) -> None:
    complete = plan(
        [
            [
                stop(f"{mode} Bengaluru → Indore", "08:00", "transport", 240),
                stop("Hotel Sayaji", "13:00", "hotel", 30),
            ],
            [
                stop("Hotel Sayaji checkout", "08:00", "hotel", 30),
                stop(f"{mode} Ujjain → Bengaluru", "16:00", "transport", 240),
            ],
        ]
    )

    assert trip_validation._round_trip_transport_warnings(complete) == []
    assert trip_validation._journey_inventory_errors(complete) == []


def test_open_jaw_edges_are_complete_when_both_touch_home() -> None:
    open_jaw = plan(
        [
            [
                stop("Flight Bengaluru → Jaipur", "08:00", "flight", 150),
                stop("Jaipur Hotel", "12:00", "hotel", 30),
            ],
            [
                stop("Udaipur Hotel checkout", "08:00", "hotel", 30),
                stop("Flight Udaipur → Bengaluru", "18:00", "flight", 150),
            ],
        ],
        destination="Rajasthan",
        selected_flights=[{"airline": "Air India"}],
    )

    assert trip_validation._round_trip_transport_warnings(open_jaw) == []
    assert trip_validation._journey_inventory_errors(open_jaw) == []


def test_narrated_flight_requires_selected_offer() -> None:
    assert trip_validation._journey_inventory_errors(ROUND_TRIP) == [
        "The itinerary narrates flight travel but no selected flight offer supports it."
    ]


def test_a_plan_that_names_its_origin_reports_no_coverage_gap(located: None) -> None:
    codes = {violation.code for violation in trip_guard.validate_plan(ROUND_TRIP)}
    assert "I10" not in codes


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


def test_placement_waits_until_an_evening_place_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evening_hours = [
        f"{day}: 6:00 PM - 11:00 PM"
        for day in (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )
    ]
    monkeypatch.setattr(
        trip_guard,
        "_summary_for_place",
        lambda name, _destination="": {
            "name": name,
            "weekday_descriptions": evening_hours,
        },
    )
    itinerary = plan(
        [[]],
        departure_date="2026-09-07",
        origin="",
        travel_scope="destination_only",
    )

    placement, rejections = trip_guard.choose_placement(
        itinerary,
        "Sarafa Bazaar",
        "meal",
        duration_min=90,
        preferred_day=1,
    )

    assert placement is not None
    assert placement.time == "18:00"
    assert not [rejection for rejection in rejections if rejection.code == "I3"]


def test_a_meal_without_duration_uses_the_meal_default_for_split_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    split_hours = [
        f"{day}: 11:30 AM - 2:30 PM, 7:00 - 11:00 PM"
        for day in (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )
    ]
    monkeypatch.setattr(
        trip_guard,
        "_summary_for_place",
        lambda name, _destination="": {
            "name": name,
            "weekday_descriptions": split_hours,
        },
    )
    itinerary = plan(
        [[{"name": "La Petite Venise", "kind": "meal", "time": "13:15"}]],
        departure_date="2027-04-08",
        destination="Paris",
        origin="",
        travel_scope="destination_only",
    )

    assert trip_guard._duration_of(itinerary["day_wise_itinerary"][0]["stops"][0]) == 60
    assert not [
        violation for violation in trip_guard.validate_plan(itinerary) if violation.code == "I3"
    ]

    itinerary["day_wise_itinerary"][0]["stops"][0]["kind"] = "attraction"
    assert trip_guard._duration_of(itinerary["day_wise_itinerary"][0]["stops"][0]) == 90
    assert [
        violation
        for violation in trip_guard.validate_plan(itinerary)
        if violation.code == "I3"
    ]


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


def test_grounded_weather_exposure_names_heat_and_rain_without_a_score() -> None:
    exposed = plan(
        [[stop("Rajwada Palace", "12:00", "attraction", 180)]],
        weather={
            "source": "forecast",
            "days": [
                {
                    "date": "2026-08-25",
                    "high_c": 36,
                    "precip_probability_pct": 80,
                }
            ]
        },
    )
    exposed["day_wise_itinerary"][0]["date"] = "2026-08-25"

    notes = trip_effort.coherence_notes(exposed)

    assert any("36°C" in note and "Open-Meteo" in note for note in notes)
    assert any("80%" in note and "rain" in note.lower() for note in notes)
    assert not any("score" in note.lower() for note in notes)


def test_review_duration_only_speaks_from_structured_place_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    under_timed = plan([[stop("Rajwada Palace", "10:00", "attraction", 45)]])
    monkeypatch.setattr(
        trip_effort,
        "_summary_for_place",
        lambda _name, _destination="": {
            "typical_visit_duration_min": 120,
            "visit_duration_source": "Google visitor summaries",
        },
    )

    notes = trip_effort.coherence_notes(under_timed)

    assert any("45 minutes" in note and "2 hours" in note for note in notes)
    assert any("Google visitor summaries" in note for note in notes)


def test_activity_provider_duration_can_ground_an_under_timed_visit() -> None:
    under_timed = plan([[stop("Lisbon Food Tour", "10:00", "attraction", 45)]])
    under_timed["selected_activities"] = [
        {
            "name": "Lisbon Food Tour",
            "provider": "viator",
            "duration_minutes": {"min": 120, "max": 180},
        }
    ]

    notes = trip_effort.coherence_notes(under_timed)

    assert any("45 minutes" in note and "2 hours" in note for note in notes)
    assert any("viator activity listing" in note for note in notes)


def test_the_effort_model_cannot_refuse_anything() -> None:
    public = {
        name
        for name in dir(trip_effort)
        if not name.startswith("_") and callable(getattr(trip_effort, name))
    }
    assert not {name for name in public if "valid" in name or "block" in name}


# --------------------------------------------------------------------------- #
# A drive in the middle of the day
# --------------------------------------------------------------------------- #

EXCURSION = plan(
    [
        [
            stop("Flight Bengaluru → Indore", "09:00", "flight", 120),
            stop("Hotel Sayaji", "13:00", "hotel", 45),
        ],
        [
            stop("Hotel Sayaji", "08:00", "hotel", 30),
            stop("Drive Indore to Ujjain", "09:00", "transport", 120),
            stop("Mandu Fort", "11:30", "attraction", 120),
            stop("Drive Ujjain to Indore", "15:00", "transport", 120),
        ],
        [
            stop("Rajwada Palace", "10:00"),
            stop("Flight Indore → Bengaluru", "18:00", "flight", 120),
        ],
    ]
)


def test_a_midday_drive_holds_its_hours(located: None) -> None:
    """The traveller is sitting in the car; that time is not free."""
    env = trip_guard.envelope(EXCURSION)
    stops = EXCURSION["day_wise_itinerary"][1]["stops"]
    windows = trip_guard._windows(2, stops, env)
    drive = trip_guard._abs(2, 15 * 60)
    assert not any(window.start < drive + 120 and window.end > drive for window in windows)


def test_the_trips_own_legs_do_not_carve_up_their_day(located: None) -> None:
    """Arrival and departure already bound the day; blocking them twice would
    leave the arrival day with no usable time at all."""
    env = trip_guard.envelope(ROUND_TRIP)
    stops = ROUND_TRIP["day_wise_itinerary"][0]["stops"]
    assert trip_guard._windows(1, stops, env)


def test_a_stop_is_never_offered_the_hours_a_drive_occupies(located: None) -> None:
    placement, _ = trip_guard.choose_placement(
        EXCURSION, "Lal Bagh Palace", "attraction", duration_min=90, preferred_day=2
    )
    if placement is not None:
        chosen = trip_guard._parse_hhmm(placement.time)
        assert chosen is not None
        assert not (chosen < 17 * 60 and chosen + 90 > 15 * 60)


def test_a_drive_does_not_demand_airport_check_in(located: None) -> None:
    """Two hours of buffer before a car ride is noise, not a rule."""
    codes = [item.message for item in trip_guard.validate_plan(EXCURSION) if item.code == "I5"]
    assert not codes
