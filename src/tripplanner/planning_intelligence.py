"""Deterministic trip-shape recommendations and itinerary density checks."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from statistics import median
from typing import Any

_STYLE_ACTIVE_MINUTES = {
    "relaxed": 300,
    "leisure": 300,
    "balanced": 360,
    "packed": 420,
    "packed_sightseeing": 420,
    "adventure": 420,
    "adventurous": 420,
}
_SCOPE_DEFAULT_DAYS = {
    "city": 3,
    "region": 5,
    "resort": 4,
    "road_trip": 7,
    "remote": 5,
}
_PRIORITY_WEIGHTS = {
    "must_do": 1.0,
    "preferred": 0.85,
    "recommended": 0.75,
    "optional": 0.5,
}
_MIN_PLATFORM_COHORT = 20
_MIN_PLATFORM_CONFIDENCE = 0.6
_LEISURE_RE = re.compile(
    r"\b(rest|leisure|free time|slow day|spa|pool|beach day|unplanned|at your own pace)\b",
    re.I,
)
_PARTIAL_DAY_RE = re.compile(r"\b(arrival|arrive|departure|depart|check[ -]?in)\b", re.I)


@dataclass(frozen=True)
class PlatformPlanningPrior:
    """Privacy-safe aggregate supplied by a future platform-insights provider."""

    median_days: int
    sample_size: int
    confidence: float
    version: str


@dataclass(frozen=True)
class PlanningProfile:
    trip_style: str
    target_active_minutes: int
    preferred_free_time_ratio: float
    major_attractions_per_day: float | None
    sources: tuple[str, ...]


@dataclass(frozen=True)
class TripShapeRecommendation:
    destination: str
    recommended_days: int
    recommended_range: tuple[int, int]
    confidence: str
    evidence_place_count: int
    estimated_planned_minutes: int
    target_active_minutes_per_full_day: int
    user_duration_is_authoritative: bool
    platform_prior_applied: bool
    platform_prior_version: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DayDensity:
    day: int
    planned_minutes: int
    threshold_minutes: int
    reason: str


@dataclass(frozen=True)
class ItineraryDensityAssessment:
    sparse_days: tuple[DayDensity, ...]
    compression_opportunity_days: int
    target_active_minutes_per_full_day: int


def _bounded_number(value: Any, minimum: float, maximum: float) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return min(maximum, max(minimum, float(value)))


def build_planning_profile(preferences: dict[str, Any] | None) -> PlanningProfile:
    prefs = preferences or {}
    style = str(prefs.get("trip_style") or "balanced").strip().lower()
    default_minutes = _STYLE_ACTIVE_MINUTES.get(style, _STYLE_ACTIVE_MINUTES["balanced"])
    planning = prefs.get("planning_preferences")
    planning = planning if isinstance(planning, dict) else {}
    sources = [f"trip_style:{style}"]

    explicit_minutes = _bounded_number(
        planning.get("target_active_minutes_per_full_day"), 180, 600
    )
    history_minutes: list[float] = []
    for trip in prefs.get("past_trips") or []:
        if not isinstance(trip, dict):
            continue
        value = _bounded_number(trip.get("actual_active_minutes_per_full_day"), 180, 600)
        if value is None:
            continue
        pace_feedback = str(trip.get("pace_feedback") or "").strip().lower()
        rating = trip.get("rating")
        if pace_feedback == "too_rushed":
            history_minutes.append(value * 0.85)
        elif pace_feedback == "too_sparse":
            history_minutes.append(value * 1.15)
        elif pace_feedback == "just_right" or (
            isinstance(rating, (int, float)) and rating >= 4
        ):
            history_minutes.append(value)
    if explicit_minutes is not None:
        target_minutes = round(explicit_minutes)
        sources.append("explicit_planning_preference")
    elif history_minutes:
        historical = median(history_minutes[-5:])
        target_minutes = round((default_minutes + historical) / 2)
        sources.append("stated_or_high_rated_trip_pace")
    else:
        target_minutes = default_minutes

    free_time = _bounded_number(planning.get("preferred_free_time_ratio"), 0, 0.6)
    attractions = _bounded_number(planning.get("major_attractions_per_day"), 1, 6)
    if free_time is not None:
        sources.append("explicit_free_time_preference")
    if attractions is not None:
        sources.append("explicit_daily_attraction_preference")
    return PlanningProfile(
        trip_style=style,
        target_active_minutes=target_minutes,
        preferred_free_time_ratio=free_time if free_time is not None else 0.0,
        major_attractions_per_day=attractions,
        sources=tuple(sources),
    )


def _candidate_workload(candidate_places: list[dict[str, Any]]) -> tuple[int, int]:
    planned_minutes = 0.0
    usable_places = 0
    previous_cluster = ""
    for raw in candidate_places:
        if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
            continue
        duration = _bounded_number(raw.get("duration_min"), 30, 480) or 90
        priority = str(raw.get("priority") or "recommended").strip().lower()
        planned_minutes += duration * _PRIORITY_WEIGHTS.get(priority, 0.75)
        cluster = str(raw.get("cluster") or "").strip().lower()
        if usable_places:
            planned_minutes += 30
            if cluster and previous_cluster and cluster != previous_cluster:
                planned_minutes += 30
        previous_cluster = cluster or previous_cluster
        usable_places += 1
    return round(planned_minutes), usable_places


def _minimum_days_for_workload(workload: int, daily_capacity: int) -> int:
    if workload <= 0:
        return 1
    for days in range(1, 22):
        capacity = daily_capacity * max(1, days - 1)
        if capacity >= workload:
            return days
    return 21


def recommend_trip_shape(
    *,
    destination: str,
    destination_scope: str,
    candidate_places: list[dict[str, Any]],
    preferences: dict[str, Any] | None,
    explicit_days: int | None = None,
    platform_prior: PlatformPlanningPrior | None = None,
) -> TripShapeRecommendation:
    """Recommend the shortest useful trip that fits preference-matched evidence."""
    profile = build_planning_profile(preferences)
    workload, place_count = _candidate_workload(candidate_places)
    scope = destination_scope.strip().lower() or "city"
    daily_capacity = max(
        180,
        round(profile.target_active_minutes * (1 - profile.preferred_free_time_ratio)),
    )
    evidence_days = (
        _minimum_days_for_workload(workload, daily_capacity)
        if place_count
        else _SCOPE_DEFAULT_DAYS.get(scope, 3)
    )
    if place_count and profile.major_attractions_per_day is not None:
        evidence_days = max(
            evidence_days,
            math.ceil(place_count / profile.major_attractions_per_day),
        )
    evidence_days = max(1, min(21, evidence_days))
    reasons = [
        f"{place_count} preference-matched places account for about {workload} planned minutes"
        if place_count
        else f"No place-duration evidence was supplied; used the {scope} scope baseline",
        (
            f"{profile.trip_style} pace targets about "
            f"{profile.target_active_minutes} active minutes on a full day"
        ),
    ]
    if profile.preferred_free_time_ratio:
        reasons.append(
            f"Reserved about {profile.preferred_free_time_ratio:.0%} of each full day as free time"
        )
    if profile.major_attractions_per_day is not None:
        reasons.append(
            "Limited major attractions to about "
            f"{profile.major_attractions_per_day:g} per day"
        )

    prior_applied = False
    prior_version: str | None = None
    if (
        platform_prior is not None
        and platform_prior.sample_size >= _MIN_PLATFORM_COHORT
        and platform_prior.confidence >= _MIN_PLATFORM_CONFIDENCE
        and 1 <= platform_prior.median_days <= 21
    ):
        evidence_days += max(-1, min(1, platform_prior.median_days - evidence_days))
        prior_applied = True
        prior_version = platform_prior.version
        reasons.append(
            "Privacy-safe aggregate planning outcomes adjusted the estimate by at most one day"
        )

    explicit_duration = (
        explicit_days
        if isinstance(explicit_days, int) and not isinstance(explicit_days, bool)
        else None
    )
    user_authoritative = explicit_duration is not None
    recommended_days = (
        max(1, min(21, explicit_duration))
        if explicit_duration is not None
        else evidence_days
    )
    if user_authoritative:
        reasons.insert(0, f"The user's explicit {recommended_days}-day duration is authoritative")

    return TripShapeRecommendation(
        destination=destination.strip(),
        recommended_days=recommended_days,
        recommended_range=(max(1, evidence_days - 1), min(21, evidence_days + 1)),
        confidence="high" if place_count >= 5 else "medium" if place_count >= 2 else "low",
        evidence_place_count=place_count,
        estimated_planned_minutes=workload,
        target_active_minutes_per_full_day=profile.target_active_minutes,
        user_duration_is_authoritative=user_authoritative,
        platform_prior_applied=prior_applied,
        platform_prior_version=prior_version,
        reasons=tuple(reasons),
    )


def _planned_day_minutes(day: dict[str, Any]) -> tuple[int, bool]:
    total = 0
    has_transfer = False
    for stop in day.get("stops") or []:
        if not isinstance(stop, dict):
            continue
        kind = str(stop.get("kind") or "other").strip().lower()
        if kind in {"flight", "transport"}:
            has_transfer = True
        if kind == "hotel":
            continue
        duration = _bounded_number(stop.get("duration_min"), 0, 720)
        total += round(duration if duration is not None else 90)
        travel = stop.get("travel_from_previous")
        if isinstance(travel, dict):
            travel_minutes = _bounded_number(travel.get("duration_min"), 0, 480)
            total += round(travel_minutes or 0)
    return total, has_transfer


def assess_itinerary_density(
    itinerary: list[dict[str, Any]],
    preferences: dict[str, Any] | None,
) -> ItineraryDensityAssessment:
    """Identify accidentally sparse full days without penalizing intentional downtime."""
    profile = build_planning_profile(preferences)
    threshold = round(profile.target_active_minutes * 0.55)
    sparse: list[DayDensity] = []
    for index, day in enumerate(itinerary):
        if not isinstance(day, dict):
            continue
        planned_minutes, has_transfer = _planned_day_minutes(day)
        description = " ".join(
            str(day.get(key) or "") for key in ("title", "summary", "note")
        )
        if has_transfer or _LEISURE_RE.search(description):
            continue
        day_threshold = (
            round(profile.target_active_minutes * 0.25)
            if _PARTIAL_DAY_RE.search(description)
            else threshold
        )
        if planned_minutes < day_threshold:
            day_number = int(day.get("day") or index + 1)
            sparse.append(
                DayDensity(
                    day=day_number,
                    planned_minutes=planned_minutes,
                    threshold_minutes=day_threshold,
                    reason=(
                        f"Day {day_number} has about {planned_minutes} planned minutes; "
                        f"this profile's useful-day threshold is {day_threshold} minutes"
                    ),
                )
            )
    return ItineraryDensityAssessment(
        sparse_days=tuple(sparse),
        compression_opportunity_days=len(sparse),
        target_active_minutes_per_full_day=profile.target_active_minutes,
    )
