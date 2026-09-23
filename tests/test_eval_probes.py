from __future__ import annotations

from tripplanner.evals import judge, probes, trip_text


def _plan(**overrides):  # type: ignore[no-untyped-def]
    plan = {
        "destination": "Goa",
        "origin": "Bangalore",
        "total_cost": 0,
        "selected_flights": [{"airline": "Duffel Airways", "price": 10, "currency": "USD"}],
        "selected_hotels": [{"name": "Stay", "checkout": "2027-03-14"}],
        "day_wise_itinerary": [
            {
                "day": 1,
                "date": "2027-03-12",
                "summary": "Relax at Baga Beach.",
                "stops": [
                    {"name": "Stay", "kind": "hotel"},
                    {"name": "Candolim Beach", "kind": "attraction", "time": "10:00"},
                    {"name": "Lunch (TBD)", "kind": "meal", "time": "13:00"},
                ],
            },
            {
                "day": 2,
                "date": "2027-03-13",
                "summary": "Leave.",
                "stops": [
                    {"name": "Stay", "kind": "hotel", "note": "Start"},
                    {
                        "name": "Drive: Goa to Bangalore",
                        "kind": "transport",
                        "time": "08:00",
                        "distance_km": 560,
                        "duration_min": 300,
                    },
                    {"name": "Stay", "kind": "hotel", "time": "11:00", "note": "Checkout"},
                    {"name": "Baga Beach", "kind": "attraction", "time": "07:00"},
                ],
            },
        ],
    }
    plan.update(overrides)
    return plan


def test_probes_find_each_judged_defect_pattern() -> None:
    plan = _plan()

    assert probes.placeholder_stops(plan) == ["Day 1: Lunch (TBD)"]
    assert probes.unpriced(plan)
    assert probes.synthetic_fares(plan) == ["Duffel Airways 10 USD"]
    assert probes.stay_after_departure(plan)[0].startswith("Day 2: Stay (Checkout)")
    assert probes.out_of_order(plan)[0].startswith("Day 2: Baga Beach at 07:00")
    assert probes.implausible_road_speed(plan) == [
        "Day 2: Drive: Goa to Bangalore 560 km in 300 min (112 km/h)"
    ]
    assert probes.summary_drift(plan) == ["Day 1 summary names Baga Beach, planned on Day 2"]


def test_probes_stay_quiet_on_a_clean_plan() -> None:
    plan = _plan(total_cost=100, selected_flights=[], selected_hotels=[])
    plan["day_wise_itinerary"] = [plan["day_wise_itinerary"][0]]
    plan["day_wise_itinerary"][0]["stops"][2]["name"] = "Gunpowder"

    assert not any(probe(plan) for _, probe in probes.PROBES.values())


def test_unused_night_needs_a_final_departure() -> None:
    plan = _plan(selected_hotels=[{"name": "Stay", "checkout": "2027-03-15"}])
    plan["day_wise_itinerary"][1]["stops"].append(
        {"name": "Flight: Goa to Bangalore", "kind": "flight"}
    )

    assert probes.unused_nights(plan) == ["Stay checks out 2027-03-15 after leaving on 2027-03-13"]


def test_place_identity_counts_resolutions_that_share_no_word() -> None:
    result = probes.place_identity(
        {
            "india gate|delhi, agra, jaipur": {"name": "Delhi Agra Jaipur Trip"},
            "ortakoy|istanbul": {"name": "Ortaköy"},
            "galleria|florence": {"name": "Galleria dell’Accademia"},
            "missing|x": {},
        }
    )

    assert (result["resolved"], result["mismatched"]) == (3, 1)
    assert result["examples"] == ["india gate (delhi, agra, jaipur) -> Delhi Agra Jaipur Trip"]


def test_trip_text_cites_pointers_the_judge_validator_resolves() -> None:
    plan = _plan()
    places = {
        "lunch (tbd)|goa": {"name": "Tereza Beach House", "rating": 4.5},
        "lunch (tbd)|mumbai": {"name": "Elsewhere"},
    }
    evidence = {
        "request": "Plan Goa",
        "preferences": {},
        "plan": plan,
        "final_reply": "",
        "places": trip_text.places_for(plan, places),
    }

    text = trip_text.render(evidence)

    assert list(evidence["places"]) == ["lunch (tbd)|goa"]
    line = next(line for line in text.splitlines() if line.endswith(": Lunch (TBD)"))
    path, quote = line.split(": ", 1)
    assert judge.pointer(evidence, path) == quote
