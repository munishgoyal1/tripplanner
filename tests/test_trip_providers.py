"""Ownership-focused tests split from the former tests/test_trip.py module."""

# ruff: noqa: E501, F403, F405, I001

from tests.support.trip import *  # noqa: F403

class TestFlightHelpers:
    def test_resolve_iata_city_name(self):
        assert resolve_iata("Delhi") == "DEL"
        assert resolve_iata("mumbai") == "BOM"
        assert resolve_iata("Goa") == "GOI"

    def test_resolve_iata_already_code(self):
        assert resolve_iata("DEL") == "DEL"
        assert resolve_iata("bom") == "BOM"

    def test_resolve_iata_international(self):
        assert resolve_iata("Dubai") == "DXB"
        assert resolve_iata("Singapore") == "SIN"
        assert resolve_iata("London") == "LHR"

class TestActivityHelpers:
    def test_known_city_coords(self):
        coords = _get_coords("Goa")
        assert coords is not None
        lat, lon = coords
        assert 15 < lat < 16
        assert 73 < lon < 74

    def test_unknown_city_coords(self):
        assert _get_coords("Narnia") is None

class TestGooglePlacesHelpers:
    def test_format_place_full(self):
        out = _format_place({
            "id": "abc",
            "displayName": {"text": "Taj Mahal Palace"},
            "formattedAddress": "Mumbai, India",
            "rating": 4.6,
            "userRatingCount": 1234,
            "priceLevel": "PRICE_LEVEL_VERY_EXPENSIVE",
            "types": ["lodging", "hotel", "establishment"],
            "websiteUri": "https://taj.com",
            "internationalPhoneNumber": "+91 22 6665 3366",
            "currentOpeningHours": {"openNow": True},
            "location": {"latitude": 18.9217, "longitude": 72.8332},
            "photos": [{"name": "places/abc/photos/one"}],
        })
        assert out["name"] == "Taj Mahal Palace"
        assert out["rating"] == 4.6
        assert out["place_id"] == "abc"
        assert out["lat"] == 18.9217
        assert out["photo_refs"] == ["places/abc/photos/one"]
        assert len(out["types"]) == 3

    def test_format_place_minimal(self):
        out = _format_place({})
        assert out["name"] == ""
        assert out["rating"] is None
        assert out["types"] == []

    def test_format_reviews_truncates(self):
        reviews = [
            {
                "rating": 5,
                "text": {"text": "x" * 500},
                "authorAttribution": {"displayName": "Alice"},
                "relativeTimeDescription": "1 month ago",
            }
        ] * 10
        out = _format_reviews(reviews, limit=3)
        assert len(out) == 3
        assert len(out[0]["text"]) == 300

    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from tripplanner import config
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type(
                "S",
                (),
                {"enable_google_places": False, "google_places_api_key": "copied-key"},
            )(),
        )
        # Re-bind in module under test
        monkeypatch.setattr(google_places, "get_settings", config.get_settings)
        assert not google_places.is_configured()
        result = search_places_with_reviews.invoke({"query": "test", "city": "Goa"})
        assert "disabled or not configured" in result.lower()
        result = nearby_restaurants.invoke({"city": "Goa"})
        assert "disabled or not configured" in result.lower()

    def test_configured_requires_flag_and_key(self, monkeypatch):
        monkeypatch.setattr(
            google_places,
            "get_settings",
            lambda: type(
                "S",
                (),
                {"enable_google_places": True, "google_places_api_key": ""},
            )(),
        )
        assert not google_places.is_configured()

        monkeypatch.setattr(
            google_places,
            "get_settings",
            lambda: type(
                "S",
                (),
                {"enable_google_places": True, "google_places_api_key": "test-key"},
            )(),
        )
        assert google_places.is_configured()

