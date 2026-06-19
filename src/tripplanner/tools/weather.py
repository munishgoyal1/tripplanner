"""Weather forecast & seasonal estimate using Open-Meteo (no API key required).

Used by the trip agent in STEP 4 to ground packing recommendations:
"Goa in July → daily highs 28-31°C with heavy rain on 4/7 days → pack a
quick-dry rain jacket + sandals, skip the wool sweater".

Two backends, picked by date range:
- forecast API   (next ~16 days, exact)        https://api.open-meteo.com
- archive  API   (same dates last year, proxy) https://archive-api.open-meteo.com

Both are free, public, no auth.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import httpx
from langchain_core.tools import tool

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

# Subset of WMO weather codes for human-readable summaries.
_WMO = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Violent showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


def _wmo_text(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return _WMO.get(int(code), f"Code {code}")


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _geocode(location: str) -> dict | None:
    try:
        r = httpx.get(
            _GEOCODE,
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    data = r.json()
    results = data.get("results") or []
    if not results:
        return None
    g = results[0]
    return {
        "name": g.get("name", location),
        "country": g.get("country", ""),
        "latitude": g.get("latitude"),
        "longitude": g.get("longitude"),
        "timezone": g.get("timezone", "auto"),
    }


def _shift_year(d: date, years: int) -> date:
    # Feb 29 → Feb 28 fallback
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _build_daily(payload: dict) -> list[dict]:
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or [None] * len(times)
    tmin = daily.get("temperature_2m_min") or [None] * len(times)
    psum = daily.get("precipitation_sum") or [None] * len(times)
    pprob = daily.get("precipitation_probability_max") or [None] * len(times)
    codes = daily.get("weather_code") or [None] * len(times)
    out: list[dict] = []
    for i, day_str in enumerate(times):
        out.append(
            {
                "date": day_str,
                "summary": _wmo_text(codes[i] if i < len(codes) else None),
                "high_c": tmax[i] if i < len(tmax) else None,
                "low_c": tmin[i] if i < len(tmin) else None,
                "precip_mm": psum[i] if i < len(psum) else None,
                "precip_probability_pct": pprob[i] if i < len(pprob) else None,
            }
        )
    return out


def _fetch_forecast(lat: float, lon: float, start: date, end: date, tz: str) -> dict | None:
    try:
        r = httpx.get(
            _FORECAST,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": ",".join(
                    [
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_sum",
                        "precipitation_probability_max",
                        "weather_code",
                    ]
                ),
                "timezone": tz or "auto",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            timeout=20,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    return r.json()


def _fetch_archive(lat: float, lon: float, start: date, end: date, tz: str) -> dict | None:
    try:
        r = httpx.get(
            _ARCHIVE,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": ",".join(
                    [
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_sum",
                        "weather_code",
                    ]
                ),
                "timezone": tz or "auto",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            timeout=30,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    return r.json()


@tool
def get_weather_forecast(location: str, start_date: str, end_date: str) -> str:
    """Get daily weather for a destination over a trip date range.

    Uses Open-Meteo (free, no API key). If the trip is within ~16 days from
    today the agent gets the actual forecast; for trips farther out it returns
    last year's same-date archive as a seasonal estimate (clearly labelled).

    The agent should use this in STEP 4 to:
      - Tailor activities (e.g. swap an outdoor walking tour for a museum on a
        rainy day).
      - Build a packing list grounded in real numbers, not vibes.

    Args:
        location: City or place name (e.g. "Paris", "Goa", "Tokyo").
        start_date: Trip start date, ISO format "YYYY-MM-DD".
        end_date:   Trip end date,   ISO format "YYYY-MM-DD".

    Returns JSON with destination metadata, source ("forecast" or "seasonal_estimate"),
    and a per-day list with high/low °C, precipitation mm, probability %, and
    a short human-readable summary.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if not start or not end:
        return "Invalid dates. Use YYYY-MM-DD for both start_date and end_date."
    if end < start:
        return "end_date must be on or after start_date."

    geo = _geocode(location)
    if not geo or geo["latitude"] is None or geo["longitude"] is None:
        return f"Could not geocode '{location}'. Try a more specific city name."

    today = date.today()
    forecast_horizon = today + timedelta(days=16)
    use_forecast = start <= forecast_horizon

    if use_forecast:
        payload = _fetch_forecast(geo["latitude"], geo["longitude"], start, end, geo["timezone"])
        source = "forecast"
        # If the trip extends past forecast horizon, the API silently clips —
        # daily.time will only cover the available window.
    else:
        proxy_start = _shift_year(start, -1)
        proxy_end = _shift_year(end, -1)
        payload = _fetch_archive(
            geo["latitude"], geo["longitude"], proxy_start, proxy_end, geo["timezone"]
        )
        source = "seasonal_estimate"

    if not payload:
        return f"Failed to fetch weather from Open-Meteo for {geo['name']}."

    days = _build_daily(payload)
    if source == "seasonal_estimate":
        # Re-label proxy dates back to the trip's actual dates for readability.
        for i, d in enumerate(days):
            d["proxy_date"] = d["date"]
            d["date"] = (start + timedelta(days=i)).isoformat()

    out = {
        "destination": geo["name"],
        "country": geo["country"],
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "source": source,
        "note": (
            "Real forecast from Open-Meteo."
            if source == "forecast"
            else "Trip is beyond the 16-day forecast horizon — these values are "
            "last year's same-week archive as a seasonal proxy."
        ),
        "days": days,
    }
    return json.dumps(out, indent=2)
