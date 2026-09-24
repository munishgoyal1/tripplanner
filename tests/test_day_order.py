from __future__ import annotations

from tripplanner.tools import day_order


def _plan():  # type: ignore[no-untyped-def]
    return {
        "selected_hotels": [
            {"name": "Radisson", "checkin": "2027-09-10", "checkout": "2027-09-13",
             "price_per_night": 6500, "total_price": 19500},
        ],
        "day_wise_itinerary": [
            {"day": 1, "date": "2027-09-10", "stops": [
                {"name": "Drive: Bangalore to Mysore", "kind": "transport", "time": "08:00"},
                {"name": "Radisson", "kind": "hotel", "note": "Check-in"},
                {"name": "Mysore Palace", "kind": "attraction", "time": "15:00"},
            ]},
            {"day": 2, "date": "2027-09-11", "stops": [
                {"name": "Radisson", "kind": "hotel", "note": "Start from hotel"},
                {"name": "Drive: Mysore to Srirangapatna", "kind": "transport", "time": "09:00"},
                {"name": "Srirangapatna", "kind": "attraction", "time": "09:30"},
                {"name": "Drive: Srirangapatna to Mysore", "kind": "transport", "time": "13:00"},
                {"name": "Radisson", "kind": "hotel", "note": "Return"},
            ]},
            {"day": 3, "date": "2027-09-12", "stops": [
                {"name": "Drive: Mysore to Bangalore", "kind": "transport", "time": "10:00"},
                {"name": "Radisson", "kind": "hotel", "time": "12:10", "note": "Checkout"},
                {"name": "Lunch at MTR", "kind": "meal", "time": "13:30"},
                {"name": "Flight: Bangalore to Delhi", "kind": "flight", "time": "18:00"},
            ]},
        ],
    }


def test_arrival_check_in_and_day_trip_return_are_left_alone() -> None:
    plan = _plan()
    plan["day_wise_itinerary"] = plan["day_wise_itinerary"][:2]

    assert day_order.misplaced_stays(plan) == []
    assert day_order.normalize(plan) is False


def test_checkout_after_departure_moves_before_it_and_loses_its_impossible_time() -> None:
    plan = _plan()

    assert day_order.misplaced_stays(plan) == [
        "Day 3: Radisson (Checkout) after Drive: Mysore to Bangalore"
    ]
    assert day_order.normalize(plan)

    stops = plan["day_wise_itinerary"][2]["stops"]
    assert [stop["name"] for stop in stops][:2] == ["Radisson", "Drive: Mysore to Bangalore"]
    assert "time" not in stops[0]
    assert day_order.misplaced_stays(plan) == []


def test_previous_nights_stay_is_recognised_without_a_note() -> None:
    plan = _plan()
    day = plan["day_wise_itinerary"][2]
    day["stops"][1]["note"] = ""

    assert day_order.misplaced_stays(plan)[0].startswith("Day 3: Radisson")


def test_a_night_after_the_journey_home_is_not_paid_for() -> None:
    plan = _plan()
    day = plan["day_wise_itinerary"][2]
    # Check out, then the day ends with the drive home on the 12th.
    day["stops"] = [day["stops"][1], day["stops"][0]]
    assert day_order.unused_nights(plan) == [
        "Radisson checks out 2027-09-13 after leaving on 2027-09-12"
    ]
    assert day_order.trim_unused_nights(plan)

    hotel = plan["selected_hotels"][0]
    assert (hotel["checkout"], hotel["total_price"]) == ("2027-09-12", 13000)
    assert day_order.unused_nights(plan) == []


def test_backward_times_are_reported_not_reordered() -> None:
    plan = _plan()
    plan["day_wise_itinerary"][2]["stops"].append(
        {"name": "Coffee", "kind": "meal", "time": "09:00"}
    )
    before = [stop["name"] for stop in plan["day_wise_itinerary"][2]["stops"]]

    assert day_order.out_of_order(plan) == [
        "Day 3: Coffee at 09:00 is listed after Flight: Bangalore to Delhi at 18:00"
    ]
    day_order.normalize(plan)
    after = [stop["name"] for stop in plan["day_wise_itinerary"][2]["stops"]]
    assert after.index("Coffee") == len(after) - 1 and set(after) == set(before)
