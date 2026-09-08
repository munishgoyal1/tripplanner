"""Tests for persistent shared trip snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest

from tripplanner import user_context
from tripplanner.tools import trip_history, trip_planner
from tripplanner.web import share


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin trip-planner files to a temp dir; restore user_id after each test."""
    monkeypatch.setattr(trip_planner, "_TRIPS_DIR", tmp_path / ".tripplanner")
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", tmp_path / ".tripplanner" / "active_trip.json")
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", tmp_path / ".tripplanner" / "trips")
    monkeypatch.setattr(trip_history, "_TRIPS_DIR", tmp_path / ".tripplanner")
    monkeypatch.setattr(trip_history, "_ACTIVE_TRIP_FILE", tmp_path / ".tripplanner" / "active_trip.json")
    monkeypatch.setattr(trip_history, "_TRIP_HISTORY_DIR", tmp_path / ".tripplanner" / "trips")
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


def _decision(**extra) -> dict:
    decision = {
        "id": "dec_transport_lisbon_porto_2026_10_02",
        "kind": "transport_mode",
        "subject": "Lisbon to Porto",
        "scope": {"day": 2, "from_place": "Lisbon", "to_place": "Porto"},
        "rule": {"code": "door_to_door_time", "text": "Fastest door to door."},
        "chosen_option_id": "opt_train",
        "priced": "full",
        "options": [
            {
                "id": "opt_train",
                "mode": "train",
                "label": "Train",
                "price": {"amount": 32.0, "currency": "EUR"},
                "priced": True,
                "duration_estimated": False,
                "day_cost": 41.0,
                "provider_ref": "off_0000AbC",
                "source": {
                    "provider": "Rail Europe",
                    "checked_at": "2026-09-15T08:00:00",
                    "confidence": "live",
                    "url": "https://rail.example/booking?apikey=secret",
                },
            },
            {
                "id": "opt_flight",
                "mode": "flight",
                "label": "Flight",
                "price": {"amount": 118.0, "currency": "EUR"},
                "priced": True,
                "rejected_because": "Two hours slower once airport time is counted.",
                "source": {
                    "provider": "Duffel",
                    "checked_at": "2026-09-15T08:00:00",
                    "url": "https://duffel.example/offer/1",
                },
            },
        ],
    }
    decision.update(extra)
    return decision


def test_sanitized_decision_keeps_the_reasoning_and_drops_the_plumbing() -> None:
    [public] = share.sanitize_decisions([_decision()])
    assert public["rule_text"] == "Fastest door to door."
    assert "rule" not in public
    train = public["options"][0]
    assert "provider_ref" not in train
    assert "day_cost" not in train
    assert train["duration_estimated"] is False
    assert train["source"]["provider"] == "Rail Europe"


def test_sanitized_decision_drops_a_keyed_url_and_keeps_a_plain_one() -> None:
    [public] = share.sanitize_decisions([_decision()])
    assert public["options"][0]["source"].get("url", "") == ""
    assert public["options"][1]["source"]["url"] == "https://duffel.example/offer/1"


def test_sanitized_decision_shows_the_overruled_choice_not_the_agent_one() -> None:
    overruled = _decision(
        state="overruled",
        override={"option_id": "opt_flight", "at": "2026-09-16T09:00:00"},
    )
    [public] = share.sanitize_decisions([overruled])
    assert public["chosen_option_id"] == "opt_flight"


def test_shared_plan_carries_decisions_and_price_checks() -> None:
    _write_active(
        _make_plan(
            decisions=[_decision()],
            price_checks=[
                {
                    "kind": "flights",
                    "provider": "Duffel",
                    "checked_at": "2026-09-15T08:00:00",
                    "expires_at": "2026-09-15T08:30:00",
                }
            ],
        )
    )
    resolved = share.resolve(share.mint_for_active_trip())
    assert resolved is not None
    public = resolved["plan"]
    assert public["decisions"][0]["subject"] == "Lisbon to Porto"
    assert public["price_checks"][0]["provider"] == "Duffel"


def test_shared_stay_drops_opaque_provider_references_at_every_level() -> None:
    plan = _make_plan(
        selected_hotels=[
            {
                "name": "Memmo Alfama",
                "provider_ref": {"hotel_id": "hotel-42", "rate_id": "rate-7"},
                "source": {"provider": "LiteAPI", "checked_at": "2026-09-15T08:00:00"},
            }
        ],
        decisions=[
            _decision(
                kind="lodging",
                options=[
                    {
                        "id": "opt_memmo",
                        "mode": None,
                        "label": "Memmo Alfama",
                        "price": {"amount": 640, "currency": "EUR"},
                        "lodging": {
                            "room_name": "River view king",
                            "provider_ref": {"hotel_id": "hotel-42", "rate_id": "rate-7"},
                        },
                    }
                ],
            )
        ],
    )

    public = share.sanitize_plan(plan)

    assert "provider_ref" not in public["selected_hotels"][0]
    assert "provider_ref" not in public["decisions"][0]["options"][0]["lodging"]
    assert public["selected_hotels"][0]["source"]["provider"] == "LiteAPI"


def test_shared_flight_drops_opaque_provider_references_at_every_level() -> None:
    plan = _make_plan(
        selected_flights=[
            {
                "airline": "Air India",
                "provider_ref": {"offer_id": "off-direct"},
                "source": {"provider": "Duffel", "checked_at": "2026-09-15T08:00:00"},
            }
        ],
        decisions=[
            _decision(
                kind="flight",
                options=[
                    {
                        "id": "opt_direct",
                        "mode": "flight",
                        "label": "Air India",
                        "price": {"amount": 900, "currency": "USD"},
                        "flight": {
                            "origin": "DEL",
                            "destination": "LHR",
                            "provider_ref": {"offer_id": "off-direct"},
                        },
                    }
                ],
            )
        ],
    )

    public = share.sanitize_plan(plan)

    assert "provider_ref" not in public["selected_flights"][0]
    assert "provider_ref" not in public["decisions"][0]["options"][0]["flight"]
    assert public["selected_flights"][0]["source"]["provider"] == "Duffel"

