from __future__ import annotations

from datetime import UTC, datetime

from tripplanner import provider_usage, storage_cosmos
from tripplanner.usage_attribution import annotate_current_batch, usage_scope
from tripplanner.validation.harness.context import harness_scope


def test_summary_preserves_attribution_and_unknown_costs(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    monkeypatch.setattr(
        provider_usage,
        "_now",
        lambda: datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )

    with usage_scope(
        "user_trip",
        interaction_id="request-1",
        trip_id="trip-1",
    ):
        provider_usage.record_call(
            provider="google",
            operation="text_search",
            sku_class="essentials",
            status="ok",
            duration_ms=100,
        )
        provider_usage.record_call(
            provider="tavily",
            operation="request",
            status="ok",
            duration_ms=200,
        )
        provider_usage.record_call(
            provider="azure_openai",
            operation="chat_completion",
            sku_class="gpt-4o-mini",
            status="ok",
            duration_ms=300,
            prompt_tokens=1000,
            completion_tokens=500,
            estimated_cost_usd=0.00045,
        )

    with harness_scope(
        "scenario-1",
        run_id="audit-1",
        environment="local",
    ):
        provider_usage.record_call(
            provider="google",
            operation="photo_media",
            sku_class="photo_media",
            status="TimeoutError",
            duration_ms=400,
        )

    result = provider_usage.summary(days=30)

    assert result["totals"] == {
        "calls": 4,
        "avoided_calls": 0,
        "cache_hits": 0,
        "failures": 1,
        "estimated_cost_usd": 0.03945,
        "estimated_savings_usd": 0,
        "unknown_cost_calls": 1,
        "prompt_tokens": 1000,
        "completion_tokens": 500,
    }
    assert {(row["initiator"], row["calls"]) for row in result["by_initiator"]} == {
        ("user_trip", 3),
        ("audit", 1),
    }
    trip = next(row for row in result["by_trip"] if row["initiator"] == "user_trip")
    assert trip["trip_id"] == "trip-1"
    assert trip["unknown_cost_calls"] == 1
    audit = next(row for row in result["by_interaction"] if row["initiator"] == "audit")
    assert audit["interaction_id"] == "audit-1"


def test_hosted_cosmos_failure_does_not_write_local_usage(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "canary")
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "upsert_doc",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unavailable")),
    )

    provider_usage.record_call(
        provider="google",
        operation="text_search",
        sku_class="essentials",
        status="ok",
        duration_ms=10,
    )

    assert not (tmp_path / "provider_usage").exists()


def test_hosted_cosmos_read_failure_does_not_read_local_usage(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "canary")
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "_container",
        lambda *_args: (_ for _ in ()).throw(OSError("unavailable")),
    )
    monkeypatch.setattr(
        provider_usage,
        "_read_local",
        lambda *_args: (_ for _ in ()).throw(AssertionError("local fallback used")),
    )

    assert provider_usage._read(datetime.now(UTC)) == []


