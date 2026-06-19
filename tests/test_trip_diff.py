"""Tests for the structural trip-plan diff used by update_trip_plan."""

from __future__ import annotations

from tripplanner.tools.trip_diff import diff_plans, format_diff


def _plan(**overrides):
    base = {
        "status": "draft",
        "destination": "Paris",
        "origin": "Mumbai",
        "departure_date": "2026-09-10",
        "return_date": "2026-09-15",
        "travelers": "2 adults",
        "selected_flights": [{"airline": "Air France", "price": 50000}],
        "selected_hotels": [{"name": "Hotel des Tuileries"}],
        "selected_activities": [{"name": "Eiffel Tower"}],
        "day_wise_itinerary": [{"day": 1, "plan": "Arrive + Eiffel"}],
        "total_cost": 50000,
    }
    base.update(overrides)
    return base


def test_no_change_returns_empty() -> None:
    assert diff_plans(_plan(), _plan()) == []


def test_swap_hotel_phrased_as_swap() -> None:
    after = _plan(selected_hotels=[{"name": "Hotel Lutetia"}])
    bullets = diff_plans(_plan(), after)
    assert any("swapped hotel" in b.lower() for b in bullets)
    assert any("Hotel des Tuileries" in b and "Hotel Lutetia" in b for b in bullets)


def test_add_activity() -> None:
    after = _plan(
        selected_activities=[{"name": "Eiffel Tower"}, {"name": "Louvre"}]
    )
    bullets = diff_plans(_plan(), after)
    assert any("added activity" in b.lower() and "Louvre" in b for b in bullets)


def test_remove_activity() -> None:
    after = _plan(selected_activities=[])
    bullets = diff_plans(_plan(), after)
    assert any("removed activity" in b.lower() and "Eiffel" in b for b in bullets)


def test_total_cost_delta_signed() -> None:
    after = _plan(total_cost=75000)
    bullets = diff_plans(_plan(), after)
    assert any("total cost" in b.lower() and "+25,000" in b for b in bullets)


def test_destination_change() -> None:
    after = _plan(destination="Rome")
    bullets = diff_plans(_plan(), after)
    assert any("destination" in b.lower() and "Paris" in b and "Rome" in b for b in bullets)


def test_new_plan_when_before_none() -> None:
    assert diff_plans(None, _plan()) == ["new plan created"]


def test_format_diff_empty() -> None:
    assert format_diff([]) == "no material changes"


def test_format_diff_bullets() -> None:
    text = format_diff(["swapped hotel: 'A' \u2192 'B'", "added activity: 'X'"])
    assert text.count("\u2022") == 2
    assert "swapped hotel" in text and "added activity" in text
