"""Tests for tools/routing.py (Google Routes API v2 wrapper)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tripplanner.places_budget import places_budget_scope
from tripplanner.tools import routing

# ---------------------------------------------------------------------------
# Pure-helper tests (no network)
# ---------------------------------------------------------------------------


def test_seconds_to_human_str_input():
    assert routing._seconds_to_human("75s") == "1m"
    assert routing._seconds_to_human("3900s") == "1h 5m"
    assert routing._seconds_to_human("3600s") == "1h"
    assert routing._seconds_to_human("45s") == "45s"


def test_seconds_to_human_numeric_and_none():
    assert routing._seconds_to_human(None) == ""
    assert routing._seconds_to_human(60) == "1m"


def test_meters_to_human():
    assert routing._meters_to_human(500) == "500 m"
    assert routing._meters_to_human(1800) == "1.8 km"
    assert routing._meters_to_human(None) == ""


def test_waypoint_accepts_string_dict_and_placeid():
    assert routing._waypoint("Eiffel Tower") == {"address": "Eiffel Tower"}
    assert routing._waypoint({"place_id": "ChIJ_abc"}) == {"placeId": "ChIJ_abc"}
    assert routing._waypoint({"lat": 48.86, "lng": 2.34}) == {
        "location": {"latLng": {"latitude": 48.86, "longitude": 2.34}}
    }
    assert routing._waypoint({"name": "Louvre"}) == {"address": "Louvre"}


def test_parse_stops_rejects_short_or_invalid():
    with pytest.raises(ValueError):
        routing._parse_stops("not json")
    with pytest.raises(ValueError):
        routing._parse_stops("[]")
    with pytest.raises(ValueError):
        routing._parse_stops("[\"only one\"]")


# ---------------------------------------------------------------------------
# compute_route / optimize_day_route — mock httpx.post
# ---------------------------------------------------------------------------


def _mk_response(payload: dict):
    return SimpleNamespace(
        json=lambda: payload,
        raise_for_status=lambda: None,
    )


@pytest.fixture
def _authorized():
    with places_budget_scope("user_interaction"):
        yield


@pytest.fixture
def _configured(monkeypatch, _authorized):
    """Force is_configured() True without needing a real env var."""
    monkeypatch.setattr(routing, "is_configured", lambda: True)
    monkeypatch.setattr(
        routing,
        "get_settings",
        lambda: SimpleNamespace(
            enable_google_maps=True,
            google_places_api_key="test-key",
            openrouteservice_route_ttl_sec=21600,
        ),
    )


def test_google_routes_key_does_not_bypass_disabled_maps_gate(monkeypatch):
    monkeypatch.setattr(
        routing,
        "get_settings",
        lambda: SimpleNamespace(enable_google_maps=False, google_places_api_key="copied-key"),
    )

    assert routing._google_configured() is False


def test_google_routes_denies_unscoped_provider_call(monkeypatch):
    monkeypatch.setattr(
        routing,
        "get_settings",
        lambda: SimpleNamespace(
            enable_google_maps=True,
            google_places_api_key="test-key",
            openrouteservice_api_key="",
        ),
    )
    monkeypatch.setattr(
        routing.http_client,
        "post",
        lambda *args, **kwargs: pytest.fail("unscoped provider call"),
    )

    out = routing.compute_route.invoke({"stops_json": '["A", "B"]'})

    assert out == "No route found for the supplied stops."


def test_compute_route_returns_legs_and_totals(_configured, monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        captured["mode"] = json["travelMode"]
        return _mk_response({
            "routes": [{
                "duration": "1800s",
                "distanceMeters": 5400,
                "legs": [
                    {"duration": "900s", "distanceMeters": 2700},
                    {"duration": "900s", "distanceMeters": 2700},
                ],
            }]
        })

    monkeypatch.setattr(routing.http_client, "post", fake_post)

    stops_json = json.dumps(["Hotel Lutetia", "Louvre", "Notre Dame"])
    out = routing.compute_route.invoke({"stops_json": stops_json, "mode": "WALK"})
    parsed = json.loads(out)

    assert parsed["mode"] == "WALK"
    assert parsed["total_duration"] == "30m"
    assert parsed["total_distance"] == "5.4 km"
    assert len(parsed["legs"]) == 2
    assert parsed["legs"][0]["from"] == "Hotel Lutetia"
    assert parsed["legs"][0]["to"] == "Louvre"
    assert parsed["legs"][0]["duration"] == "15m"
    assert captured["mode"] == "WALK"
    # WALK should NOT set TRAFFIC_AWARE
    assert "routingPreference" not in captured["payload"]


def test_compute_route_drive_sets_traffic_aware(_configured, monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        return _mk_response({"routes": [{"duration": "60s", "distanceMeters": 100, "legs": []}]})

    monkeypatch.setattr(routing.http_client, "post", fake_post)
    routing.compute_route.invoke({
        "stops_json": json.dumps(["A", "B"]),
        "mode": "drive",  # lowercase is normalized
    })
    assert captured["payload"]["travelMode"] == "DRIVE"
    assert captured["payload"]["routingPreference"] == "TRAFFIC_AWARE"


def test_compute_route_not_configured(monkeypatch):
    monkeypatch.setattr(routing, "is_configured", lambda: False)
    out = routing.compute_route.invoke({"stops_json": "[\"A\", \"B\"]"})
    assert "not configured" in out.lower()


def test_coordinate_route_falls_back_to_openrouteservice(_authorized, monkeypatch):
    captured = {}
    routing._ORS_ROUTE_CACHE.clear()
    monkeypatch.setattr(
        routing,
        "get_settings",
        lambda: SimpleNamespace(
            enable_google_maps=False,
            google_places_api_key="",
            openrouteservice_api_key="ors-test-key",
            openrouteservice_base_url="https://api.openrouteservice.org",
            openrouteservice_route_ttl_sec=60,
        ),
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return _mk_response(
            {
                "routes": [
                    {
                        "summary": {"duration": 900, "distance": 2200},
                        "segments": [{"duration": 900, "distance": 2200}],
                    }
                ]
            }
        )

    monkeypatch.setattr(routing.http_client, "post", fake_post)
    stops_json = json.dumps(
        [{"name": "A", "lat": 48.8566, "lng": 2.3522}, {"name": "B", "lat": 48.86, "lng": 2.34}]
    )

    out = json.loads(routing.compute_route.invoke({"stops_json": stops_json, "mode": "WALK"}))

    assert out["provider"] == "openrouteservice"
    assert out["total_duration"] == "15m"
    assert out["total_distance"] == "2.2 km"
    assert captured["headers"]["Authorization"] == "ors-test-key"
    assert captured["json"]["coordinates"] == [[2.3522, 48.8566], [2.34, 48.86]]


def test_openrouteservice_coordinate_routes_are_cached(_authorized, monkeypatch):
    calls = []
    routing._ORS_ROUTE_CACHE.clear()
    monkeypatch.setattr(
        routing,
        "get_settings",
        lambda: SimpleNamespace(
            enable_google_maps=False,
            google_places_api_key="",
            openrouteservice_api_key="ors-test-key",
            openrouteservice_base_url="https://api.openrouteservice.org",
            openrouteservice_route_ttl_sec=60,
        ),
    )

    def fake_post(*args, **kwargs):
        calls.append(args[0])
        return _mk_response({"routes": [{"summary": {"duration": 60, "distance": 100}}]})

    monkeypatch.setattr(routing.http_client, "post", fake_post)
    origin = {"lat": 48.8566, "lng": 2.3522}
    destination = {"lat": 48.86, "lng": 2.34}

    assert routing.route_metrics(origin, destination, "DRIVE") is not None
    assert routing.route_metrics(origin, destination, "DRIVE") is not None
    assert len(calls) == 1


def test_google_route_metrics_are_cached(_configured, monkeypatch):
    calls = []
    routing._GOOGLE_ROUTE_CACHE.clear()

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return _mk_response({"routes": [{"duration": "600s", "distanceMeters": 1200}]})

    monkeypatch.setattr(routing.http_client, "post", fake_post)

    assert routing.route_metrics("A", "B", "DRIVE") is not None
    assert routing.route_metrics("A", "B", "DRIVE") is not None
    assert len(calls) == 1


def test_compute_route_invalid_json(_configured):
    out = routing.compute_route.invoke({"stops_json": "not json"})
    assert "valid JSON" in out


def test_optimize_day_route_uses_returned_order(_configured, monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        # API permutes the 3 intermediates: was [B, C, D] -> now [C, B, D]
        return _mk_response({
            "routes": [{
                "duration": "2400s",
                "distanceMeters": 8000,
                "optimizedIntermediateWaypointIndex": [1, 0, 2],
                "legs": [
                    {"duration": "600s", "distanceMeters": 2000},
                    {"duration": "600s", "distanceMeters": 2000},
                    {"duration": "600s", "distanceMeters": 2000},
                    {"duration": "600s", "distanceMeters": 2000},
                ],
            }]
        })

    monkeypatch.setattr(routing.http_client, "post", fake_post)

    stops_json = json.dumps(["Hotel", "B", "C", "D", "Hotel"])
    out = routing.optimize_day_route.invoke({"stops_json": stops_json, "mode": "WALK"})
    parsed = json.loads(out)

    assert parsed["optimized_order"] == ["Hotel", "C", "B", "D", "Hotel"]
    assert parsed["total_duration"] == "40m"
    assert parsed["total_distance"] == "8.0 km"
    assert len(parsed["legs"]) == 4
    # leg labels should reflect the new order
    assert parsed["legs"][0]["from"] == "Hotel"
    assert parsed["legs"][0]["to"] == "C"


def test_optimize_day_route_requires_three_stops(_configured):
    out = routing.optimize_day_route.invoke({"stops_json": json.dumps(["A", "B"])})
    assert "at least 3 stops" in out


def test_optimize_day_route_sends_optimize_flag(_configured, monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        return _mk_response({
            "routes": [{
                "duration": "0s",
                "distanceMeters": 0,
                "optimizedIntermediateWaypointIndex": [0],
                "legs": [],
            }]
        })

    monkeypatch.setattr(routing.http_client, "post", fake_post)
    routing.optimize_day_route.invoke({"stops_json": json.dumps(["A", "B", "C"])})
    assert captured["payload"]["optimizeWaypointOrder"] is True
    assert captured["payload"]["intermediates"] == [{"address": "B"}]
