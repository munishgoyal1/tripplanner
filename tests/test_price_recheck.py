from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from tripplanner.decisions import price_recheck
from tripplanner.providers.models import FlightOffer, HotelOffer, Money
from tripplanner.tools import trip_planner


def _stale_check(kind: str, provider: str) -> dict[str, str]:
    return {
        "kind": kind,
        "provider": provider,
        "checked_at": "2026-01-01T00:00:00+00:00",
        "expires_at": "2026-01-01T00:01:00+00:00",
    }


def test_exact_flight_recheck_records_movement_without_mutating_selection(monkeypatch) -> None:
    selected = {
        "airline": "Example Air",
        "price": 400,
        "currency": "EUR",
        "booking_status": "planned",
        "provider_ref": {"offer_id": "offer-1"},
        "source": {"provider": "liteapi"},
    }
    plan = {
        "status": "finalized",
        "selected_flights": [selected],
        "price_checks": [_stale_check("flights", "liteapi")],
    }
    offer = FlightOffer(
        provider="liteapi",
        provider_ref={"offer_id": "offer-1"},
        total=Money(amount=430, currency="EUR", all_in=True),
        segments=[],
        quoted_at=datetime.now(UTC),
    )
    provider = SimpleNamespace(
        name="liteapi",
        verify_flight=lambda offer_id: offer if offer_id == "offer-1" else None,
    )
    monkeypatch.setattr(price_recheck, "get_flight_providers", lambda: [provider])
    monkeypatch.setattr(price_recheck, "get_hotel_providers", lambda: [])

    outcome = price_recheck.recheck_prices(plan)

    assert plan["selected_flights"] == [selected]
    assert outcome["results"][0]["current_total"] == 430
    assert outcome["results"][0]["delta"] == 30
    assert outcome["results"][0]["status"] == "live"
    assert plan["price_checks"][0]["expires_at"] > plan["price_checks"][0]["checked_at"]


def test_hotel_recheck_refuses_to_guess_missing_occupancy_context(monkeypatch) -> None:
    plan = {
        "status": "finalized",
        "selected_hotels": [
            {
                "name": "LX Boutique",
                "total": 420,
                "booking_status": "planned",
                "source": {"provider": "liteapi"},
            }
        ],
        "price_checks": [_stale_check("lodging", "liteapi")],
    }
    provider = SimpleNamespace(
        name="liteapi",
        search_hotels=lambda _query: (_ for _ in ()).throw(AssertionError("must not search")),
    )
    monkeypatch.setattr(price_recheck, "get_flight_providers", lambda: [])
    monkeypatch.setattr(price_recheck, "get_hotel_providers", lambda: [provider])

    outcome = price_recheck.recheck_prices(plan)

    assert outcome["results"][0]["status"] == "unavailable"
    assert "occupancy and nationality" in outcome["results"][0]["reason"]
    assert plan["price_checks"] == [_stale_check("lodging", "liteapi")]


def test_exact_hotel_recheck_uses_preserved_search_context(monkeypatch) -> None:
    selected = {
        "name": "LX Boutique",
        "room_name": "Deluxe",
        "board_name": "Breakfast",
        "refundable": True,
        "checkin": "2026-09-10",
        "checkout": "2026-09-13",
        "total": 420,
        "currency": "EUR",
        "booking_status": "planned",
        "provider_ref": {"hotel_id": "lx"},
        "source": {"provider": "liteapi"},
        "search_context": {
            "destination": "Lisbon",
            "adults_per_room": 2,
            "rooms": 1,
            "children_ages": [],
            "guest_nationality": "GB",
            "refundable_only": True,
        },
    }
    plan = {
        "status": "finalized",
        "destination": "Lisbon",
        "selected_hotels": [selected],
        "price_checks": [_stale_check("lodging", "liteapi")],
    }
    offer = HotelOffer(
        provider="liteapi",
        provider_ref={"hotel_id": "lx", "offer_id": "fresh"},
        hotel_name="LX Boutique",
        search_destination="Lisbon",
        room_name="Deluxe",
        board_name="Breakfast",
        total=Money(amount=390, currency="EUR", all_in=True),
        refundable=True,
        quoted_at=datetime.now(UTC),
    )
    seen_queries = []
    provider = SimpleNamespace(
        name="liteapi",
        search_hotels=lambda query: seen_queries.append(query) or [offer],
    )
    monkeypatch.setattr(price_recheck, "get_flight_providers", lambda: [])
    monkeypatch.setattr(price_recheck, "get_hotel_providers", lambda: [provider])

    outcome = price_recheck.recheck_prices(plan)

    assert plan["selected_hotels"] == [selected]
    assert seen_queries[0].guest_nationality == "GB"
    assert outcome["results"][0]["current_total"] == 390
    assert outcome["results"][0]["delta"] == -30


def test_active_trip_recheck_rejects_a_stale_revision(monkeypatch) -> None:
    plan = {"status": "finalized", "updated_at": "newer"}
    monkeypatch.setattr(trip_planner, "_load_active_trip", lambda: plan)
    monkeypatch.setattr(
        price_recheck,
        "recheck_prices",
        lambda _plan: (_ for _ in ()).throw(AssertionError("must not call provider")),
    )

    outcome = trip_planner.recheck_active_trip_prices(expected_updated_at="older")

    assert outcome["ok"] is False
    assert outcome["stale"] is True
