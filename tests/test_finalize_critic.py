"""Tests for the deterministic self-correction critic on finalize_trip."""

from __future__ import annotations

from tripplanner.tools.finalize_critic import critique


def _plan(**overrides):
    base = {
        "destination": "Paris",
        "departure_date": "2026-09-10",
        "return_date": "2026-09-15",
        "selected_flights": [{"airline": "AF", "from": "BOM", "to": "CDG"}],
        "selected_hotels": [{"name": "Hotel des Tuileries, Paris", "city": "Paris"}],
        "selected_activities": [{"name": "Eiffel Tower visit"}],
        "day_wise_itinerary": [{"day": 1, "plan": "Eiffel + dinner"}],
    }
    base.update(overrides)
    return base


def test_clean_plan_returns_no_heads_up() -> None:
    assert critique(_plan(), prefs={}) == []


def test_return_before_departure_flagged() -> None:
    out = critique(_plan(departure_date="2026-09-15", return_date="2026-09-10"), prefs={})
    assert any("before departure" in s for s in out)


def test_hotel_mismatch_flagged() -> None:
    plan = _plan(selected_hotels=[{"name": "Lyon Grand Hotel", "city": "Lyon"}])
    out = critique(plan, prefs={})
    assert any("Paris" in s and "hotel" in s.lower() for s in out)


def test_missing_flights_for_multiday_trip_flagged() -> None:
    plan = _plan(selected_flights=[])
    out = critique(plan, prefs={})
    assert any("flight" in s.lower() for s in out)


def test_kid_unfriendly_activities_flagged() -> None:
    prefs = {
        "family_members": [
            {"relationship": "child", "name": "Aanya", "age": 7},
        ],
    }
    plan = _plan(selected_activities=[{"name": "Wine cellar tasting tour"}])
    out = critique(plan, prefs)
    assert any("kid" in s.lower() for s in out)


def test_kid_friendly_activities_pass() -> None:
    prefs = {
        "family_members": [
            {"relationship": "child", "name": "Aanya", "age": 7},
        ],
    }
    plan = _plan(selected_activities=[{"name": "Paris zoo and park"}])
    assert critique(plan, prefs) == []


def test_mobility_needs_without_accessible_choices_flagged() -> None:
    prefs = {
        "family_members": [
            {"relationship": "father", "age": 72, "mobility": "needs wheelchair"},
        ],
    }
    out = critique(_plan(), prefs)
    assert any("accessibility" in s.lower() or "mobility" in s.lower() for s in out)


def test_dietary_needs_not_in_itinerary_flagged() -> None:
    prefs = {"food_preferences": {"dietary": "Jain vegetarian"}}
    plan = _plan(day_wise_itinerary=[{"day": 1, "plan": "Eiffel + steakhouse dinner"}])
    out = critique(plan, prefs)
    assert any("dietary" in s.lower() for s in out)


def test_past_dislike_surfaced() -> None:
    prefs = {
        "learned_notes": [
            {"note": "Disliked on Goa trip: morning flight", "source": "stated"},
        ],
    }
    plan = _plan(selected_flights=[{"airline": "IndiGo", "departure": "morning flight at 5:30"}])
    out = critique(plan, prefs)
    assert any("previously disliked" in s.lower() for s in out)


def test_empty_plan_returns_empty_list() -> None:
    assert critique({}, prefs={}) == []
