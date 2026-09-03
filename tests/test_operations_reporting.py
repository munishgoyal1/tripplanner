from __future__ import annotations

from datetime import UTC, date, datetime

from tripplanner import operations_reporting


def _milliseconds(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=UTC).timestamp() * 1000)


def test_snapshot_joins_cross_user_trip_interactions_and_safe_infra(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    documents = {
        "product_events": [
            {
                "event": "page_view",
                "occurred_at": "2026-08-05T08:00:00+00:00",
                "user_bucket": "visitor-1",
                "page": "welcome",
            },
            {
                "event": "page_view",
                "occurred_at": "2026-08-05T09:00:00+00:00",
                "user_bucket": "visitor-1",
                "page": "planner",
            },
        ],
        "trips": [
            {
                "id": "goa-trip",
                "user_id": "google-user",
                "trip_id": "goa-trip",
                "destination": "Goa",
                "created_at": "2026-08-05T08:30:00Z",
                "updated_at": "2026-08-06T10:00:00Z",
            },
            {
                "id": "older-trip",
                "user_id": "google-user-2",
                "trip_id": "older-trip",
                "destination": "Jaipur",
                "created_at": "2026-01-05T08:30:00Z",
                "updated_at": "2026-01-06T10:00:00Z",
            },
        ],
        "users": [
            {
                "id": "chat_goa-trip",
                "user_id": "google-user",
                "messages": [
                    {
                        "role": "user",
                        "text": "Plan Goa",
                        "ts": _milliseconds("2026-08-05T08:30:00"),
                    },
                    {
                        "role": "assistant",
                        "text": "Built",
                        "seconds": 180,
                        "ts": _milliseconds("2026-08-05T08:33:00"),
                    },
                    {
                        "role": "user",
                        "text": "Add food",
                        "ts": _milliseconds("2026-08-06T10:00:00"),
                    },
                    {
                        "role": "assistant",
                        "text": "Updated",
                        "seconds": 20,
                        "ts": _milliseconds("2026-08-06T10:00:20"),
                    },
                ],
            }
        ],
        "trip_feedback": [
            {
                "id": "feedback-1",
                "user_id": "google-user",
                "trip_id": "goa-trip",
                "sentiment": "up",
                "rating": 4,
                "comment": "More local food",
                "created_at": "2026-08-06T11:00:00Z",
            }
        ],
    }
    monkeypatch.setattr(operations_reporting.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        operations_reporting.storage_cosmos,
        "operations_query",
        lambda container, _query, _parameters=None: documents[container],
    )
    monkeypatch.setattr(
        operations_reporting.storage_cosmos,
        "operations_inventory",
        lambda: {
            "enabled": True,
            "database": "tripplanner-prod",
            "containers": [{"name": "trips", "records": 1, "default_ttl": None}],
        },
    )
    settings = type(
        "Settings",
        (),
        {
            "cosmos_use_managed_identity": True,
            "cosmos_connection_string": "secret-connection",
            "cosmos_key": "secret-key",
            "enable_azure_openai": True,
            "azure_openai_deployment": "gpt-4.1",
            "azure_openai_api_version": "2024-10-21",
            "enable_google_places": True,
            "enable_google_maps": True,
            "google_analytics_measurement_id": "G-TEST",
            "cache_redis_enabled": True,
            "travel_flight_provider": "auto",
            "travel_hotel_provider": "liteapi",
            "travel_activity_provider": "viator",
        },
    )()
    monkeypatch.setattr(operations_reporting, "get_settings", lambda: settings)
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "production")

    result = operations_reporting.snapshot(
        days=30,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 10),
    )

    assert result["business"] == {
        "visitors": 1,
        "page_counts": {"welcome": 1, "planner": 1},
        "new_trips": 1,
        "chat_turns": 2,
        "existing_trip_updates": 1,
    }
    assert result["trips"][0]["user_id"] == "google-user"
    assert result["trips"][0]["places_requested"] == "Goa"
    assert result["trips"][0]["first_build_seconds"] == 180
    assert result["trips"][0]["iterations"] == 1
    assert result["trips"][0]["feedback"] == "up · 4/5 · More local food"
    assert [row["title"] for row in result["trips"]] == ["Goa", "Jaipur"]
    serialized_config = str(result["infra"]["configuration"])
    assert "secret-key" not in serialized_config
    assert "secret-connection" not in serialized_config
    assert "Managed identity" in serialized_config
