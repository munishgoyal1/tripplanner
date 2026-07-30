"""Tests for tools/weather.py (Open-Meteo wrapper)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from tripplanner.tools import weather


def _mk_response(payload):
    return SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)


GEOCODE_PARIS = {
    "results": [
        {
            "name": "Paris",
            "country": "France",
            "latitude": 48.85,
            "longitude": 2.35,
            "timezone": "Europe/Paris",
        }
    ]
}


def _forecast_payload(start_iso: str, days: int = 3):
    dates = [(date.fromisoformat(start_iso) + timedelta(days=i)).isoformat() for i in range(days)]
    return {
        "daily": {
            "time": dates,
            "temperature_2m_max": [25.1, 27.4, 22.9][:days],
            "temperature_2m_min": [17.0, 18.5, 16.2][:days],
            "precipitation_sum": [0.0, 1.2, 8.5][:days],
            "precipitation_probability_max": [10, 30, 80][:days],
            "weather_code": [1, 2, 65][:days],
        }
    }


# ---- pure helpers ---------------------------------------------------------


def test_wmo_text_known_and_unknown():
    assert weather._wmo_text(0) == "Clear"
    assert weather._wmo_text(65) == "Heavy rain"
    assert weather._wmo_text(None) == "Unknown"
    assert weather._wmo_text(7777) == "Code 7777"


def test_parse_date_handles_bad_input():
    assert weather._parse_date("2026-07-14") == date(2026, 7, 14)
    assert weather._parse_date("garbage") is None
    assert weather._parse_date("") is None


def test_shift_year_handles_feb_29():
    assert weather._shift_year(date(2024, 2, 29), -1) == date(2023, 2, 28)
    assert weather._shift_year(date(2025, 3, 1), -1) == date(2024, 3, 1)


def test_build_daily_pads_missing_fields():
    payload = {"daily": {"time": ["2026-07-14"], "temperature_2m_max": [25.0]}}
    days = weather._build_daily(payload)
    assert len(days) == 1
    assert days[0]["high_c"] == 25.0
    assert days[0]["low_c"] is None
    assert days[0]["precip_mm"] is None


# ---- @tool: get_weather_forecast -----------------------------------------


def test_get_weather_forecast_invalid_dates(monkeypatch):
    out = weather.get_weather_forecast.invoke(
        {"location": "Paris", "start_date": "bad", "end_date": "2026-07-20"}
    )
    assert "Invalid dates" in out


def test_get_weather_forecast_end_before_start(monkeypatch):
    out = weather.get_weather_forecast.invoke(
        {"location": "Paris", "start_date": "2026-07-20", "end_date": "2026-07-10"}
    )
    assert "end_date" in out


def test_get_weather_forecast_geocode_miss(monkeypatch):
    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: _mk_response({"results": []}))
    out = weather.get_weather_forecast.invoke(
        {"location": "Nowheresville", "start_date": "2026-07-10", "end_date": "2026-07-12"}
    )
    assert "Could not geocode" in out


def test_get_weather_forecast_uses_forecast_within_horizon(monkeypatch):
    start = (date.today() + timedelta(days=5)).isoformat()
    end = (date.today() + timedelta(days=7)).isoformat()
    calls: list[str] = []

    def fake_get(url, *, params=None, timeout=None):
        calls.append(url)
        if url == weather._GEOCODE:
            return _mk_response(GEOCODE_PARIS)
        if url == weather._FORECAST:
            return _mk_response(_forecast_payload(start, days=3))
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(weather.httpx, "get", fake_get)
    out = json.loads(
        weather.get_weather_forecast.invoke(
            {"location": "Paris", "start_date": start, "end_date": end}
        )
    )
    assert out["destination"] == "Paris"
    assert out["source"] == "forecast"
    assert len(out["days"]) == 3
    assert out["days"][2]["summary"] == "Heavy rain"
    assert out["days"][2]["precip_probability_pct"] == 80
    assert weather._ARCHIVE not in calls


def test_get_weather_forecast_uses_archive_beyond_horizon(monkeypatch):
    far_start = (date.today() + timedelta(days=90)).isoformat()
    far_end = (date.today() + timedelta(days=92)).isoformat()

    def fake_get(url, *, params=None, timeout=None):
        if url == weather._GEOCODE:
            return _mk_response(GEOCODE_PARIS)
        if url == weather._ARCHIVE:
            # Archive returns proxy dates from last year
            proxy_start = (date.fromisoformat(far_start) - timedelta(days=365)).isoformat()
            return _mk_response(_forecast_payload(proxy_start, days=3))
        if url == weather._FORECAST:
            raise AssertionError("Should not call forecast for far-out trip")
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(weather.httpx, "get", fake_get)
    out = json.loads(
        weather.get_weather_forecast.invoke(
            {"location": "Paris", "start_date": far_start, "end_date": far_end}
        )
    )
    assert out["source"] == "seasonal_estimate"
    # Dates should be relabelled to trip dates, with proxy_date preserved
    assert out["days"][0]["date"] == far_start
    assert "proxy_date" in out["days"][0]
    assert "seasonal proxy" in out["note"]


def test_get_weather_forecast_falls_back_to_archive(monkeypatch):
    calls = []

    def fake_get(url, *, params=None, timeout=None):
        calls.append(url)
        if url == weather._GEOCODE:
            return _mk_response(GEOCODE_PARIS)
        if url == weather._FORECAST:
            raise weather.httpx.HTTPError("boom")
        if url == weather._ARCHIVE:
            return _mk_response(_forecast_payload("2025-07-14", days=3))
        raise AssertionError(url)

    start = (date.today() + timedelta(days=5)).isoformat()
    end = (date.today() + timedelta(days=7)).isoformat()
    monkeypatch.setattr(weather.httpx, "get", fake_get)
    out = json.loads(
        weather.get_weather_forecast.invoke(
            {"location": "Paris", "start_date": start, "end_date": end}
        )
    )
    assert out["source"] == "seasonal_estimate"
    assert out["days"][0]["date"] == start
    assert weather._FORECAST in calls
    assert weather._ARCHIVE in calls
