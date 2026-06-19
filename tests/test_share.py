"""Tests for read-only share-link tokens (#6.3)."""

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


def test_mint_and_verify_roundtrip() -> None:
    token = share.mint_token("alice", "2026-09-15T08:00:00")
    payload = share.verify_token(token)
    assert payload == {"u": "alice", "c": "2026-09-15T08:00:00"}


def test_token_is_idempotent() -> None:
    """Same (owner, trip) -> same token, so share links are stable."""
    t1 = share.mint_token("alice", "2026-09-15T08:00:00")
    t2 = share.mint_token("alice", "2026-09-15T08:00:00")
    assert t1 == t2


def test_token_is_unguessable_per_owner() -> None:
    t_alice = share.mint_token("alice", "2026-09-15T08:00:00")
    t_bob = share.mint_token("bob", "2026-09-15T08:00:00")
    assert t_alice != t_bob


def test_verify_rejects_tampered_token() -> None:
    token = share.mint_token("alice", "2026-09-15T08:00:00")
    head, body, sig = token.split(".")
    # Flip a byte in the signature.
    bad_sig = sig[:-2] + ("aa" if sig[-2:] != "aa" else "bb")
    assert share.verify_token(f"{head}.{body}.{bad_sig}") is None


def test_verify_rejects_secret_rotation() -> None:
    token = share.mint_token("alice", "2026-09-15T08:00:00")
    import os

    os.environ["WEB_SESSION_SECRET"] = "rotated-secret"
    try:
        assert share.verify_token(token) is None
    finally:
        os.environ["WEB_SESSION_SECRET"] = "test-secret-pin"


def test_verify_rejects_garbage() -> None:
    assert share.verify_token("") is None
    assert share.verify_token("not.a.token.at.all") is None
    assert share.verify_token("v1.notbase64!!.also-not") is None


def test_mint_for_active_trip_returns_none_without_plan() -> None:
    assert share.mint_for_active_trip() is None


def test_resolve_active_trip() -> None:
    plan = _make_plan()
    _write_active(plan)
    token = share.mint_for_active_trip()
    assert token is not None
    resolved = share.resolve(token)
    assert resolved is not None
    assert resolved["destination"] == "Lisbon"
    assert resolved["day_wise_itinerary"][0]["plan"] == "Tram 28 ride"


def test_resolve_strips_private_fields() -> None:
    plan = _make_plan()
    _write_active(plan)
    token = share.mint_for_active_trip()
    resolved = share.resolve(token)
    assert "agent_scratchpad" not in resolved
    # And only public keys are present:
    for key in resolved:
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
            "currency",
            "notes",
            "summary",
        }


def test_resolve_returns_none_for_unknown_trip() -> None:
    token = share.mint_token("alice", "2099-01-01T00:00:00")
    assert share.resolve(token) is None

