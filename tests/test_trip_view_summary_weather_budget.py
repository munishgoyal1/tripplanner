"""Trip-view summary, weather, budget, and traveler-context tests."""

from __future__ import annotations

import pytest

from tests.support.trip_view import SAMPLE_TRIP
from tripplanner.web import trip_view

pytestmark = pytest.mark.usefixtures("_no_network")


def test_build_weather_normalizes_forecast_and_packing() -> None:
    weather = trip_view.build_weather(
        {
            "weather": {
                "source": "forecast",
                "days": [
                    {
                        "date": "2026-07-14",
                        "summary": "Heavy rain",
                        "high_c": 30,
                        "low_c": 24,
                        "precip_mm": 18,
                        "precip_probability_pct": 85,
                    }
                ],
            }
        }
    )

    assert weather is not None
    assert weather["source_label"] == "Live forecast"
    assert weather["days"][0]["condition"] == "rain"
    assert weather["days"][0]["high_c"] == 30
    assert any("breathable" in item for item in weather["packing_advice"])
    assert any("umbrella" in item for item in weather["packing_advice"])


def test_build_weather_labels_agent_fallback_honestly() -> None:
    weather = trip_view.build_weather(
        {
            "weather": {
                "source": "agent_climate_estimate",
                "note": "Open-Meteo was unavailable.",
                "days": [
                    {"date": "2026-12-02", "summary": "Typically cool", "high_c": 17, "low_c": 8}
                ],
            }
        }
    )

    assert weather is not None
    assert weather["source_label"] == "Typical monthly pattern"
    assert weather["note"] == "Open-Meteo was unavailable."
    assert any("jacket" in item for item in weather["packing_advice"])


def test_itinerary_matches_weather_to_day_date() -> None:
    trip = {
        **SAMPLE_TRIP,
        "weather": {
            "source": "seasonal_estimate",
            "days": [
                {"date": "2026-01-10", "summary": "Clear", "high_c": 27, "low_c": 18},
                {"date": "2026-01-11", "summary": "Rain", "high_c": 25, "low_c": 17},
            ],
        },
        "day_wise_itinerary": [
            {"day": 1, "date": "2026-01-10", "stops": []},
            {"day": 2, "date": "2026-01-11", "stops": []},
        ],
    }

    itinerary = trip_view.build_itinerary(trip)

    assert itinerary["days"][0]["weather"]["condition"] == "clear"
    assert itinerary["days"][1]["weather"]["condition"] == "rain"


def test_overview_counts_unique_itinerary_places() -> None:
    trip = {
        "selected_flights": [],
        "selected_hotels": [{"name": "Hotel A"}],
        "selected_activities": [{"name": "Fort Aguada"}],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Hotel A", "kind": "hotel"},
                    {"name": "Fort Aguada", "kind": "attraction"},
                    {"name": "Britto's", "kind": "meal"},
                    {"name": "Taxi", "kind": "transport"},
                    {"name": "Hotel A", "kind": "hotel"},
                ],
            },
            {"day": 2, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
        ],
    }

    assert trip_view._build_overview(trip)["counts"] == {
        "flights": 0,
        "hotels": 1,
        "activities": 2,
        "days": 2,
    }


def test_fmt_money_default_rupee() -> None:
    assert trip_view.fmt_money(82000) == "\u20b982,000"
    assert trip_view.fmt_money(0) == "\u2014"
    assert trip_view.fmt_money(None) == "\u2014"


def test_build_budget_none_when_no_spend_or_target() -> None:
    assert trip_view.build_budget(None) is None
    assert trip_view.build_budget({"destination": "Goa"}) is None


def test_build_budget_spent_without_target() -> None:
    b = trip_view.build_budget(SAMPLE_TRIP)
    assert b is not None
    assert b["spent"] == 82000
    assert b["currency"] == "\u20b9"
    assert b["travelers"] == 2
    assert b["per_traveler"] == 41000
    assert b["target"] is None
    assert b["pct_used"] is None
    assert b["over_budget"] is False
    # breakdown sums per-item prices for the categories that have them
    assert b["breakdown"]["flights"] == 8500
    assert b["breakdown"]["hotels"] == 12000
    assert "activities" not in b["breakdown"]


def test_build_budget_with_target_under() -> None:
    trip = {**SAMPLE_TRIP, "budget": 100000, "total_cost": 80000}
    b = trip_view.build_budget(trip)
    assert b is not None
    assert b["target"] == 100000
    assert b["remaining"] == 20000
    assert b["pct_used"] == 80
    assert b["over_budget"] is False


def test_build_budget_accepts_structured_user_owned_target() -> None:
    trip = {
        **SAMPLE_TRIP,
        "currency": "USD",
        "total_cost": 8000,
        "budget": {
            "amount": 10000,
            "currency": "USD",
            "owner": "user",
            "updated_at": "2026-08-10T17:55:00Z",
        },
    }

    budget = trip_view.build_budget(trip)

    assert budget is not None
    assert budget["target"] == 10000
    assert budget["target_currency"] == "USD"
    assert budget["target_owner"] == "user"
    assert budget["target_updated_at"] == "2026-08-10T17:55:00Z"
    assert budget["remaining"] == 2000


