"""Assemble the synchronized view-models for the planner workspace."""

from __future__ import annotations

from typing import Any

from tripplanner.observability import timed_operation
from tripplanner.web import trip_view


def build_workspace_payload(
    plan: dict[str, Any] | None,
    focus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build every panel from one already-loaded trip snapshot."""
    with timed_operation("workflow_operation", "workspace_projection"):
        with timed_operation("workflow_operation", "workspace_details_projection"):
            view = trip_view.build_view(plan, focus)
        with timed_operation("workflow_operation", "workspace_map_projection"):
            map_view = trip_view.build_map_view(plan)
        with timed_operation("workflow_operation", "workspace_itinerary_projection"):
            itinerary = trip_view.build_itinerary(plan)
        return {
            "ok": True,
            "view": view,
            "map": map_view,
            "itinerary": itinerary,
        }
