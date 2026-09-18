from copy import deepcopy

import pytest

from tripplanner.decisions import booking_intent as booking
from tripplanner.decisions.apply import _travellers
from tripplanner.decisions.booking_defaults import research_defaults
from tripplanner.party import party_size
from tripplanner.tools.trip_guard import day_dates, validate_plan
from tripplanner.web.budget import traveler_count
from tests.test_booking_intent import make_plan


@pytest.mark.parametrize(
    "party, expected",
    [
        ("5 adults, 2 children (ages 11.5 and 2.5), including 1 elderly mother", 7),
        ("2 adults, 1 infant (age 0.5)", 3),
        ("2 adults, 1 elderly", 3),
        ({"adults": 5, "children": 2, "infants": 1}, 8),
        ("7 people", 7),
        (4.0, 4),
        ("family, ages 11 and 2", None),
    ],
)
def test_shared_party_count_ignores_ages(party, expected):
    assert party_size(party) == expected
    assert _travellers({"travelers": party}) == (expected or 1)
    assert traveler_count(party) == (expected or 1)


def test_matching_family_quote_and_search_defaults_agree():
    plan = make_plan()
    plan["travelers"] = "5 adults, 2 children (ages 11.5 and 2.5)"
    raw = plan["selected_hotels"][0]
    raw["search_context"] = {"adults_per_room": 5, "rooms": 1, "children_ages": [11, 2]}
    assert booking._facts(raw, plan)["context_warning"] == ""
    flight = plan["selected_flights"][0]
    flight["search_context"] = {"adults": 5, "children": 2, "infants": 0}
    assert booking._facts(flight, plan)["context_warning"] == ""
    defaults = research_defaults(plan)["hotels"][0]["search"]
    assert defaults["adults"] == 5
    assert defaults["children_ages"] == [11, 2]
    plan["travelers"] = "family with children aged 11 and 2"
    assert "party/occupancy" in booking._facts(raw, plan)["context_warning"]


def test_calendar_rejects_reversed_duplicate_dates_and_uses_canonical_weekdays():
    from tripplanner.tools.trip_validation import itinerary_coherence_gaps

    plan = {
        "departure_date": "2026-10-12",
        "return_date": "2026-10-14",
        "day_wise_itinerary": [
            {"day": day, "date": text, "stops": []}
            for day, text in [(1, "2026-10-14"), (2, "2026-10-14"), (3, "2026-10-12")]
        ],
    }
    assert [v.day for v in validate_plan(plan) if v.code == "I14"] == [1, 2, 3]
    assert len(itinerary_coherence_gaps(plan)) == 3
    assert day_dates(plan) == {1: "2026-10-12", 2: "2026-10-13", 3: "2026-10-14"}
    for day in plan["day_wise_itinerary"]:
        day["date"] = day_dates(plan)[day["day"]]
    assert not any(v.code == "I14" for v in validate_plan(plan))
    plan["day_wise_itinerary"].append(deepcopy(plan["day_wise_itinerary"][0]))
    assert any("occurs more than once" in gap for gap in itinerary_coherence_gaps(plan))


def report(plan, start, end):
    return booking.prepare_change(
        plan,
        {
            "action": "report",
            "item_id": "stay-goa",
            "actual": {
                "product": "Hotel 1",
                "provider": "Offline",
                "amount": 70000,
                "start_date": start,
                "end_date": end,
            },
        },
    )


def test_shortened_stay_exposes_night_and_clears_place_and_booking_identity(monkeypatch):
    from tripplanner.web import itinerary_view

    plan = make_plan()
    plan["day_wise_itinerary"][0]["stops"][0].update(lat=15.5, lng=73.8, place_id="hotel-old")
    candidate, warnings = report(plan, "2026-12-02", "2026-12-03")
    gap = candidate["day_wise_itinerary"][0]["stops"][0]
    assert gap["name"] == "Hotel TBD" and not gap["booked"]
    assert not any(
        key in gap for key in ("lat", "lng", "place_id", "booking_item_id", "decision_id", "price")
    )
    assert candidate["selected_hotels"][0]["checkin"] == "2026-12-02"
    assert candidate["day_wise_itinerary"][1]["stops"][0]["booked"]
    assert any("2026-12-01 is uncovered" in warning for warning in warnings)
    monkeypatch.setattr(itinerary_view, "_place_coords", lambda *args, **kwargs: None)
    rendered = itinerary_view.build_itinerary(candidate)["days"][0]["stops"]
    assert not any(stop["name"] == "Hotel 1" for stop in rendered)
    assert any(stop["name"] == "Hotel TBD" for stop in rendered)
    assert plan["day_wise_itinerary"][0]["stops"][0]["name"] == "Hotel 1"


