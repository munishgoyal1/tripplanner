"""Tests for persistent shared trip snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest

from tripplanner import user_context
from tripplanner.tools import trip_planner
from tripplanner.web import share


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin trip-planner files to a temp dir; restore user_id after each test."""
    monkeypatch.setattr(trip_planner, "_TRIPS_DIR", tmp_path / ".tripplanner")
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", tmp_path / ".tripplanner" / "active_trip.json")
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", tmp_path / ".tripplanner" / "trips")
    monkeypatch.setenv("WEB_SESSION_SECRET", "test-secret-pin")
    user_context.set_user_id("alice")
    yield
    user_context.set_user_id("local")


def _make_plan(**extra) -> dict:
    plan = {
        "destination": "Lisbon",
        "departure_date": "2026-10-01",
        "return_date": "2026-10-05",
        "created_at": "2026-09-15T08:00:00",
        "selected_hotels": [{"name": "Pousada"}],
        "day_wise_itinerary": [{"day": 1, "plan": "Tram 28 ride"}],
        # Owner-only field that must NOT leak to the public view:
        "agent_scratchpad": "private notes only the owner sees",
    }
    plan.update(extra)
    return plan


def _write_active(plan: dict) -> None:
    """Bypass the @tool by writing directly to the local-mode file."""
    from tripplanner.user_context import get_user_id

    uid = get_user_id()
    user_dir = trip_planner._TRIPS_DIR / "users" / uid
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "active_trip.json").write_text(
        __import__("json").dumps(plan), encoding="utf-8"
    )


def test_token_is_idempotent() -> None:
    """Sharing the same unchanged snapshot yields the same token."""
    plan = _make_plan()
    _write_active(plan)
    t1 = share.mint_for_active_trip()
    t2 = share.mint_for_active_trip()
    assert t1 == t2


def test_new_snapshot_after_plan_changes() -> None:
    _write_active(_make_plan())
    t1 = share.mint_for_active_trip()
    _write_active(_make_plan(summary="updated summary"))
    t2 = share.mint_for_active_trip()
    assert t1 != t2


def test_mint_for_active_trip_returns_none_without_plan() -> None:
    assert share.mint_for_active_trip() is None


def test_resolve_active_trip() -> None:
    plan = _make_plan()
    _write_active(plan)
    token = share.mint_for_active_trip()
    assert token is not None
    resolved = share.resolve(token)
    assert resolved is not None
    assert resolved["plan"]["destination"] == "Lisbon"
    assert resolved["plan"]["day_wise_itinerary"][0]["plan"] == "Tram 28 ride"
    assert "<html>" in resolved["html"].lower()


def test_resolve_strips_private_fields() -> None:
    plan = _make_plan()
    _write_active(plan)
    token = share.mint_for_active_trip()
    resolved = share.resolve(token)
    public = resolved["plan"]
    assert "agent_scratchpad" not in public
    # And only public keys are present:
    for key in public:
        assert key in {
            "destination",
            "origin",
            "departure_date",
            "return_date",
            "travelers",
            "trip_style",
            "interests",
            "status",
            "selected_flights",
            "selected_hotels",
            "selected_activities",
            "day_wise_itinerary",
            "estimated_total_cost",
            "total_cost",
            "currency",
            "notes",
            "summary",
            "created_at",
            "updated_at",
        }


def test_resolve_returns_none_for_unknown_trip() -> None:
    assert share.resolve("s1_missing") is None


def test_snapshot_survives_live_trip_changes() -> None:
    _write_active(_make_plan(summary="first"))
    token = share.mint_for_active_trip()
    _write_active(_make_plan(summary="second"))
    resolved = share.resolve(token)
    assert resolved is not None
    assert resolved["plan"].get("summary") == "first"


def test_import_shared_snapshot_creates_active_trip_for_viewer() -> None:
    _write_active(_make_plan(summary="family copy"))
    token = share.mint_for_active_trip()
    snapshot = share.resolve(token)
    assert snapshot is not None

    user_context.set_user_id("bob")
    imported = trip_planner.import_shared_trip_snapshot(snapshot["plan"])
    active = trip_planner.load_active_trip_dict()

    assert active is not None
    assert imported["destination"] == "Lisbon"
    assert active["summary"] == "family copy"
    assert active["imported_from_share"] is True
    assert active["trip_id"] == imported["trip_id"]

