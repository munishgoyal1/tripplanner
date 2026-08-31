"""Assemble the synchronized view-models for the planner workspace."""

from __future__ import annotations

from typing import Any

from tripplanner.observability import timed_operation
from tripplanner.web import trip_view


def build_workspace_payload(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Build every panel from one already-loaded trip snapshot."""
    with timed_operation("workflow_operation", "workspace_projection"):
        return {
            "ok": True,
            "view": trip_view.build_view(plan, None),
            "map": trip_view.build_map_view(plan),
            "itinerary": trip_view.build_itinerary(plan),
        }