def test_checkout_morning_does_not_cover_checkout_night():
    candidate, warnings = report(make_plan(), "2026-12-01", "2026-12-02")
    hotels = candidate["day_wise_itinerary"][1]["stops"]
    assert hotels[0]["stay_role"] == "checkout" and hotels[0]["booked"]
    assert hotels[-1]["name"] == "Hotel TBD" and not hotels[-1]["booked"]
    assert any("2026-12-02 is uncovered" in warning for warning in warnings)


def test_extension_recovers_only_its_own_uncovered_nights():
    candidate, _ = report(make_plan(), "2026-12-02", "2026-12-03")
    extended, _ = report(candidate, "2026-12-01", "2026-12-03")
    assert all(day["stops"][0]["booked"] for day in extended["day_wise_itinerary"])
    assert all(day["stops"][0]["name"] == "Hotel 1" for day in extended["day_wise_itinerary"])


def test_extension_does_not_replace_a_gap_that_was_booked_independently():
    candidate, _ = report(make_plan(), "2026-12-02", "2026-12-03")
    stop = candidate["day_wise_itinerary"][0]["stops"][0]
    stop.update(name="Independent hotel", booking_item_id="independent", booked=True)
    expected = deepcopy(stop)
    extended, warnings = report(candidate, "2026-12-01", "2026-12-03")
    assert extended["day_wise_itinerary"][0]["stops"][0] == expected
    assert not any("2026-12-01 is uncovered" in warning for warning in warnings)


def test_date_extension_preserves_repeat_city_other_booking_identity():
    plan = make_plan()
    other = deepcopy(plan["selected_hotels"][0])
    other.update(
        booking_item_id="second-visit", decision_id="", checkin="2026-12-03", checkout="2026-12-04"
    )
    plan["selected_hotels"].append(other)
    day = {"day": 3, "date": "2026-12-03", "stops": [deepcopy(other) | {"kind": "hotel"}]}
    plan["day_wise_itinerary"].append(day)
    candidate, warnings = report(plan, "2026-12-01", "2026-12-04")
    assert candidate["day_wise_itinerary"][2] == day
    assert candidate["selected_hotels"][1] == other
    assert any("2026-12-03" in warning and "not linked" in warning for warning in warnings)


@pytest.mark.usefixtures("_map_geo")
@pytest.mark.parametrize(
    "start,end,gap_day", [("2026-12-02", "2026-12-03", 1), ("2026-12-01", "2026-12-02", 2)]
)
def test_map_does_not_return_to_a_hotel_on_an_uncovered_night(monkeypatch, start, end, gap_day):
    from tripplanner.web import trip_view

    plan = make_plan()
    plan["day_wise_itinerary"][1]["stops"].append({"kind": "attraction", "name": "Museum"})
    candidate, _ = report(plan, start, end)
    coords = {"Hotel 1": (15.5, 73.8), "Museum": (15.51, 73.81)}

    def summary(name, city, **kwargs):
        lat, lng = coords.get(name, (None, None))
        return {"name": name, "lat": lat, "lng": lng, "place_id": name}

    monkeypatch.setattr(trip_view.places_cache, "get_summary", summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", summary)
    monkeypatch.setattr(trip_view, "_airport_pin", lambda *args: None)
    result = trip_view.build_map_view(candidate)
    pins = {pin["id"]: pin for pin in result["pins"]}
    day = next(day for day in result["days"] if day["day"] == gap_day)
    assert all(pins[leg["to_pin_id"]]["name"] != "Hotel 1" for leg in day["legs"])
    if gap_day == 1:
        assert all(pins[pid]["name"] != "Hotel 1" for pid in day["pin_ids"])
