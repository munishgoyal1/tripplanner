from tripplanner.decisions.booking_intent import build_booking_view


def family_trip():
    return {
        "travelers": "5 adults, 2 children (ages 11.5 and 2.5)",
        "currency": "USD",
        "origin": "Bangalore",
        "destination": "Madurai, Rameshwaram",
        "departure_date": "2026-10-12",
        "return_date": "2026-10-19",
        "selected_hotels": [
            {
                "name": "Heritage Madurai",
                "city": "Madurai",
                "checkin": "2026-10-12",
                "checkout": "2026-10-14",
            },
            {
                "name": "Daiwik",
                "city": "Rameshwaram",
                "checkin": "2026-10-14",
                "checkout": "2026-10-16",
            },
        ],
    }


def test_family_road_trip_defaults_preserve_party_currency_and_each_stay():
    defaults = build_booking_view(family_trip())["research_defaults"]
    flight = defaults["flights"][0]["search"]
    assert (flight["adults"], flight["children"], flight["infants"]) == (5, 2, 0)
    assert flight["currency"] == "USD"
    first, second = defaults["hotels"]
    assert first["search"]["children_ages"] == [11, 2]
    assert (first["search"]["start_date"], first["search"]["end_date"]) == (
        "2026-10-12",
        "2026-10-14",
    )
    assert second["search"]["destination"] == "Rameshwaram"
    assert second["search"]["start_date"] == "2026-10-14"
    assert first["search"]["nationality"] == ""
    assert any("room" in note for note in first["assumptions"])


def test_explicit_adults_only_does_not_inherit_saved_children():
    plan = family_trip()
    plan["travelers"] = "2 adults"
    plan["preferences_snapshot"] = {"family": {"adults": 5, "children": 2, "child_ages": [11, 2]}}
    query = build_booking_view(plan)["research_defaults"]["flights"][0]["search"]
    assert (query["adults"], query["children"], query["infants"]) == (2, 0, 0)
    assert query["children_ages"] == []


def test_under_twos_are_classified_for_provider_search():
    plan = family_trip()
    plan["travelers"] = "2 adults, 2 children (ages 5 and 1)"
    query = build_booking_view(plan)["research_defaults"]["flights"][0]["search"]
    assert (query["children"], query["infants"], query["children_ages"]) == (1, 1, [5, 1])


def test_provider_stay_context_keeps_city_room_allocation_and_nationality():
    plan = family_trip()
    plan["travelers"] = "4 adults, 2 children (11 and 2)"
    hotel = plan["selected_hotels"][0]
    hotel.pop("city")
    hotel["search_context"] = {"destination": "Madurai", "rooms": 2, "adults_per_room": 2, "guest_nationality": "IN"}
    query = build_booking_view(plan)["research_defaults"]["hotels"][0]["search"]
    assert (query["destination"], query["rooms"], query["adults"], query["nationality"]) == ("Madurai", 2, 2, "IN")
    assert query["children_ages"] == [11, 2]
