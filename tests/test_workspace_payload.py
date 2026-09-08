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
    captured = {}
    monkeypatch.setattr(
        workspace_payload,
        "timed_operation",
        lambda kind, operation: _CapturedOperation(captured, kind, operation),
    )

    workspace_payload.build_workspace_payload(None)

    assert captured == {
        "kind": "workflow_operation",
        "operation": "workspace_projection",
        "entered": True,
        "exited": True,
    }


class _CapturedOperation:
    def __init__(self, captured: dict, kind: str, operation: str) -> None:
        self.captured = captured
        self.captured.update(kind=kind, operation=operation)

    def __enter__(self) -> None:
        self.captured["entered"] = True

    def __exit__(self, *_args: object) -> None:
        self.captured["exited"] = True
