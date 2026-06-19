"""Tests for deterministic trip-plan eval scenarios."""

from __future__ import annotations

from tripplanner.evals import SCENARIOS, evaluate_plan, format_result, scenario_by_id


def _family_dubai_plan() -> dict:
    return {
        "destination": "Dubai",
        "departure_date": "2026-09-10",
        "return_date": "2026-09-15",
        "selected_flights": [{"airline": "Emirates", "price": "INR 50000"}],
        "selected_hotels": [
            {
                "name": "Dubai Marina Family Suites",
                "city": "Dubai",
                "amenities": ["elevator", "wheelchair accessible", "breakfast"],
            }
        ],
        "selected_activities": [
            {"name": "Dubai Aquarium family visit", "notes": "kid-friendly, lift access"},
            {"name": "Accessible desert dinner", "notes": "short walks"},
        ],
        "day_wise_itinerary": [
            {"day": 1, "plan": "Arrival, vegetarian dinner near hotel"},
            {"day": 2, "plan": "Optimized route: hotel -> aquarium -> mall; short taxi hops"},
        ],
        "total_cost": 140000,
    }


def test_builtin_scenario_ids_are_unique() -> None:
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def test_scenario_by_id_returns_known_scenario() -> None:
    scenario = scenario_by_id("family_dubai_accessible")
    assert scenario.name == "Dubai family trip with elderly parent"


def test_family_accessibility_plan_passes() -> None:
    scenario = scenario_by_id("family_dubai_accessible")
    result = evaluate_plan(scenario, _family_dubai_plan())

    assert result.passed is True
    assert result.score == 1.0
    assert result.failures == ()
    assert format_result(result).startswith("PASS family_dubai_accessible")


def test_family_accessibility_plan_fails_on_missing_accessibility() -> None:
    scenario = scenario_by_id("family_dubai_accessible")
    plan = _family_dubai_plan()
    plan["selected_hotels"] = [{"name": "Dubai Marina Family Suites", "city": "Dubai"}]
    plan["selected_activities"] = [{"name": "Dubai Aquarium family visit"}]

    result = evaluate_plan(scenario, plan)

    assert result.passed is False
    assert any(c.id == "mobility_accessible" for c in result.failures)
    assert result.score < 1.0


def test_budget_grounding_plan_passes_with_evidenced_prices() -> None:
    scenario = scenario_by_id("budget_grounding_goa")
    plan = {
        "destination": "Goa",
        "departure_date": "2026-08-01",
        "return_date": "2026-08-05",
        "selected_flights": [{"airline": "IndiGo", "price": "INR 18500"}],
        "selected_hotels": [{"name": "Family Beach Resort Goa", "city": "Goa"}],
        "selected_activities": [{"name": "Spice plantation tour", "price": "INR 3500"}],
        "day_wise_itinerary": [{"day": 1, "plan": "Beach arrival and seafood shack"}],
        "total_cost": 66500,
    }
    reply = (
        "The plan totals INR 66500: flights INR 18500, hotel INR 42000, "
        "spice plantation INR 3500, and transfer INR 2500."
    )

    result = evaluate_plan(scenario, plan, final_reply=reply)

    assert result.passed is True
    assert result.score == 1.0


def test_budget_grounding_fails_for_unverified_reply_price() -> None:
    scenario = scenario_by_id("budget_grounding_goa")
    plan = {
        "destination": "Goa",
        "departure_date": "2026-08-01",
        "return_date": "2026-08-05",
        "selected_flights": [{"airline": "IndiGo", "price": "INR 18500"}],
        "selected_hotels": [{"name": "Family Beach Resort Goa", "city": "Goa"}],
        "selected_activities": [{"name": "Spice plantation tour", "price": "INR 3500"}],
        "day_wise_itinerary": [{"day": 1, "plan": "Beach arrival"}],
        "total_cost": 66500,
    }

    result = evaluate_plan(scenario, plan, final_reply="This plan totals INR 70000.")

    assert result.passed is False
    failure = next(c for c in result.failures if c.id == "grounded_reply")
    assert "INR 70000" in failure.reason


def test_budget_check_fails_when_total_exceeds_limit() -> None:
    scenario = scenario_by_id("budget_grounding_goa")
    plan = {
        "destination": "Goa",
        "departure_date": "2026-08-01",
        "return_date": "2026-08-05",
        "selected_flights": [{"airline": "IndiGo", "price": "INR 18500"}],
        "selected_hotels": [{"name": "Family Beach Resort Goa", "city": "Goa"}],
        "day_wise_itinerary": [{"day": 1, "plan": "Beach arrival"}],
        "total_cost": 90000,
    }

    result = evaluate_plan(scenario, plan, final_reply="Flights are INR 18500.")

    assert any(c.id == "within_budget" for c in result.failures)
