from __future__ import annotations

import json

from tripplanner.planning_intelligence import (
    PlatformPlanningPrior,
    assess_itinerary_density,
    recommend_trip_shape,
)
from tripplanner.tools import trip_shape
from tripplanner.tools.trip_planner import (
    core_planning_completion_gaps,
    planning_completion_gaps,
)


def _balanced_preferences() -> dict:
    return {
        "trip_style": "balanced",
        "planning_preferences": {},
        "past_trips": [],
    }


def test_balanced_city_break_uses_evidence_instead_of_seven_day_default() -> None:
    places = [
        {"name": name, "duration_min": 90, "priority": "must_do"}
        for name in (
            "Mysore Palace",
            "Devaraja Market",
            "Chamundi Hills",
            "St Philomena's Cathedral",
            "Rail Museum",
            "Brindavan Gardens",
        )
    ]

    result = recommend_trip_shape(
        destination="Mysore",
        destination_scope="city",
        candidate_places=places,
        preferences=_balanced_preferences(),
    )

    assert result.recommended_days == 3
    assert result.recommended_range == (2, 4)
    assert result.user_duration_is_authoritative is False
    assert result.evidence_place_count == 6


def test_explicit_duration_remains_authoritative() -> None:
    result = recommend_trip_shape(
        destination="Mysore",
        destination_scope="city",
        candidate_places=[],
        preferences=_balanced_preferences(),
        explicit_days=7,
    )

    assert result.recommended_days == 7
    assert result.user_duration_is_authoritative is True


def test_explicit_free_time_and_daily_attraction_preferences_shape_duration() -> None:
    places = [
        {"name": f"Place {index}", "duration_min": 90, "priority": "must_do"}
        for index in range(6)
    ]
    preferences = _balanced_preferences()
    preferences["planning_preferences"] = {
        "preferred_free_time_ratio": 0.3,
        "major_attractions_per_day": 2,
    }

    result = recommend_trip_shape(
        destination="Mysore",
        destination_scope="city",
        candidate_places=places,
        preferences=preferences,
    )

    assert result.recommended_days == 4
    assert any("free time" in reason for reason in result.reasons)


def test_sparse_full_day_is_flagged_but_deliberate_leisure_is_not() -> None:
    itinerary = [
        {
            "day": 1,
            "title": "Palace morning",
            "stops": [
                {"name": "Hotel", "kind": "hotel"},
                {"name": "Mysore Palace", "kind": "attraction", "duration_min": 90},
                {"name": "Hotel", "kind": "hotel"},
            ],
        },
        {
            "day": 2,
            "title": "Deliberate rest and spa day",
            "stops": [
                {"name": "Hotel", "kind": "hotel"},
                {"name": "Hotel spa", "kind": "other", "duration_min": 90},
                {"name": "Hotel", "kind": "hotel"},
            ],
        },
        {
            "day": 3,
            "title": "Market and gardens",
            "stops": [
                {"name": "Hotel", "kind": "hotel"},
                {"name": "Devaraja Market", "kind": "attraction", "duration_min": 120},
                {"name": "Brindavan Gardens", "kind": "attraction", "duration_min": 150},
                {"name": "Dinner", "kind": "meal", "duration_min": 60},
                {"name": "Hotel", "kind": "hotel"},
            ],
        },
    ]

    result = assess_itinerary_density(itinerary, _balanced_preferences())

    assert [day.day for day in result.sparse_days] == [1]
    assert result.compression_opportunity_days == 1


def test_platform_prior_requires_a_privacy_safe_cohort() -> None:
    places = [
        {"name": f"Place {index}", "duration_min": 90, "priority": "must_do"}
        for index in range(6)
    ]
    weak_prior = PlatformPlanningPrior(
        median_days=6,
        sample_size=8,
        confidence=0.9,
        version="future-v1",
    )
    strong_prior = PlatformPlanningPrior(
        median_days=4,
        sample_size=40,
        confidence=0.8,
        version="future-v1",
    )

    ignored = recommend_trip_shape(
        destination="Mysore",
        destination_scope="city",
        candidate_places=places,
        preferences=_balanced_preferences(),
        platform_prior=weak_prior,
    )
    applied = recommend_trip_shape(
        destination="Mysore",
        destination_scope="city",
        candidate_places=places,
        preferences=_balanced_preferences(),
        platform_prior=strong_prior,
    )

    assert ignored.recommended_days == 3
    assert ignored.platform_prior_applied is False
    assert applied.recommended_days == 4
    assert applied.platform_prior_applied is True


def test_duration_tool_uses_saved_preferences_and_returns_auditable_json(
    monkeypatch,
) -> None:
    monkeypatch.setattr(trip_shape, "load_preferences", _balanced_preferences)

    result = trip_shape.recommend_trip_duration.invoke({
        "destination": "Mysore",
        "destination_scope": "city",
        "candidate_places_json": "[]",
    })

    assert '"recommended_days": 3' in result
    assert '"platform_prior_applied": false' in result


def test_duration_tool_uses_only_eligible_platform_prior(monkeypatch) -> None:
    monkeypatch.setattr(trip_shape, "load_preferences", _balanced_preferences)
    monkeypatch.setattr(
        trip_shape,
        "get_platform_planning_prior",
        lambda _destination, _scope: PlatformPlanningPrior(
            median_days=4,
            sample_size=40,
            confidence=0.8,
            version="cohort-v1",
        ),
    )

    result = json.loads(trip_shape.recommend_trip_duration.invoke({
        "destination": "Mysore",
        "destination_scope": "city",
        "candidate_places_json": json.dumps([
            {"name": f"Place {index}", "duration_min": 90, "priority": "must_do"}
            for index in range(6)
        ]),
    }))

    assert result["recommended_days"] == 4
    assert result["platform_prior_applied"] is True
    assert result["platform_prior_version"] == "cohort-v1"


def test_advisor_enabled_plan_flags_sparse_days_without_affecting_legacy() -> None:
    plan = {
        "planning_recommendation": {
            "target_active_minutes_per_full_day": 360,
            "recommended_days": 3,
        },
        "preferences_snapshot": {"trip_style": "balanced"},
        "day_wise_itinerary": [{
            "day": 1,
            "title": "Palace morning",
            "stops": [
                {"name": "Hotel", "kind": "hotel"},
                {"name": "Mysore Palace", "kind": "attraction", "duration_min": 90},
                {"name": "Hotel", "kind": "hotel"},
            ],
        }],
    }

    assert any("Sparse itinerary" in gap for gap in planning_completion_gaps(plan))
    assert any("Sparse itinerary" in gap for gap in core_planning_completion_gaps(plan))

    legacy_plan = dict(plan)
    legacy_plan.pop("planning_recommendation")
    assert not any(
        "Sparse itinerary" in gap for gap in planning_completion_gaps(legacy_plan)
    )
    assert not any(
        "Sparse itinerary" in gap for gap in core_planning_completion_gaps(legacy_plan)
    )
