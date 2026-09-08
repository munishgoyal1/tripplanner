"""Read-only tool exposing deterministic trip-shape planning intelligence."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from langchain_core.tools import tool

from tripplanner.planning_intelligence import recommend_trip_shape
from tripplanner.platform_planning_insights import get_platform_planning_prior
from tripplanner.tools.user_preferences import load_preferences


@tool
def recommend_trip_duration(
    destination: str,
    destination_scope: str = "city",
    candidate_places_json: str = "[]",
    explicit_days: int = 0,
) -> str:
    """Recommend a fitting trip duration before creating a new plan.

    Call for every new trip. The user's explicit duration remains authoritative.
    Otherwise pass 4-12 likely preference-matched anchor experiences with realistic
    ``duration_min``, ``priority`` (must_do/preferred/recommended/optional), and an
    optional geographic ``cluster``. ``destination_scope`` is one of city, region,
    resort, road_trip, or remote. The result is explainable and contains no mutation.
    """
    try:
        candidates: Any = json.loads(candidate_places_json)
    except json.JSONDecodeError:
        return "Error: candidate_places_json must be valid JSON."
    if not isinstance(candidates, list):
        return "Error: candidate_places_json must be a JSON array."
    if len(candidates) > 30:
        return "Error: at most 30 candidate places may be assessed."

    recommendation = recommend_trip_shape(
        destination=destination,
        destination_scope=destination_scope,
        candidate_places=candidates,
        preferences=load_preferences(),
        explicit_days=explicit_days or None,
        platform_prior=get_platform_planning_prior(destination, destination_scope),
    )
    return json.dumps(asdict(recommendation), ensure_ascii=False, sort_keys=True)