def test_hotel_search_uses_google_fallback_when_amadeus_unconfigured(monkeypatch):
    from tripplanner.tools import hotel_search

    class FakeGoogleSearch:
        @staticmethod
        def invoke(args):
            return json.dumps([{"name": "Grounded Hotel", "rating": 4.7, **args}])

    # No live provider configured, so best-effort falls through to Amadeus then Google.
    monkeypatch.setattr(hotel_search, "get_hotel_providers", lambda: [])
    monkeypatch.setattr(hotel_search.amadeus_client, "is_configured", lambda: False)
    monkeypatch.setattr(hotel_search, "search_places_with_reviews", FakeGoogleSearch())

    result = hotel_search.search_hotels.invoke(
        {"city": "Paris", "checkin": "2026-09-01", "checkout": "2026-09-05"}
    )

    assert "Grounded Hotel" in result
    assert '"city": "Paris"' in result

class TestWebSearchHelpers:
    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from tripplanner import config
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type("S", (), {"tavily_api_key": ""})(),
        )
        monkeypatch.setattr(web_search, "get_settings", config.get_settings)
        assert not web_search.is_configured()
        result = web_search_tool.invoke({"query": "best beaches in Goa"})
        assert "not configured" in result.lower()

class TestDuffelHelpers:
    def test_format_duration_basic(self):
        assert _format_duration("PT5H30M") == "5h 30m"
        assert _format_duration("PT2H") == "2h"
        assert _format_duration("PT45M") == "45m"
        assert _format_duration("") == ""

    def test_format_segment_minimal(self):
        seg = {
            "marketing_carrier": {"iata_code": "AI"},
            "marketing_carrier_flight_number": "101",
            "origin": {"iata_code": "DEL"},
            "destination": {"iata_code": "BOM"},
            "departing_at": "2026-03-01T09:30:00",
            "arriving_at": "2026-03-01T11:45:00",
            "duration": "PT2H15M",
        }
        line = _format_segment(seg)
        assert "AI101" in line
        assert "DEL 09:30" in line
        assert "BOM 11:45" in line
        assert "2h 15m" in line

    def test_format_offers_empty(self):
        assert "No Duffel offers" in _format_offers([], 5)

    def test_format_offers_sorts_by_price(self):
        offers = [
            {
                "total_amount": "500.00",
                "total_currency": "INR",
                "owner": {"name": "Expensive Air"},
                "slices": [
                    {
                        "duration": "PT2H",
                        "segments": [
                            {
                                "marketing_carrier": {"iata_code": "XX"},
                                "marketing_carrier_flight_number": "999",
                                "origin": {"iata_code": "DEL"},
                                "destination": {"iata_code": "BOM"},
                                "departing_at": "2026-03-01T08:00:00",
                                "arriving_at": "2026-03-01T10:00:00",
                                "duration": "PT2H",
                            }
                        ],
                    }
                ],
            },
            {
                "total_amount": "100.00",
                "total_currency": "INR",
                "owner": {"name": "Cheap Air"},
                "slices": [
                    {
                        "duration": "PT2H",
                        "segments": [
                            {
                                "marketing_carrier": {"iata_code": "YY"},
                                "marketing_carrier_flight_number": "1",
                                "origin": {"iata_code": "DEL"},
                                "destination": {"iata_code": "BOM"},
                                "departing_at": "2026-03-01T09:00:00",
                                "arriving_at": "2026-03-01T11:00:00",
                                "duration": "PT2H",
                            }
                        ],
                    }
                ],
            },
        ]
        out = _format_offers(offers, 5)
        cheap_pos = out.find("Cheap Air")
        exp_pos = out.find("Expensive Air")
        assert 0 <= cheap_pos < exp_pos

    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from tripplanner import config
        # No live provider configured, so the friendly Duffel setup message surfaces.
        monkeypatch.setattr(duffel_flights, "get_flight_provider", lambda: None)
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type("S", (), {"duffel_api_key": ""})(),
        )
        monkeypatch.setattr(duffel_flights, "get_settings", config.get_settings)
        assert not duffel_flights.is_configured()
        result = search_flights_duffel.invoke({
            "origin": "Delhi",
            "destination": "Mumbai",
            "departure_date": "2026-03-01",
        })
        assert "not configured" in result.lower()
        assert "duffel.com/sign-up" in result.lower()
