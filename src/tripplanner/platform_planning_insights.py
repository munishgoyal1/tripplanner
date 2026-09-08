"""Privacy boundary for aggregate planning insights learned across users."""

from __future__ import annotations

from tripplanner.planning_intelligence import PlatformPlanningPrior


def get_platform_planning_prior(
    destination: str,
    destination_scope: str,
) -> PlatformPlanningPrior | None:
    """Return a versioned cohort prior when an aggregate provider is configured.

    The neutral implementation intentionally returns no prior. A future analytics
    adapter may return only anonymized aggregates; eligibility thresholds are
    enforced again by the deterministic recommendation engine.
    """
    del destination, destination_scope
    return None
