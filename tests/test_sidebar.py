"""Tests for the right-rail sidebar panels and focus-action builder.

Pure unit tests — no Chainlit runtime, no HTTP. The sidebar functions
construct ``cl.Text`` / ``cl.Image`` / ``cl.Action`` dataclasses, which
work outside a request context (only ``.send()`` would need it).

Places lookups are monkeypatched so we never hit the network.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import chainlit as cl
from chainlit.context import ChainlitContext, context_var
from chainlit.session import HTTPSession

from multiagent.web import sidebar
from multiagent.web.sidebar import (
    PANELS,
    SidebarContext,
    build_focus_actions,
    panel_gallery,
    panel_overview,
    panel_reviews,
)


@pytest.fixture(autouse=True)
def _chainlit_ctx(monkeypatch: pytest.MonkeyPatch):
    """Chainlit ``Element`` constructors read ``context.session.thread_id``
    via a default factory, and ``ChainlitContext.__init__`` calls
    ``asyncio.get_running_loop()``. ``init_http_context`` doesn't work
    here because its ``context_var.set()`` would be scoped to the
    short-lived ``asyncio.run()`` task.

    So we build the context manually with a fake loop, then set the
    ContextVar in the test's own context — that's what stays in scope
    for the test body.
    """
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
    session = HTTPSession(id="test-session", client_type="webapp", thread_id="test-thread")
    ctx = ChainlitContext(session)
    token = context_var.set(ctx)
    try:
        yield
    finally:
        context_var.reset(token)
        loop.close()


SAMPLE_TRIP: dict[str, Any] = {
    "status": "draft",
    "destination": "Goa",
    "origin": "Bengaluru",
    "departure_date": "2026-01-10",
    "return_date": "2026-01-15",
    "travelers": "2 adults, 1 child (age 11)",
    "notes": "Beach holiday with some history",
    "selected_flights": [{"airline": "IndiGo", "price": 8500}],
    "selected_hotels": [
        {"name": "Taj Exotica Resort", "price": 12000},
        {"name": "W Goa", "price": 18000},
    ],
    "selected_activities": [
        {"name": "Dudhsagar Falls Trek"},
        {"name": "Old Goa Churches"},
    ],
    "day_wise_itinerary": [{"day": 1}, {"day": 2}, {"day": 3}],
    "cost_breakdown": {"flights": 17000, "hotels": 60000, "activities": 5000},
    "total_cost": 82000,
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub all Places lookups so tests never touch the network."""

    def fake_photos(name: str, city: str, max_photos: int = 3) -> list[str]:
        return [
            f"https://example.test/{city.lower()}/{name.replace(' ', '_').lower()}/{i}.jpg"
            for i in range(min(max_photos, 2))
        ]

    def fake_summary(name: str, city: str) -> dict[str, Any] | None:
        return {
            "place_id": f"pid-{name}",
            "name": name,
            "rating": 4.5,
            "review_count": 1234,
            "editorial_summary": f"{name} in {city} is a beloved spot.",
            "website": "https://example.test/",
            "reviews": [
                {"rating": 5, "text": "Loved the views!", "author": "Asha"},
                {"rating": 4, "text": "Crowded but worth it.", "author": "Rohan"},
            ],
        }

    monkeypatch.setattr(sidebar.places_cache, "get_photos", fake_photos)
    monkeypatch.setattr(sidebar.places_cache, "get_summary", fake_summary)


# --- registry -------------------------------------------------------------


def test_panels_registry_is_non_empty() -> None:
    assert PANELS, "PANELS must not be empty"
    for p in PANELS:
        assert callable(p)


def test_panels_each_have_a_name() -> None:
    names = [p.__name__ for p in PANELS]
    assert "panel_overview" in names
    assert "panel_gallery" in names
    assert "panel_reviews" in names


# --- panel_overview -------------------------------------------------------


def test_overview_with_no_trip_shows_empty_state() -> None:
    ctx = SidebarContext(trip=None, focus=None, user_id="u")
    out = panel_overview(ctx)
    assert len(out) == 1
    assert isinstance(out[0], cl.Text)
    assert "No active trip yet" in out[0].content


