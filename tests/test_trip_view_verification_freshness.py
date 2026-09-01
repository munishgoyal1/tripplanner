"""Trip-view evidence, verification, and freshness tests."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.trip_view import SAMPLE_TRIP
from tripplanner.web import trip_view

pytestmark = pytest.mark.usefixtures("_no_network")


def test_overview_exposes_effort_and_price_recheck_intelligence() -> None:
    trip = {
        **SAMPLE_TRIP,
        "status": "finalized",
        "selected_hotels": [
            {
                "name": "Taj Exotica Resort",
                "price": 12000,
                "booking_status": "planned",
            }
        ],
        "price_checks": [
            {
                "kind": "lodging",
                "provider": "liteapi",
                "checked_at": "2026-01-01T00:00:00+00:00",
                "expires_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        "day_wise_itinerary": [
            {
                "day": 1,
                "date": "2026-01-10",
                "stops": [
                    {
                        "name": "Fort Aguada",
                        "kind": "attraction",
                        "time": "12:00",
                        "duration_min": 180,
                    }
                ],
            }
        ],
        "weather": {
            "source": "forecast",
            "days": [
                {
                    "date": "2026-01-10",
                    "high_c": 36,
                    "precip_probability_pct": 80,
                }
            ],
        },
    }

    overview = trip_view.build_view(trip, None)["overview"]

    assert any("36°C" in note for note in overview["effort_notes"])
    assert overview["price_rechecks"] == [
        {
            "kind": "lodging",
            "provider": "liteapi",
            "reason": "finalized but unbooked quote expired",
        }
    ]


def test_budget_headroom_is_verified_only_with_complete_live_evidence() -> None:
    evidence = {
        "complete": True,
        "coverage_pct": 100,
        "priced_total": 8000,
        "all_in_total": 8200,
        "all_in_coverage_pct": 100,
        "required_unknown": [],
    }
    budget = trip_view.build_budget(
        {"currency": "USD", "total_cost": 8000, "budget": 10000},
        cost_evidence=evidence,
    )

    assert budget is not None
    assert budget["estimated"] is False
    assert budget["evidence_coverage_pct"] == 100
    assert budget["verified_spent"] == 8000
    assert budget["all_in_spent"] == 8200
    assert budget["all_in_coverage_pct"] == 100
    assert budget["required_unknown"] == []


def test_budget_names_unknown_mandatory_costs() -> None:
    budget = trip_view.build_budget(
        {"currency": "USD", "total_cost": 8000},
        cost_evidence={
            "complete": False,
            "coverage_pct": 100,
            "priced_total": 8000,
            "all_in_total": None,
            "all_in_coverage_pct": 0,
            "required_unknown": ["baggage charges", "taxes and mandatory carrier fees"],
        },
    )

    assert budget is not None
    assert budget["estimated"] is True
    assert budget["verified_spent"] == 8000
    assert budget["all_in_spent"] is None
    assert budget["required_unknown"] == [
        "baggage charges",
        "taxes and mandatory carrier fees",
    ]


def test_structured_target_uses_published_fx_provenance(monkeypatch) -> None:
    from datetime import UTC, datetime

    from tripplanner.providers import fx

    # Seeded relative to now: a fixed timestamp ages past the rate TTL and the
    # test then silently reaches the live rate service.
    fetched_at = datetime.now(UTC)
    fx._cache.set(
        "EUR",
        fx.RateTable(
            base="EUR",
            rates={"USD": 1.2},
            fetched_at=fetched_at,
            rate_date="2026-08-10",
        ).to_payload(),
    )
    budget = trip_view.build_budget(
        {
            "currency": "USD",
            "total_cost": 6000,
            "budget": {"amount": 10000, "currency": "EUR", "owner": "user"},
        }
    )

    assert budget is not None
    assert budget["target"] == 12000
    assert budget["target_fx"]["rate"] == 1.2
    assert budget["target_fx"]["rate_date"] == "2026-08-10"


def test_map_view_rejects_coordinates_from_a_mismatched_provider_place(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {
            "place_id": "padmanabhapuram-palace",
            "name": "Padmanabhapuram Palace",
            "address": "Thuckalay, Tamil Nadu",
            "lat": 8.2507,
            "lng": 77.3260,
        },
    )
    trip = {
        "destination": "Kanyakumari",
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [{"name": "Kanyakumari Beach", "kind": "attraction"}],
        }],
    }

    view = trip_view.build_map_view(trip)

    assert view["pins"] == []


def test_map_view_leaves_partial_flight_between_stays_unverified(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Origin Hotel": (13.05, 77.59),
        "Bangalore Airport": (13.1986, 77.7066),
        "Destination Hotel": (24.577, 73.683),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {
            "place_id": f"pid-{name}",
            "name": name,
            "lat": coords.get(name, (None, None))[0],
            "lng": coords.get(name, (None, None))[1],
        },
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [{"name": "Origin Hotel"}, {"name": "Destination Hotel"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Origin Hotel", "kind": "hotel"},
                {"name": "Flight: Bangalore to Udaipur", "kind": "flight"},
                {"name": "Destination Hotel", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    day = view["days"][0]
    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    assert [names_by_id[pin_id] for pin_id in day["pin_ids"]] == [
        "Origin Hotel",
        "Bangalore Airport",
        "Destination Hotel",
    ]
    assert all(leg["mode"] == "Taxi" for leg in day["legs"])
    assert all("intercity" not in leg for leg in day["legs"])


def test_local_route_does_not_invent_unverified_metro_service() -> None:
    route = trip_view._route_stats_for_distance(
        10.0,
        from_name="Trident Udaipur",
        to_name="City Palace Udaipur",
    )

    assert route["mode"] == "Taxi"
    assert route["detail"] == "Take a taxi from Trident Udaipur to City Palace Udaipur."


def test_arrival_hotel_time_requires_airport_transfer_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trip_view, "_place_coords", lambda name, destination: None)
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {
                    "name": "Flight: Bangalore to Udaipur",
                    "kind": "flight",
                    "time": "08:00",
                    "arrival_time": "11:10",
                    "duration_min": 70,
                },
                {"name": "Trident Udaipur", "kind": "hotel"},
            ],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    hotel = itinerary["days"][0]["stops"][-1]
    assert hotel["time"] == ""
    assert "time_estimated" not in hotel


def test_itinerary_enriches_stop_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_summary(name: str, city: str, **_kw: Any) -> dict[str, Any] | None:
        lower = str(name).strip().lower()
        if lower == "taj exotica resort":
            return {
                "name": name,
                "editorial_summary": "Beachfront luxury stay with easy access to South Goa.",
                "price_level": "PRICE_LEVEL_EXPENSIVE",
                "open_now": True,
                "weekday_descriptions": ["Monday: Open 24 hours"],
            }
        if lower == "dudhsagar falls trek":
            return {
                "name": name,
                "editorial_summary": "Iconic waterfall trail with scenic viewpoints.",
                "price_level": "PRICE_LEVEL_MODERATE",
                "open_now": False,
                "weekday_descriptions": ["Monday: Closed", "Tuesday: 8:00 AM-5:00 PM"],
            }
        return {"name": name}

    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_summary)

    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {
                "day": 1,
                "date": "2026-01-12",  # Monday
                "stops": [
                    {"name": "Taj Exotica Resort", "kind": "hotel", "booked": True},
                    {"name": "Dudhsagar Falls Trek", "kind": "attraction", "time": "14:00"},
                ],
            }
        ],
    }

    it = trip_view.build_itinerary(trip)
    hotel = it["days"][0]["stops"][0]
    trek = it["days"][0]["stops"][1]

    assert hotel["cost_display"] == "\u20b912,000"
    assert hotel["opening_hours"].startswith("Monday:")
    assert hotel["insight"]
    assert hotel["duration_min"] is None

    assert trek["cost_display"] == "Mid-range"
    assert trek["opening_hours"].startswith("Monday:")
    assert trek["concern"] == "Closed on Mondays; move this to another day."
    assert trek["insight"]

    assert it["days"][0]["reachability"]