def test_build_budget_over_target() -> None:
    trip = {**SAMPLE_TRIP, "budget": 60000, "total_cost": 82000}
    b = trip_view.build_budget(trip)
    assert b is not None
    assert b["over_budget"] is True
    assert b["remaining"] == -22000
    assert b["remaining_display"] == "\u20b922,000"  # absolute value for display


def test_build_budget_respects_currency() -> None:
    trip = {**SAMPLE_TRIP, "currency": "USD", "total_cost": 3000}
    b = trip_view.build_budget(trip)
    assert b is not None
    assert b["currency"] == "$"
    assert b["spent_display"] == "$3,000"


def test_build_budget_falls_back_to_item_sum() -> None:
    trip = {
        "destination": "Goa",
        "travelers": "2 adults, 1 child (ages 5)",
        "selected_flights": [{"price": "\u20b910,000"}],
        "selected_hotels": [{"name": "X", "price": 5000}],
        "selected_activities": [],
        "total_cost": 0,
    }
    b = trip_view.build_budget(trip)
    assert b is not None
    assert b["spent"] == 15000
    assert b["travelers"] == 3  # ages 5 not counted as a head


def test_traveler_count_parsing() -> None:
    assert trip_view.traveler_count("2 adults") == 2
    assert trip_view.traveler_count("2 adults, 1 child (ages 5)") == 3
    assert trip_view.traveler_count("") == 1
    assert trip_view.traveler_count(4) == 4


def test_overview_includes_budget() -> None:
    view = trip_view.build_view({**SAMPLE_TRIP, "budget": 100000}, None)
    assert view["overview"]["budget"]["target"] == 100000
    assert view["overview"]["budget"]["estimated"] is True
    assert view["overview"]["budget"]["evidence_coverage_pct"] == 0


def test_family_pills_empty_when_no_prefs() -> None:
    assert trip_view.family_pills(None) == []
    assert trip_view.family_pills({}) == []


def test_family_pills_kids_seniors_pets_diet_accessibility() -> None:
    prefs = {
        "family_members": [
            {"relationship": "spouse", "name": "A", "age": 38, "dietary": "vegetarian"},
            {"relationship": "daughter", "name": "R", "age": 6},
            {"relationship": "son", "name": "K", "age": 10},
            {"relationship": "father", "name": "P", "age": 72, "mobility": "uses walking stick"},
            {"relationship": "dog", "name": "Bruno"},
        ],
        "food_preferences": {"dietary": ["jain"]},
        "accessibility_needs": ["wheelchair access"],
    }
    pills = trip_view.family_pills(prefs)
    joined = " | ".join(pills)
    assert "Kid-friendly (ages 6,10)" in joined
    assert "Senior-friendly" in joined and "uses walking stick" in joined
    assert "Pet-friendly" in joined
    assert "Vegetarian" in joined and "Jain" in joined
    assert "Wheelchair Access" in joined


def test_family_pills_teen_bucket() -> None:
    prefs = {"family_members": [{"relationship": "son", "name": "T", "age": 15}]}
    pills = trip_view.family_pills(prefs)
    assert any("Teen-friendly" in p for p in pills)
    assert not any("Kid-friendly" in p for p in pills)


def test_family_pills_reads_a_traveller_field_stored_as_a_list() -> None:
    """Chat learning writes lists here; the profile editor writes strings.

    A list reached .strip() and took the whole trip view down with a 500, so
    the itinerary, map and guide all went blank for anyone travelling with a
    relative whose mobility had been noted.
    """
    prefs = {
        "family_members": [
            {"relationship": "parent", "age": 72, "mobility": ["uses walking stick"]},
            {"relationship": "spouse", "age": 40, "dietary": ["vegetarian"]},
        ]
    }

    joined = " | ".join(trip_view.family_pills(prefs))

    assert "Senior-friendly (uses walking stick)" in joined
    assert "Vegetarian" in joined


def test_family_pills_joins_several_noted_needs() -> None:
    prefs = {
        "family_members": [
            {"relationship": "parent", "age": 70, "mobility": ["walking stick", "no stairs"]}
        ]
    }

    assert "walking stick, no stairs" in " | ".join(trip_view.family_pills(prefs))


def test_family_pills_surfaced_in_view(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        trip_view.user_preferences,
        "load_preferences",
        lambda: {"family_members": [{"relationship": "daughter", "name": "R", "age": 7}]},
    )
    view = trip_view.build_view(SAMPLE_TRIP, None)
    pills = view["overview"]["family_pills"]
    assert any("Kid-friendly" in p for p in pills)
