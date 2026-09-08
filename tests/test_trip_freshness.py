from __future__ import annotations

from typing import Any

import pytest

from tripplanner.web import trip_freshness


def _plan(*stops: dict[str, Any]) -> dict[str, Any]:
    return {
        "destination": "Paris",
        "day_wise_itinerary": [
            {"day": 1, "stops": list(stops)},
            {"day": 2, "stops": [{"name": "Hotel Lumiere", "kind": "hotel"}]},
        ],
    }


def _summary(name: str, status: str = "OPERATIONAL") -> dict[str, Any]:
    return {
        "place_id": f"id-{name}",
        "name": name,
        "business_status": status,
        "weekday_descriptions": ["Monday: 9:00 AM - 5:00 PM"],
    }


def test_refresh_deduplicates_places_and_records_successes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(
        {"name": "Hotel Lumiere", "kind": "hotel"},
        {"name": "Louvre Museum", "kind": "attraction"},
        {"name": "Flight to Paris", "kind": "flight"},
    )
    calls: list[str] = []

    def refresh(name: str, destination: str):
        calls.append(f"{name}|{destination}")
        return _summary(name), True

    monkeypatch.setattr(trip_freshness.places_cache, "refresh_details", refresh)
    monkeypatch.setattr(trip_freshness.web_search, "is_configured", lambda: False)

    result = trip_freshness.refresh(plan)

    assert sorted(calls) == ["Hotel Lumiere|Paris", "Louvre Museum|Paris"]
    assert result["checked"] == 2
    assert result["total"] == 2
    assert result["failed"] == []
    assert result["changes"] == []
    assert result["comparison_available"] is False
    assert set(plan["place_fact_snapshots"]) == {"hotel lumiere", "louvre museum"}


def test_refresh_reports_material_changes_and_preserves_failed_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(
        {"name": "Louvre Museum", "kind": "attraction"},
        {"name": "Cafe de Flore", "kind": "meal"},
    )
    plan["place_fact_snapshots"] = {
        "louvre museum": _summary("Louvre Museum"),
        "cafe de flore": _summary("Cafe de Flore"),
    }

    def refresh(name: str, _destination: str):
        if name == "Cafe de Flore":
            return _summary(name), False
        return _summary(name, "CLOSED_TEMPORARILY"), True

    monkeypatch.setattr(trip_freshness.places_cache, "refresh_details", refresh)
    monkeypatch.setattr(trip_freshness.web_search, "is_configured", lambda: False)

    result = trip_freshness.refresh(plan)

    assert result["checked"] == 2
    assert result["comparison_available"] is True
    assert result["failed"] == [{"name": "Cafe de Flore", "days": [1]}]
    assert result["changes"] == [
        {"name": "Louvre Museum", "days": [1], "changed": ["business status"]}
    ]
    assert plan["place_fact_snapshots"]["cafe de flore"]["business_status"] == "OPERATIONAL"


def test_refresh_checks_places_beyond_the_parallelism_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stops = tuple(
        {"name": f"Museum {index}", "kind": "attraction"}
        for index in range(trip_freshness._MAX_PARALLEL_CHECKS + 2)
    )
    monkeypatch.setattr(
        trip_freshness.places_cache,
        "refresh_details",
        lambda name, _destination: (_summary(name), True),
    )
    monkeypatch.setattr(trip_freshness.web_search, "is_configured", lambda: False)

    result = trip_freshness.refresh(_plan(*stops))

    assert result["checked"] == trip_freshness._MAX_PARALLEL_CHECKS + 3
    assert result["total"] == trip_freshness._MAX_PARALLEL_CHECKS + 3


def test_closure_watch_keeps_named_source_as_advisory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan({"name": "Louvre Museum", "kind": "attraction"})
    monkeypatch.setattr(
        trip_freshness.places_cache,
        "refresh_details",
        lambda name, _destination: (_summary(name), True),
    )
    monkeypatch.setattr(trip_freshness.web_search, "is_configured", lambda: True)
    monkeypatch.setattr(
        trip_freshness.web_search,
        "search_raw",
        lambda *_args, **_kwargs: {
            "results": [
                {
                    "title": "Louvre Museum renovation notice",
                    "url": "https://www.louvre.fr/notice",
                    "content": "A gallery is closed for renovation during the visit dates.",
                },
                {
                    "title": "Paris seasonal advice",
                    "url": "https://example.com/paris",
                    "content": "Some attractions have seasonal hours.",
                },
            ]
        },
    )

    result = trip_freshness.refresh(plan)

    assert result["closure_watch"] == {
        "status": "checked",
        "advisories": [
            {
                "name": "Louvre Museum",
                "days": [1],
                "title": "Louvre Museum renovation notice",
                "url": "https://www.louvre.fr/notice",
                "snippet": "A gallery is closed for renovation during the visit dates.",
            }
        ],
    }
