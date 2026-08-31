from __future__ import annotations

from tripplanner.observability import app_event
from tripplanner.validation.harness import EvidenceCollector, harness_scope


def test_harness_scope_correlates_and_collects_app_events() -> None:
    with harness_scope(
        "open-destination", run_id="run-1", action_id="open-guide", environment="test"
    ):
        with EvidenceCollector("run-1", "open-destination", "test") as collector:
            app_event("provider_call", operation="text_search", status="ok")

    payload = collector.evidence.as_dict()
    assert payload["version"] == 1
    assert payload["run_id"] == "run-1"
    assert payload["scenario_id"] == "open-destination"
    assert payload["environment"] == "test"
    assert payload["events"] == [
        {
            "kind": "provider_call",
            "fields": {
                    "initiator": "audit",
                    "interaction_id": "run-1",
                    "interaction_kind": "other",
                    "route": "open-guide",
                "run_id": "run-1",
                "scenario_id": "open-destination",
                "action_id": "open-guide",
                "environment": "test",
                "operation": "text_search",
                "status": "ok",
                "user_id": None,
                "event_kind": "provider_call",
            },
        }
    ]


def test_collector_ignores_events_from_other_runs() -> None:
    with EvidenceCollector("wanted", "scenario") as collector:
        with harness_scope("scenario", run_id="other"):
            app_event("provider_call", operation="photo_media")

    assert collector.evidence.events == []
