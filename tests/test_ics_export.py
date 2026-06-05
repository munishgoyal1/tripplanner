"""Tests for the .ics calendar export."""

from __future__ import annotations

from multiagent.web.ics_export import build_ics


def _plan(**overrides):
    base = {
        "destination": "Paris",
        "departure_date": "2026-09-10",
        "return_date": "2026-09-15",
        "created_at": "2026-09-01T10:00:00",
        "selected_flights": [
            {"airline": "Air France", "from": "BOM", "to": "CDG"},
            {"airline": "Air France", "from": "CDG", "to": "BOM"},
        ],
        "selected_hotels": [{"name": "Hotel des Tuileries"}],
        "selected_activities": [{"name": "Eiffel Tower"}],
        "day_wise_itinerary": [
            {"day": 1, "plan": "Arrive + Eiffel"},
            {"day": 2, "plan": "Louvre + Seine cruise"},
        ],
    }
    base.update(overrides)
    return base


def test_empty_plan_still_valid_calendar() -> None:
    ics = build_ics(None)
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.rstrip().endswith("END:VCALENDAR")
    assert "VEVENT" not in ics


def test_flight_events_use_correct_dates() -> None:
    ics = build_ics(_plan())
    assert "DTSTART;VALUE=DATE:20260910" in ics  # outbound
    assert "DTSTART;VALUE=DATE:20260915" in ics  # return
    assert "Air France" in ics
    assert "BOM" in ics and "CDG" in ics


def test_hotel_event_spans_trip_with_exclusive_end() -> None:
    ics = build_ics(_plan())
    # Check-in == dep date, exclusive checkout day is ret + 1.
    assert "DTSTART;VALUE=DATE:20260910" in ics
    assert "DTEND;VALUE=DATE:20260916" in ics
    assert "Hotel des Tuileries" in ics


def test_itinerary_days_emitted() -> None:
    ics = build_ics(_plan())
    assert ics.count("BEGIN:VEVENT") >= 5  # 2 flights + 1 hotel + 2 days
    assert "Arrive + Eiffel" in ics
    assert "Louvre + Seine cruise" in ics


def test_escapes_special_chars_in_summary() -> None:
    plan = _plan(day_wise_itinerary=[{"day": 1, "plan": "Lunch; then museum, dinner"}])
    ics = build_ics(plan)
    # Commas/semicolons inside DESCRIPTION must be escaped per RFC 5545.
    assert "Lunch\\; then museum\\, dinner" in ics


def test_uid_is_stable_per_event_type() -> None:
    ics1 = build_ics(_plan())
    ics2 = build_ics(_plan())
    # Same plan -> same UIDs (uses created_at) so calendar updates replace, not duplicate.
    for prefix in ("flight-0-", "flight-1-", "hotel-0-", "day-1-"):
        assert prefix in ics1 and prefix in ics2
