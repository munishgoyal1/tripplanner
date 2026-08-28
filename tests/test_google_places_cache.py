"""Paid Google Places tool responses are reusable outside the graph wrapper."""

from __future__ import annotations

from types import SimpleNamespace

from tripplanner.places_budget import places_budget_scope
from tripplanner.tools import google_places


def test_search_reuses_cached_response_before_consuming_budget(monkeypatch) -> None:
    google_places._SEARCH_CACHE.clear()
    calls = []
    payload = {
        "places": [
            {
                "id": "louvre",
                "displayName": {"text": "Louvre"},
                "location": {"latitude": 48.8606, "longitude": 2.3376},
            }
        ]
    }
    monkeypatch.setattr(google_places, "is_configured", lambda: True)
    monkeypatch.setattr(
        google_places,
        "get_settings",
        lambda: SimpleNamespace(
            google_places_api_key="test-key",
            google_places_search_cache_ttl_sec=604800,
        ),
    )
    monkeypatch.setattr(google_places, "_remember_places", lambda *_args: None)

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    def fake_post(*args, **kwargs):
        calls.append(args[0])
        return Response()

    monkeypatch.setattr(google_places.http_client, "post", fake_post)

    with places_budget_scope("user_interaction") as budget:
        first = google_places.search_places_with_reviews.invoke(
            {"query": "museum", "city": "Paris"}
        )
        second = google_places.search_places_with_reviews.invoke(
            {"query": "museum", "city": "Paris"}
        )

    assert first == second
    assert len(calls) == 1
    assert budget.used == {"text_search": 1}
