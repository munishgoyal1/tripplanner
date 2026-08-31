from __future__ import annotations

import json

from tripplanner import provider_usage, storage_cosmos
from tripplanner.observability import add_event_observer, app_event, remove_event_observer
from tripplanner.usage_attribution import usage_scope


def test_usage_scope_writes_content_safe_interaction_study_trace(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    observed: list[tuple[str, dict]] = []

    def observer(kind: str, fields: dict) -> None:
        observed.append((kind, fields))

    add_event_observer(observer)

    try:
        with usage_scope(
            "user_trip",
            interaction_id="turn-1",
            trip_id="trip-1",
            interaction_kind="new_trip",
        ):
            app_event(
                "tool_call",
                tool="search_places",
                status="ok",
                cache_hit=True,
                claims=["Dinner at 8 PM costs $50"],
            )
            provider_usage.record_call(
                provider="google",
                operation="text_search",
                sku_class="essentials",
                status="ok",
                duration_ms=42,
            )
    finally:
        remove_event_observer(observer)

    paths = list((tmp_path / "trip-telemetry" / "interactions").glob("*/*.json"))
    assert len(paths) == 1
    trace = json.loads(paths[0].read_text(encoding="utf-8"))
    assert trace["interaction"]["interaction_id"] == "turn-1"
    assert [event["kind"] for event in trace["events"]] == [
        "tool_call",
        "provider_call",
    ]
    assert trace["events"][0]["cache_hit"] is True
    assert trace["provider_calls"][0]["provider"] == "google"
    assert "content" not in json.dumps(trace)
    assert "claims" not in json.dumps(trace)
    provider_event = next(fields for kind, fields in observed if kind == "provider_call")
    assert provider_event["interaction_id"] == "turn-1"
    assert provider_event["trip_id"] == "trip-1"


def test_local_interaction_trace_failure_does_not_fail_scope(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    monkeypatch.setattr(
        "tripplanner.interaction_telemetry.atomic_write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read only")),
    )

    with usage_scope("user_trip", interaction_id="turn-write-fails"):
        app_event("tool_call", tool="get_trip_plan", status="ok")


def test_nested_trip_scope_labels_the_shared_interaction_trace(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)

    with usage_scope("user_action", interaction_id="middleware-generated"):
        app_event("request_started", status="ok")
        with usage_scope(
            "user_trip",
            interaction_id="turn-nested",
            trip_id="trip-1",
            interaction_kind="trip_update",
        ):
            app_event("tool_call", tool="get_trip_plan", status="ok")

    path = next((tmp_path / "trip-telemetry" / "interactions").glob("*/*.json"))
    trace = json.loads(path.read_text(encoding="utf-8"))
    assert trace["interaction"]["initiator"] == "user_trip"
    assert trace["interaction"]["interaction_kind"] == "trip_update"
    assert trace["interaction"]["trip_id"] == "trip-1"
    assert {event["interaction_id"] for event in trace["events"]} == {"turn-nested"}
