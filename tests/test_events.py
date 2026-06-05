"""Tests for tools/events.py (Tavily-backed local events lookup)."""

from __future__ import annotations

import json

import httpx

from multiagent.tools import events


def test_build_query_includes_all_inputs():
    q = events._build_query("Paris", "2026-07-12", "2026-07-18", "festivals")
    assert "Paris" in q
    assert "2026-07-12" in q and "2026-07-18" in q
    assert "festivals" in q


def test_events_not_configured(monkeypatch):
    monkeypatch.setattr(events, "is_configured", lambda: False)
    out = events.find_local_events.invoke(
        {"destination": "Paris", "start_date": "2026-07-12", "end_date": "2026-07-18"}
    )
    assert "not configured" in out.lower()


def test_events_missing_inputs(monkeypatch):
    monkeypatch.setattr(events, "is_configured", lambda: True)
    out = events.find_local_events.invoke(
        {"destination": "", "start_date": "2026-07-12", "end_date": "2026-07-18"}
    )
    assert "required" in out.lower()


def test_events_returns_structured_envelope(monkeypatch):
    monkeypatch.setattr(events, "is_configured", lambda: True)
    fake_results = [
        {"title": "Bastille Day Parade", "url": "https://parisinfo.com/bastille", "content": "July 14, parade on Champs-Élysées..."},
        {"title": "Open-Air Cinema Festival", "url": "https://example.com/cinema", "content": "Mid-July screenings..."},
    ]

    captured = {}

    def fake_search_raw(query, max_results, search_depth, topic=None):
        captured["query"] = query
        captured["max_results"] = max_results
        captured["depth"] = search_depth
        captured["topic"] = topic
        return {"answer": "Bastille Day falls on July 14 with a major parade.", "results": fake_results}

    monkeypatch.setattr(events, "search_raw", fake_search_raw)
    out = json.loads(
        events.find_local_events.invoke(
            {"destination": "Paris", "start_date": "2026-07-12", "end_date": "2026-07-18"}
        )
    )
    assert out["destination"] == "Paris"
    assert out["summary"].startswith("Bastille Day")
    assert len(out["results"]) == 2
    assert captured["max_results"] == 8
    assert captured["depth"] == "advanced"
    assert captured["topic"] == "news"
    assert "note" in out


def test_events_propagates_search_error(monkeypatch):
    monkeypatch.setattr(events, "is_configured", lambda: True)

    def boom(*a, **k):
        raise httpx.HTTPError("network down")

    monkeypatch.setattr(events, "search_raw", boom)
    out = events.find_local_events.invoke(
        {"destination": "Paris", "start_date": "2026-07-12", "end_date": "2026-07-18"}
    )
    assert "Event search failed" in out