def test_non_billable_short_circuit_is_not_an_unknown_cost(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    monkeypatch.setattr(
        provider_usage,
        "_now",
        lambda: datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )

    provider_usage.record_call(
        provider="google",
        operation="text_search",
        sku_class="essentials",
        status="circuit_open",
        duration_ms=0,
        attempted=False,
        billable=False,
    )

    total = provider_usage.summary(days=1)["totals"]
    assert total["calls"] == 0
    assert total["avoided_calls"] == 1
    assert total["cache_hits"] == 0
    assert total["failures"] == 0
    assert total["estimated_cost_usd"] == 0.0
    assert total["estimated_savings_usd"] == 0
    assert total["unknown_cost_calls"] == 0


def test_cache_hits_report_savings_without_inflating_cost(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)

    with usage_scope("user_trip", interaction_id="turn-cache"):
        provider_usage.record_cache_hit(
            provider="google",
            operation="text_search",
            sku_class="essentials",
        )
        provider_usage.record_call(
            provider="google",
            operation="text_search",
            sku_class="essentials",
            status="ok",
            duration_ms=20,
        )

    result = provider_usage.summary(days=1)
    assert result["totals"]["estimated_cost_usd"] == 0.032
    assert result["totals"]["estimated_savings_usd"] == 0.032
    assert result["totals"]["cache_hits"] == 1
    assert result["cache_effectiveness"] == {
        "provider_calls": 1,
        "cache_hits": 1,
        "requests": 2,
        "provider_call_rate": 0.5,
        "cache_hit_rate": 0.5,
        "estimated_savings_usd": 0.032,
        "by_dataset": [
            {
                "dataset": "places_search",
                "provider_calls": 1,
                "cache_hits": 1,
                "requests": 2,
                "hit_rate": 0.5,
                "estimated_savings_usd": 0.032,
            }
        ],
    }


def test_multi_unit_cache_hit_scales_counts_and_savings(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)

    provider_usage.record_cache_hit(
        provider="google",
        operation="photo_media",
        sku_class="photo_media",
        units=3,
    )

    totals = provider_usage.summary(days=1)["totals"]
    assert totals["avoided_calls"] == 3
    assert totals["cache_hits"] == 3
    assert totals["estimated_savings_usd"] == 0.021


def test_usage_scope_persists_one_document_with_provider_breakup(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    writes: list[dict] = []
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "upsert_doc",
        lambda _container, _partition, _id, body: writes.append(body),
    )

    with usage_scope(
        "user_trip",
        interaction_id="turn-1",
        trip_id="trip-1",
        interaction_kind="trip_update",
    ):
        for provider in ("google", "tavily", "azure_openai"):
            provider_usage.record_call(
                provider=provider,
                operation="request",
                status="ok",
                duration_ms=10,
                estimated_cost_usd=0.01,
            )

    assert len(writes) == 1
    assert writes[0]["record_count"] == 3
    assert writes[0]["telemetry_event_count"] == 3
    assert {event["kind"] for event in writes[0]["telemetry_events"]} == {"provider_call"}
    assert {entry["provider"] for entry in writes[0]["entries"]} == {
        "google",
        "tavily",
        "azure_openai",
    }
    assert {entry["interaction_kind"] for entry in writes[0]["entries"]} == {"trip_update"}


def test_new_trip_batch_can_be_attributed_after_the_trip_is_created(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    writes: list[dict] = []
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "upsert_doc",
        lambda _container, _partition, _id, body: writes.append(body),
    )

    with usage_scope(
        "user_trip",
        interaction_id="turn-new",
        interaction_kind="new_trip",
    ):
        provider_usage.record_call(
            provider="azure_openai",
            operation="chat_completion",
            status="ok",
            duration_ms=10,
            estimated_cost_usd=0.01,
        )
        annotate_current_batch(interaction_id="turn-new", trip_id="trip-created")

    assert writes[0]["entries"][0]["trip_id"] == "trip-created"


def test_event_only_interaction_still_persists_telemetry(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    writes: list[dict] = []
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "upsert_doc",
        lambda _container, _partition, _id, body: writes.append(body),
    )

    with usage_scope("user_trip", interaction_id="turn-no-provider"):
        from tripplanner.observability import app_event

        app_event("tool_call", tool="get_trip_plan", status="ok", cache_hit=True)

    assert len(writes) == 1
    assert writes[0]["record_count"] == 0
    assert writes[0]["telemetry_event_count"] == 1
    assert writes[0]["day"]


def test_persist_batch_chunks_records_and_events_at_their_limits(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    writes: list[dict] = []
    monkeypatch.setattr(provider_usage, "_write", writes.append)
    base = {
        "occurred_at": "2026-08-31T12:00:00+00:00",
        "day": "2026-08-31",
        "environment": "test",
        "interaction_id": "turn-large",
    }
    records = [{**base, "provider": "google"} for _ in range(101)]
    events = [{**base, "kind": "tool_call"} for _ in range(501)]

    provider_usage.persist_batch(records, events)

    assert [row["record_count"] for row in writes] == [100, 1]
    assert [row["telemetry_event_count"] for row in writes] == [500, 1]


def test_summary_calculates_trip_cost_averages_and_names(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    rows = [
        {
            "environment": "canary",
            "initiator": "user_trip",
            "interaction_kind": kind,
            "interaction_id": interaction_id,
            "trip_id": "trip-1",
            "provider": "azure_openai",
            "operation": "chat_completion",
            "sku_class": "gpt-4o-mini",
            "status": "ok",
            "attempted": True,
            "billable": True,
            "estimated_cost_usd": cost,
        }
        for kind, interaction_id, cost in (
            ("new_trip", "create-1", 0.12),
            ("trip_update", "update-1", 0.03),
            ("trip_update", "update-2", 0.05),
        )
    ]
    monkeypatch.setattr(provider_usage, "_read", lambda _since: rows)

    result = provider_usage.summary(days=30, trip_names={"trip-1": "Kyoto"})

    assert result["trip_costs"]["new_trip"] == {
        "interactions": 1,
        "trips": 1,
        "calls": 1,
        "estimated_cost_usd": 0.12,
        "average_estimated_cost_usd": 0.12,
        "unknown_cost_interactions": 0,
    }
    assert result["trip_costs"]["trip_update"]["interactions"] == 2
    assert result["trip_costs"]["trip_update"]["average_estimated_cost_usd"] == 0.04
    assert result["by_trip"][0]["trip_name"] == "Kyoto"
    assert result["by_interaction"][0]["interaction_kind"] in {"new_trip", "trip_update"}


def test_summary_uses_inclusive_custom_date_range(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: list[tuple[datetime, datetime | None]] = []

    def read(since: datetime, until: datetime | None = None) -> list[dict]:
        captured.append((since, until))
        return []

    monkeypatch.setattr(provider_usage, "_read", read)
    monkeypatch.setattr(
        provider_usage,
        "_now",
        lambda: datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
    )

    result = provider_usage.summary(
        start_date=datetime(2026, 8, 10, tzinfo=UTC).date(),
        end_date=datetime(2026, 8, 12, tzinfo=UTC).date(),
    )

    assert result["start_date"] == "2026-08-10"
    assert result["end_date"] == "2026-08-12"
    assert result["period_days"] == 3
    assert captured[0][0] == datetime(2026, 8, 10, tzinfo=UTC)
    assert captured[0][1] == datetime(2026, 8, 13, tzinfo=UTC)
