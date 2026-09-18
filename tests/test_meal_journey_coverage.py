import pytest

from tripplanner.tools.trip_validation import _restaurant_itinerary_warnings


def drive(time, duration):
    return {
        "kind": "transport",
        "name": "Drive: Bangalore to Madurai",
        "time": time,
        "duration_min": duration,
    }


def meal(time, duration=60, note=""):
    return {
        "kind": "meal",
        "name": "Sree Sabarees",
        "time": time,
        "duration_min": duration,
        "note": note,
    }


def warnings(stops, **kwargs):
    return _restaurant_itinerary_warnings([{"day": 1, "stops": stops}], **kwargs)


@pytest.mark.parametrize(
    "stops",
    [
        [drive("06:00", 540), meal("20:00")],
        [drive("06:00", 180), drive("09:00", 180), drive("12:00", 180)],
        [drive("06:00", 540), meal("12:00")],
        [drive("08:00", 540), meal("12:00", 5)],
        [drive("", 540), meal("12:00")],
        [drive("08:00", 540), meal("16:45")],
    ],
)
def test_long_driving_requires_usable_meals_inside_the_journey(stops):
    assert any("meal break" in message for message in warnings(stops))


@pytest.mark.parametrize(
    "stops",
    [
        [drive("08:00", 540), meal("12:00")],
        [
            drive("08:00", 180),
            meal("11:00"),
            drive("12:00", 180),
            meal("15:00"),
            drive("16:00", 180),
        ],
        [drive("08:00", 120)],
    ],
)
def test_real_breaks_cover_whole_and_split_drives(stops):
    assert warnings(stops) == []


@pytest.mark.parametrize(
    "note",
    [
        "Vegetarian options",
        "Vegetarian; gluten-free unavailable",
        "Vegetarian; check gluten-free availability",
        "Vegetarian; gluten-free not confirmed",
    ],
)
def test_all_dietary_restrictions_need_positive_evidence(note):
    assert any(
        "gluten-free" in message
        for message in warnings([meal("12:00", note=note)], dietary=["vegetarian", "gluten-free"])
    )


def test_each_meal_needs_every_restriction():
    assert warnings(
        [
            meal("12:00", note="Vegetarian and gluten-free options available"),
            meal("19:00", note="Vegetarian only"),
        ],
        dietary=["vegetarian", "gluten-free"],
    )
    assert (
        warnings(
            [meal("12:00", note="Vegetarian and gluten-free options available")],
            dietary=["vegetarian", "gluten-free"],
        )
        == []
    )


def test_nonvegetarian_does_not_confirm_vegetarian():
    assert warnings([meal("12:00", note="Non-vegetarian restaurant")], dietary=["vegetarian"])


def test_dietary_gap_requires_research_before_finalization():
    from langchain_core.messages import AIMessage, HumanMessage
    from tripplanner.graph_policy import trip_restaurant_search_requirement

    plan = {
        "preferences_snapshot": {"food_preferences": {"dietary": ["vegetarian", "gluten-free"]}},
        "day_wise_itinerary": [{"day": 1, "stops": [meal("12:00", note="Vegetarian only")]}],
    }
    requirement = trip_restaurant_search_requirement(
        [
            HumanMessage(content="Plan my trip"),
            AIMessage(
                content="", tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "save"}]
            ),
        ],
        plan,
        has_planning_intent=True,
    )
    assert "gluten-free" in requirement
