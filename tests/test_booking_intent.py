from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tripplanner.decisions import booking_intent as booking
from tripplanner.decisions.apply import _flight_item, _lodging_item
from tripplanner.decisions.models import (
    Decision,
    FlightFacts,
    LodgingFacts,
    Option,
    Price,
    Rule,
    Source,
)
from tripplanner.decisions.store import upsert_decision
from tripplanner.tools import trip_planner
from tripplanner.web import booking_export, booking_http, share


def make_plan():
    source = Source(
        provider="liteapi",
        checked_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    flight = Decision(
        id="flight-del-goi",
        kind="flight",
        created_at=datetime.now(UTC),
        rule=Rule(code="test", text="Fewest stops"),
        chosen_option_id="flight-1",
        options=[
            Option(
                id=f"flight-{i}",
                label=f"Carrier {i}",
                source=source,
                price=Price(amount=amount, currency="INR", basis="per_party", all_in=True),
                flight=FlightFacts(
                    origin="DEL",
                    destination="GOI",
                    departure_date="2026-12-01",
                    return_date="2026-12-03",
                    search_context={"adults": 2},
                    baggage={"checked": "1 bag"},
                    provider_ref={"offer_id": f"secret-{i}"},
                ),
            )
            for i, amount in [(1, 90000), (2, 110000), (3, 80000)]
        ],
    )
    hotel = Decision(
        id="stay-goa",
        kind="lodging",
        created_at=datetime.now(UTC),
        rule=Rule(code="test", text="Lowest total"),
        chosen_option_id="hotel-1",
        options=[
            Option(
                id=f"hotel-{i}",
                label=f"Hotel {i}",
                source=source,
                price=Price(amount=amount, currency="INR", basis="per_party", all_in=True),
                lodging=LodgingFacts(
                    checkin="2026-12-01",
                    checkout="2026-12-03",
                    room_name="Double",
                    search_context={"adults_per_room": 2, "rooms": 1},
                ),
            )
            for i, amount in [(1, 70000), (2, 60000)]
        ],
    )
    plan = {
        "trip_id": "goa-1",
        "updated_at": "v1",
        "destination": "Goa",
        "currency": "INR",
        "travelers": "2 adults",
        "departure_date": "2026-12-01",
        "return_date": "2026-12-03",
        "total_cost": 161000,
        "category_caps": {
            "flights": {"amount": 100000, "currency": "INR"},
            "hotels": {"amount": 80000, "currency": "INR"},
        },
        "selected_flights": [_flight_item(flight.chosen, flight)],
        "selected_hotels": [_lodging_item(hotel.chosen, hotel)],
        "day_wise_itinerary": [
            {
                "day": 1,
                "date": "2026-12-01",
                "stops": [
                    {"name": "Hotel 1", "kind": "hotel"},
                    {
                        "name": "Museum",
                        "kind": "attraction",
                        "time": "12:00",
                        "price": 1000,
                        "currency": "INR",
                        "url": "https://example.com/tickets",
                    },
                ],
            },
            {"day": 2, "date": "2026-12-02", "stops": [{"name": "Hotel 1", "kind": "hotel"}]},
        ],
    }
    upsert_decision(plan, flight)
    upsert_decision(plan, hotel)
    return plan


def test_purchase_grouping_caps_and_zero_external_reads(monkeypatch):
    from tripplanner import http_client

    monkeypatch.setattr(
        http_client, "get", lambda *a, **k: pytest.fail("Projection called network")
    )
    view = booking.build_booking_view(make_plan())
    assert len(view["rows"]) == 3
    assert view["budgets"]["hotels"]["known_total"] == 70000
    assert view["budgets"]["flights"]["status"] == "within_cap"
    assert "secret-" not in json.dumps(view)


def test_selected_activity_and_occurrence_share_one_purchase():
    plan = make_plan()
    plan["selected_activities"] = [
        {
            "title": "Museum",
            "total": {"amount": 1000, "currency": "INR"},
            "provider_url": "https://example.com/museum",
        }
    ]
    rows = [row for row in booking.units(plan) if row["category"] == "tickets"]
    assert len(rows) == 1 and len(rows[0]["_targets"]) == 2 and rows[0]["amount"] == 1000
    candidate, _ = booking.prepare_change(
        plan,
        {
            "action": "report",
            "item_id": rows[0]["id"],
            "actual": {"product": "Museum guided entry", "provider": "Venue", "amount": 1200},
        },
    )
    assert candidate["selected_activities"][0]["booked"]
    assert candidate["day_wise_itinerary"][0]["stops"][1]["booked"]
    assert candidate["total_cost"] == 161200
    assert len([row for row in booking.units(candidate) if row["category"] == "tickets"]) == 1


def test_choose_is_atomic_separate_caps_and_no_duplicate_purchase():
    plan = make_plan()
    before = deepcopy(plan)
    with pytest.raises(ValueError, match="flights cap"):
        booking.prepare_change(
            plan, {"action": "choose", "item_id": "flight-del-goi", "option_id": "flight-2"}
        )
    assert plan == before
    candidate, _ = booking.prepare_change(
        plan, {"action": "choose", "item_id": "flight-del-goi", "option_id": "flight-3"}
    )
    assert len(candidate["selected_flights"]) == 1
    assert candidate["selected_flights"][0]["price"] == 80000
    assert candidate["total_cost"] == 151000
    assert plan == before


def test_lock_is_not_booked_and_changed_context_invalidates():
    plan, _ = booking.prepare_change(make_plan(), {"action": "lock", "item_id": "stay-goa"})
    row = next(r for r in booking.build_booking_view(plan)["rows"] if r["id"] == "stay-goa")
    assert row["intent_state"] == "locked" and not row["booked"]
    plan["travelers"] = "3 adults"
    row = next(r for r in booking.build_booking_view(plan)["rows"] if r["id"] == "stay-goa")
    assert row["intent_state"] == "needs_review"
    assert row["intended"]["name"] == "Hotel 1"


def test_historical_prices_and_unknown_fx_never_verify_cap():
    plan = make_plan()
    plan["selected_flights"][0]["source"]["expires_at"] = "2020-01-01T00:00:00Z"
    plan["selected_hotels"][0]["currency"] = "EUR"
    view = booking.build_booking_view(plan)
    assert view["rows"][0]["evidence"] == "stale"
    assert view["budgets"]["flights"]["status"] == "unverified"
    assert view["budgets"]["hotels"]["unknown_items"] == 1


def test_external_booking_updates_existing_stay_and_redacts_exports(tmp_path, monkeypatch):
    plan, _ = booking.prepare_change(make_plan(), {"action": "lock", "item_id": "stay-goa"})
    actual = {
        "product": "Booked hotel",
        "provider": "Offline agent",
        "amount": 75000,
        "currency": "INR",
        "reference": "PRIVATE-CONFIRMATION",
        "notes": "private passenger note",
    }
    candidate, _ = booking.prepare_change(
        plan, {"action": "report", "item_id": "stay-goa", "actual": actual}
    )
    assert len(candidate["selected_hotels"]) == 1
    assert candidate["selected_hotels"][0]["booked"]
    assert all(day["stops"][0]["name"] == "Booked hotel" for day in candidate["day_wise_itinerary"])
    assert candidate["total_cost"] == 166000
    row = next(r for r in booking.build_booking_view(candidate)["rows"] if r["id"] == "stay-goa")
    assert row["actual"]["reference"] == "PRIVATE-CONFIRMATION"
    assert row["intended"]["name"] == "Hotel 1"
    packet = json.dumps(booking_export.snapshot(candidate))
    html = booking_export.build_html(candidate)
    assert "PRIVATE-CONFIRMATION" not in packet + html
    assert "private passenger note" not in packet + html
    assert "secret-" not in packet + html
    assert booking_export.build_pdf(candidate).startswith(b"%PDF")
    monkeypatch.setattr(share, "_local_snapshot_dir", lambda: tmp_path)
    token = share.mint_booking_intent(candidate)
    candidate["destination"] = "Changed later"
    assert "Changed later" not in share._load_snapshot(token)["html"]


def test_duplicate_reports_same_item_edit_and_cross_item_rejection():
    plan = make_plan()
    actual = {"product": "Air", "provider": "Agent", "reference": "same", "amount": 90000}
    plan, _ = booking.prepare_change(
        plan, {"action": "report", "item_id": "flight-del-goi", "actual": actual}
    )
    plan, _ = booking.prepare_change(
        plan, {"action": "report", "item_id": "flight-del-goi", "actual": actual}
    )
    assert len(plan["selected_flights"]) == 1 and plan["total_cost"] == 161000
    with pytest.raises(ValueError, match="already attached"):
        booking.prepare_change(plan, {"action": "report", "item_id": "stay-goa", "actual": actual})


def test_ticket_unknown_paid_amount_and_date_conflict():
    plan = make_plan()
    ticket = next(r for r in booking.units(plan) if r["category"] == "tickets")
    command = {
        "action": "report",
        "item_id": ticket["id"],
        "actual": {"product": "Museum slot", "provider": "Venue", "amount": None},
    }
    candidate, warnings = booking.prepare_change(plan, command)
    assert candidate["day_wise_itinerary"][0]["stops"][1]["price"] is None
    assert warnings
    command["actual"]["start_date"] = "2026-12-02"
    moved, _ = booking.prepare_change(plan, command)
    assert len(moved["day_wise_itinerary"][0]["stops"]) == 1
    assert any(
        stop.get("booking_item_id") == ticket["id"]
        for stop in moved["day_wise_itinerary"][1]["stops"]
    )
    command["actual"]["start_date"] = "2026-12-05"
    with pytest.raises(ValueError, match="Add the booked date"):
        booking.prepare_change(plan, command)
    assert not plan["day_wise_itinerary"][0]["stops"][1].get("booked")


def test_single_researched_choice_can_be_materialized_and_locked():
    plan = make_plan()
    plan["selected_flights"] = []
    candidate, _ = booking.prepare_change(plan, {"action": "lock", "item_id": "flight-del-goi"})
    assert len(candidate["selected_flights"]) == 1
    assert booking.build_booking_view(candidate)["locked_count"] == 1


@pytest.fixture
def client(monkeypatch):
    plan = make_plan()
    monkeypatch.setattr(trip_planner, "load_active_trip_dict", lambda: deepcopy(plan))

    def save(candidate):
        candidate["updated_at"] = "v2"
        plan.clear()
        plan.update(deepcopy(candidate))

    monkeypatch.setattr(trip_planner, "_save_active_trip", save)
    monkeypatch.setattr(booking_http, "set_request_user", lambda *a: "booking-test")
    app = FastAPI()
    app.include_router(booking_http.router)
    with TestClient(app) as test_client:
        yield test_client, plan


def test_http_preview_apply_trip_binding_and_replay(client):
    http, plan = client
    command = {"trip_id": "goa-1", "updated_at": "v1", "action": "lock", "item_id": "stay-goa"}
    preview = http.post("/trip/bookings", json=command)
    assert preview.status_code == 200
    assert "booking_intent" not in plan
    token = preview.json()["preview_token"]
    assert (
        http.post(
            "/trip/bookings", json={**command, "preview": False, "preview_token": "bad"}
        ).status_code
        == 422
    )
    response = http.post(
        "/trip/bookings", json={**command, "preview": False, "preview_token": token}
    )
    assert response.status_code == 200 and response.json()["bookings"]["locked_count"] == 1
    assert (
        http.post(
            "/trip/bookings", json={**command, "preview": False, "preview_token": token}
        ).status_code
        == 409
    )
    assert http.get("/trip/bookings?trip_id=another-trip").status_code == 409
    assert (
        http.get("/trip/bookings/export.json?trip_id=another-trip&updated_at=v2").status_code == 409
    )


def test_recommendation_applies_cap_before_stops():
    plan = make_plan()
    decision = booking.list_decisions(plan)[0]
    decision.options[0].flight.stops = 0
    decision.options[1].flight.stops = 0
    decision.options[2].flight.stops = 1
    plan["category_caps"]["flights"]["amount"] = 85000
    assert booking.constrain_recommendation(plan, decision).chosen_option_id == "flight-3"


def test_refreshed_same_offer_needs_explicit_acceptance(monkeypatch):
    plan = make_plan()
    refreshed = booking.list_decisions(plan)[0]
    refreshed.options[0].price.amount = 95000
    monkeypatch.setattr(trip_planner, "_load_active_trip", lambda: plan)
    monkeypatch.setattr(trip_planner, "_save_active_trip", lambda candidate: None)
    assert trip_planner.record_trip_decision(refreshed)
    assert plan["selected_flights"][0]["price"] == 90000
    candidate, _ = booking.prepare_change(
        plan, {"action": "choose", "item_id": "flight-del-goi", "option_id": "flight-1"}
    )
    assert candidate["selected_flights"][0]["price"] == 95000
    assert candidate["total_cost"] == 166000


def test_manual_ticket_intent_is_public_research_without_a_booking():
    plan = make_plan()
    ticket = next(row for row in booking.units(plan) if row["category"] == "tickets")
    candidate, _ = booking.prepare_change(
        plan,
        {
            "action": "manual",
            "item_id": ticket["id"],
            "actual": {
                "product": "Museum timed entry",
                "provider": "Venue",
                "amount": 1200,
                "currency": "INR",
                "start_date": "2026-12-01",
                "time": "12:00",
                "notes": "Two adult entries, guided tour",
                "url": "https://example.com/museum",
            },
        },
    )
    row = next(
        row for row in booking.build_booking_view(candidate)["rows"] if row["id"] == ticket["id"]
    )
    assert row["name"] == "Museum timed entry" and row["amount"] == 1200
    assert not row["booked"] and row["evidence"] == "unverified"
    assert candidate["total_cost"] == 161200
    assert "Two adult entries" in candidate["day_wise_itinerary"][0]["stops"][1]["note"]
    assert "https://example.com/museum" in booking_export.build_html(candidate)


def test_hotel_variant_and_repeat_stay_are_not_collapsed():
    from tripplanner.decisions.lodging import options_from_offers, reconcile_selected_lodging
    from tripplanner.providers.models import HotelOffer, Money

    plan = make_plan()
    offer = HotelOffer(
        provider="liteapi",
        provider_ref={"hotel_id": "same"},
        hotel_name="Hotel 1",
        room_name="Double",
        search_destination="Goa",
        total=Money(amount=70000, currency="INR"),
        quoted_at=datetime.now(UTC),
    )
    variants = options_from_offers(
        [offer, offer.model_copy(update={"room_name": "Suite"})],
        checkin="2026-12-01",
        checkout="2026-12-03",
        cached=False,
    )
    assert len(variants) == 2 and variants[0].id != variants[1].id
    decision = booking.list_decisions(plan)[1]
    decision.options[1].label = "Hotel 1"
    decision.chosen_option_id = decision.options[1].id
    upsert_decision(plan, decision)
    reconcile_selected_lodging(plan)
    assert booking.list_decisions(plan)[1].chosen_option_id == decision.options[1].id
    plan["selected_hotels"].append(
        {"name": "Hotel 1", "checkin": "2026-12-05", "checkout": "2026-12-07", "total": 5000}
    )
    plan["day_wise_itinerary"].append(
        {"day": 5, "date": "2026-12-05", "stops": [{"name": "Hotel 1", "kind": "hotel"}]}
    )
    rows = [r for r in booking.units(plan) if r["category"] == "hotels"]
    assert len(rows) == 2 and len(rows[0]["_targets"]) == 3 and len(rows[1]["_targets"]) == 2


def test_unknown_party_and_outside_dates_cannot_claim_fit():
    plan = make_plan()
    plan["travelers"] = "4 adults"
    assert booking.build_booking_view(plan)["budgets"]["flights"]["status"] == "unverified"
    plan["return_date"] = "2026-12-02"
    with pytest.raises(ValueError, match="outside the trip dates"):
        booking.prepare_change(plan, {"action": "lock", "item_id": "stay-goa"})


def test_actual_replaces_product_facts_and_old_link_but_keeps_intention():
    plan = make_plan()
    plan["selected_hotels"][0].update(
        {"lat": 15, "lng": 74, "booking_url": "https://example.com/old"}
    )
    candidate, _ = booking.prepare_change(
        plan,
        {
            "action": "report",
            "item_id": "stay-goa",
            "actual": {"product": "Another hotel", "provider": "Offline", "amount": 70000},
        },
    )
    raw = candidate["selected_hotels"][0]
    assert all(key not in raw for key in ("lat", "lng", "room_name", "booking_url"))
    row = next(r for r in booking.build_booking_view(candidate)["rows"] if r["id"] == "stay-goa")
    assert row["intended"]["details"]["room_name"] == "Double"
    from tripplanner.decisions.apply import apply_override

    assert not apply_override(candidate, "stay-goa", "hotel-2").ok


def test_booking_email_snapshot_delivery_and_revision_guard(monkeypatch, tmp_path):
    from tests.test_email_export_idempotency import _EmailClient
    from azure.communication.email import EmailClient
    from tripplanner.api_contracts import ExportEmailRequest
    from tripplanner.web import itinerary_email, external_operations

    plan = make_plan()
    plan, _ = booking.prepare_change(
        plan,
        {
            "action": "report",
            "item_id": "stay-goa",
            "actual": {
                "product": "Hotel",
                "provider": "Agent",
                "reference": "private-secret",
                "amount": 70000,
            },
        },
    )
    monkeypatch.setattr(trip_planner, "load_active_trip_dict", lambda: plan)
    monkeypatch.setattr(trip_planner, "active_trip_id", lambda: plan["trip_id"])
    monkeypatch.setattr(external_operations, "_local_path", lambda: tmp_path / "operations.json")
    monkeypatch.setattr(share, "_local_snapshot_dir", lambda: tmp_path / "shares")
    client = _EmailClient()
    monkeypatch.setattr(EmailClient, "from_connection_string", lambda value: client)
    monkeypatch.setenv("AZURE_COMMUNICATION_CONNECTION_STRING", "endpoint=test")
    monkeypatch.setenv("AZURE_COMMUNICATION_EMAIL_SENDER", "sender@example.com")
    req = ExportEmailRequest(
        email="traveler@example.com",
        request_id="booking-snapshot",
        template="booking_intent",
        trip_id=plan["trip_id"],
        updated_at=plan["updated_at"],
    )
    itinerary_email.send_itinerary_email(req, base_url="https://example.com")
    replay = itinerary_email.send_itinerary_email(req, base_url="https://example.com")
    assert replay["replayed"] and len(client.calls) == 1
    message = client.calls[0][0]
    assert message["attachments"][0]["name"] == "booking-intent.pdf"
    assert "Booking intent list" in message["content"]["html"]
    assert "private-secret" not in message["content"]["html"]
    plan["updated_at"] = "newer"
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        itinerary_email.send_itinerary_email(req, base_url="https://example.com")
    assert error.value.status_code == 409 and len(client.calls) == 1
