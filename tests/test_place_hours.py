"""Tests for tools/place_hours.py (Google Places New opening-hours check)."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from multiagent.tools import place_hours


@pytest.fixture
def _configured(monkeypatch):
    monkeypatch.setattr(place_hours, "is_configured", lambda: True)
    monkeypatch.setattr(
        place_hours,
        "get_settings",
        lambda: SimpleNamespace(google_places_api_key="test-key"),
    )


def _mk_response(payload):
    return SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)


# ---- pure helpers ---------------------------------------------------------


def test_parse_when_accepts_three_formats():
    assert place_hours._parse_when("2026-07-14") == datetime(2026, 7, 14, 0, 0)
    assert place_hours._parse_when("2026-07-14T15:30") == datetime(2026, 7, 14, 15, 30)
    assert place_hours._parse_when("2026-07-14 15:30") == datetime(2026, 7, 14, 15, 30)
    assert place_hours._parse_when("") is None
    assert place_hours._parse_when("nonsense") is None


def test_is_open_at_simple_weekday():
    # Monday 09:00-18:00 in Google's Sunday=0 weekday format
    periods = [
        {
            "open": {"day": 1, "hour": 9, "minute": 0},
            "close": {"day": 1, "hour": 18, "minute": 0},
        }
    ]
    # 2026-07-13 is a Monday
    assert place_hours._is_open_at(periods, datetime(2026, 7, 13, 12, 0)) is True
    assert place_hours._is_open_at(periods, datetime(2026, 7, 13, 8, 59)) is False
    assert place_hours._is_open_at(periods, datetime(2026, 7, 13, 18, 0)) is False
    # Tuesday — closed
    assert place_hours._is_open_at(periods, datetime(2026, 7, 14, 12, 0)) is False


def test_is_open_at_handles_midnight_crossing():
    # Open Fri 22:00 → Sat 02:00 (bar)
    periods = [
        {
            "open": {"day": 5, "hour": 22, "minute": 0},
            "close": {"day": 6, "hour": 2, "minute": 0},
        }
    ]
    # 2026-07-17 = Friday
    assert place_hours._is_open_at(periods, datetime(2026, 7, 17, 23, 30)) is True
    # 2026-07-18 = Saturday
    assert place_hours._is_open_at(periods, datetime(2026, 7, 18, 1, 30)) is True
    assert place_hours._is_open_at(periods, datetime(2026, 7, 18, 2, 30)) is False


def test_is_open_at_treats_missing_close_as_always_open():
    periods = [{"open": {"day": 0, "hour": 0, "minute": 0}}]
    assert place_hours._is_open_at(periods, datetime(2026, 7, 14, 3, 33)) is True


def test_is_open_at_empty_periods_returns_false():
    assert place_hours._is_open_at([], datetime(2026, 7, 14, 12, 0)) is False


# ---- @tool: check_place_hours --------------------------------------------


def test_check_place_hours_not_configured(monkeypatch):
    monkeypatch.setattr(place_hours, "is_configured", lambda: False)
    out = place_hours.check_place_hours.invoke({"place_id": "X", "when_iso": ""})
    assert "not configured" in out.lower()


def test_check_place_hours_returns_schedule_without_when(_configured, monkeypatch):
    payload = {
        "id": "P1",
        "displayName": {"text": "Louvre"},
        "businessStatus": "OPERATIONAL",
        "regularOpeningHours": {
            "weekdayDescriptions": [
                "Monday: 9:00 AM – 6:00 PM",
                "Tuesday: Closed",
            ],
            "periods": [
                {
                    "open": {"day": 1, "hour": 9, "minute": 0},
                    "close": {"day": 1, "hour": 18, "minute": 0},
                }
            ],
        },
    }
    monkeypatch.setattr(place_hours.httpx, "get", lambda *a, **k: _mk_response(payload))
    out = json.loads(place_hours.check_place_hours.invoke({"place_id": "P1"}))
    assert out["name"] == "Louvre"
    assert out["business_status"] == "OPERATIONAL"
    assert "Monday: 9:00 AM – 6:00 PM" in out["weekday_schedule"]
    assert "open_at_requested_time" not in out


def test_check_place_hours_open_verdict(_configured, monkeypatch):
    payload = {
        "id": "P1",
        "displayName": {"text": "Louvre"},
        "businessStatus": "OPERATIONAL",
        "currentOpeningHours": {
            "weekdayDescriptions": ["Monday: 9:00 AM – 6:00 PM", "Tuesday: Closed"],
            "periods": [
                {
                    "open": {"day": 1, "hour": 9, "minute": 0},
                    "close": {"day": 1, "hour": 18, "minute": 0},
                }
            ],
        },
    }
    monkeypatch.setattr(place_hours.httpx, "get", lambda *a, **k: _mk_response(payload))

    # Monday noon → open
    open_out = json.loads(
        place_hours.check_place_hours.invoke(
            {"place_id": "P1", "when_iso": "2026-07-13T12:00"}
        )
    )
    assert open_out["open_at_requested_time"] is True
    assert open_out["requested_weekday"] == "Monday"

    # Tuesday noon → closed
    closed_out = json.loads(
        place_hours.check_place_hours.invoke(
            {"place_id": "P1", "when_iso": "2026-07-14T12:00"}
        )
    )
    assert closed_out["open_at_requested_time"] is False
    assert closed_out["requested_weekday"] == "Tuesday"


def test_check_place_hours_permanent_closure_warning(_configured, monkeypatch):
    payload = {
        "id": "P1",
        "displayName": {"text": "Old Cafe"},
        "businessStatus": "CLOSED_PERMANENTLY",
        "regularOpeningHours": {"weekdayDescriptions": [], "periods": []},
    }
    monkeypatch.setattr(place_hours.httpx, "get", lambda *a, **k: _mk_response(payload))
    out = json.loads(
        place_hours.check_place_hours.invoke(
            {"place_id": "P1", "when_iso": "2026-07-14T12:00"}
        )
    )
    assert out["business_status"] == "CLOSED_PERMANENTLY"
    assert "warning" in out
    assert out["open_at_requested_time"] is False


def test_check_place_hours_invalid_when_iso(_configured, monkeypatch):
    payload = {
        "id": "P1",
        "displayName": {"text": "X"},
        "businessStatus": "OPERATIONAL",
        "regularOpeningHours": {"weekdayDescriptions": [], "periods": []},
    }
    monkeypatch.setattr(place_hours.httpx, "get", lambda *a, **k: _mk_response(payload))
    out = json.loads(
        place_hours.check_place_hours.invoke({"place_id": "P1", "when_iso": "garbage"})
    )
    assert "error" in out


def test_check_place_hours_sends_correct_field_mask(_configured, monkeypatch):
    captured = {}

    def fake_get(url, *, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return _mk_response(
            {
                "id": "P1",
                "displayName": {"text": "X"},
                "businessStatus": "OPERATIONAL",
                "regularOpeningHours": {"weekdayDescriptions": [], "periods": []},
            }
        )

    monkeypatch.setattr(place_hours.httpx, "get", fake_get)
    place_hours.check_place_hours.invoke({"place_id": "P1"})
    assert captured["url"].endswith("/places/P1")
    assert "regularOpeningHours.periods" in captured["headers"]["X-Goog-FieldMask"]
    assert "utcOffsetMinutes" in captured["headers"]["X-Goog-FieldMask"]
    assert captured["headers"]["X-Goog-Api-Key"] == "test-key"