def test_overview_with_trip_includes_destination_and_counts() -> None:
    ctx = SidebarContext(trip=SAMPLE_TRIP, focus=None, user_id="u")
    out = panel_overview(ctx)
    assert len(out) == 1
    content = out[0].content
    assert "Goa" in content
    assert "2026-01-10" in content
    assert "Hotels: 2" in content
    assert "Activities: 2" in content
    assert "₹82,000" in content


def test_overview_mentions_focus_when_focused() -> None:
    ctx = SidebarContext(
        trip=SAMPLE_TRIP,
        focus={"kind": "hotel", "name": "Taj Exotica Resort"},
        user_id="u",
    )
    out = panel_overview(ctx)
    assert "Taj Exotica Resort" in out[0].content
    assert "Whole trip" in out[0].content  # reset hint


# --- panel_gallery --------------------------------------------------------


def test_gallery_empty_without_trip() -> None:
    ctx = SidebarContext(trip=None, focus=None, user_id="u")
    assert panel_gallery(ctx) == []


def test_gallery_returns_images_for_each_item() -> None:
    ctx = SidebarContext(trip=SAMPLE_TRIP, focus=None, user_id="u")
    out = panel_gallery(ctx)
    # 4 items × 2 stub photos = 8 images
    assert all(isinstance(e, cl.Image) for e in out)
    assert len(out) == 8


def test_gallery_only_focused_item_when_focus_set() -> None:
    ctx = SidebarContext(
        trip=SAMPLE_TRIP,
        focus={"kind": "hotel", "name": "Taj Exotica Resort"},
        user_id="u",
    )
    out = panel_gallery(ctx)
    assert len(out) == 2  # only Taj Exotica's photos
    for e in out:
        assert "Taj Exotica Resort" in e.name


def test_gallery_skips_items_without_a_name() -> None:
    trip = {
        "destination": "Goa",
        "selected_hotels": [{"price": 100}, {"name": "Taj"}],
        "selected_activities": [],
    }
    ctx = SidebarContext(trip=trip, focus=None, user_id="u")
    out = panel_gallery(ctx)
    # Only the named hotel produces photos
    assert len(out) == 2
    assert all("Taj" in e.name for e in out)


# --- panel_reviews --------------------------------------------------------


def test_reviews_empty_without_trip() -> None:
    ctx = SidebarContext(trip=None, focus=None, user_id="u")
    assert panel_reviews(ctx) == []


def test_reviews_returns_single_text_with_each_item() -> None:
    ctx = SidebarContext(trip=SAMPLE_TRIP, focus=None, user_id="u")
    out = panel_reviews(ctx)
    assert len(out) == 1
    assert isinstance(out[0], cl.Text)
    content = out[0].content
    # Editorial summaries
    assert "Taj Exotica Resort" in content
    assert "Dudhsagar Falls Trek" in content
    # Star ratings + review snippets
    assert "⭐" in content
    assert "Loved the views!" in content


def test_reviews_skips_items_without_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sidebar.places_cache, "get_summary", lambda n, c: None)
    ctx = SidebarContext(trip=SAMPLE_TRIP, focus=None, user_id="u")
    assert panel_reviews(ctx) == []


# --- build_focus_actions --------------------------------------------------


def test_focus_actions_empty_without_trip() -> None:
    assert build_focus_actions(None) == []


def test_focus_actions_one_per_hotel_and_activity_plus_reset() -> None:
    actions = build_focus_actions(SAMPLE_TRIP)
    # 2 hotels + 2 activities + 1 reset
    assert len(actions) == 5
    labels = [a.label for a in actions]
    assert any("Taj Exotica Resort" in lbl for lbl in labels)
    assert any("W Goa" in lbl for lbl in labels)
    assert any("Dudhsagar" in lbl for lbl in labels)
    assert any("Old Goa Churches" in lbl for lbl in labels)
    assert labels[-1].startswith("🌐")


def test_focus_actions_payloads_are_well_formed() -> None:
    actions = build_focus_actions(SAMPLE_TRIP)
    for a in actions:
        assert a.name == "focus_item"
        assert isinstance(a.payload, dict)
        assert "kind" in a.payload
        assert "name" in a.payload


def test_focus_actions_no_reset_when_no_real_items() -> None:
    trip = {"destination": "X", "selected_hotels": [], "selected_activities": []}
    assert build_focus_actions(trip) == []
