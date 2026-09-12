"""Warming is the one read-triggered path still allowed to spend.

Opening the planner replays ``/trip/view`` and ``/trip/workspace``, and both
schedule a background warm. Before the revision guard covered it,
``warm_view_items`` re-prefetched up to forty places on every one of those
requests -- exactly the work the cache exists to avoid, repeated on the request
that should have been free.
"""

from __future__ import annotations

from typing import Any

import pytest

from tripplanner.web import place_guide, places_cache


@pytest.fixture(autouse=True)
def _fresh_warm_state(monkeypatch: pytest.MonkeyPatch):
    place_guide.reset_warm_state()
    monkeypatch.setattr(places_cache, "is_configured", lambda: True)
    yield
    place_guide.reset_warm_state()


def _trip(updated_at: str) -> dict[str, Any]:
    return {
        "trip_id": "kashmir-1",
        "updated_at": updated_at,
        "destination": "Kashmir",
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Dal Lake", "kind": "attraction"}]}
        ],
    }


def test_view_item_warming_runs_once_per_trip_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    prefetched: list[list[str]] = []
    monkeypatch.setattr(
        places_cache,
        "prefetch",
        lambda names, _city, **_kwargs: prefetched.append(list(names)),
    )

    place_guide.warm_view_items(_trip("2026-09-12T05:00:00Z"))
    place_guide.warm_view_items(_trip("2026-09-12T05:00:00Z"))
    place_guide.warm_view_items(_trip("2026-09-12T05:00:00Z"))

    assert len(prefetched) == 1


def test_a_changed_trip_is_warmed_again(monkeypatch: pytest.MonkeyPatch) -> None:
    prefetched: list[list[str]] = []
    monkeypatch.setattr(
        places_cache,
        "prefetch",
        lambda names, _city, **_kwargs: prefetched.append(list(names)),
    )

    place_guide.warm_view_items(_trip("2026-09-12T05:00:00Z"))
    place_guide.warm_view_items(_trip("2026-09-12T06:30:00Z"))

    assert len(prefetched) == 2


def test_the_two_warms_claim_revisions_independently(monkeypatch: pytest.MonkeyPatch) -> None:
    """They warm different datasets, so one must not consume the other's claim."""
    monkeypatch.setattr(places_cache, "prefetch", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(place_guide, "discovery_pool", lambda _trip: [])

    trip = _trip("2026-09-12T05:00:00Z")
    assert place_guide._claim_warm("view_items", trip) is True
    assert place_guide._claim_warm("guide", trip) is True
    assert place_guide._claim_warm("view_items", trip) is False
    assert place_guide._claim_warm("guide", trip) is False


def test_a_warm_that_fails_is_not_retried_by_the_next_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The revision is claimed before the work runs, so a failing warm cannot
    turn every subsequent page load back into a paid one."""
    attempts: list[str] = []

    def exploding_prefetch(*_args: Any, **_kwargs: Any) -> None:
        attempts.append("tried")
        raise RuntimeError("provider down")

    monkeypatch.setattr(places_cache, "prefetch", exploding_prefetch)

    trip = _trip("2026-09-12T05:00:00Z")
    with pytest.raises(RuntimeError):
        place_guide.warm_view_items(trip)
    place_guide.warm_view_items(trip)

    assert attempts == ["tried"]
