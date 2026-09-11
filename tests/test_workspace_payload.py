from __future__ import annotations

from tripplanner.web import workspace_payload


def test_build_workspace_payload_uses_one_plan_for_every_panel(monkeypatch) -> None:
    plan = {"trip_id": "trip-1"}
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        workspace_payload.trip_view,
        "build_view",
        lambda received, focus: calls.append(("view", received)) or {"focus": focus},
    )
    monkeypatch.setattr(
        workspace_payload.trip_view,
        "build_map_view",
        lambda received: calls.append(("map", received)) or {"map": True},
    )
    monkeypatch.setattr(
        workspace_payload.trip_view,
        "build_itinerary",
        lambda received: calls.append(("itinerary", received)) or {"itinerary": True},
    )

    result = workspace_payload.build_workspace_payload(plan)

    assert result == {
        "ok": True,
        "view": {"focus": None},
        "map": {"map": True},
        "itinerary": {"itinerary": True},
    }
    assert calls == [("view", plan), ("map", plan), ("itinerary", plan)]


def test_build_workspace_payload_emits_projection_timing(monkeypatch) -> None:
    captured: list[dict] = []
    monkeypatch.setattr(
        workspace_payload,
        "timed_operation",
        lambda kind, operation: _CapturedOperation(captured, kind, operation),
    )

    workspace_payload.build_workspace_payload(None)

    assert [item["operation"] for item in captured] == [
        "workspace_projection",
        "workspace_details_projection",
        "workspace_map_projection",
        "workspace_itinerary_projection",
    ]
    assert all(item["kind"] == "workflow_operation" for item in captured)
    assert all(item["entered"] and item["exited"] for item in captured)


class _CapturedOperation:
    def __init__(self, captured: list[dict], kind: str, operation: str) -> None:
        self.captured = {"kind": kind, "operation": operation}
        captured.append(self.captured)

    def __enter__(self) -> None:
        self.captured["entered"] = True

    def __exit__(self, *_args: object) -> None:
        self.captured["exited"] = True
