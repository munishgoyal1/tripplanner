from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from tripplanner import places_budget


def test_budget_limits_parallel_paid_calls(monkeypatch):
    settings = places_budget.get_settings()
    monkeypatch.setattr(settings, "google_places_max_text_searches_per_trip", 3)
    monkeypatch.setattr(settings, "google_places_max_review_details_per_trip", 1)
    monkeypatch.setattr(settings, "google_places_max_photos_per_trip", 3)

    with places_budget.places_budget_scope("user_interaction") as budget:
        with ThreadPoolExecutor(max_workers=8) as executor:
            allowed = list(
                executor.map(lambda _index: budget.consume("text_search"), range(8))
            )

    assert allowed.count(True) == 3
    assert allowed.count(False) == 5


def test_unscoped_request_is_denied() -> None:
    assert places_budget.consume("text_search") is False


def test_worker_can_share_active_budget(monkeypatch):
    settings = places_budget.get_settings()
    monkeypatch.setattr(settings, "google_places_max_photos_per_trip", 1)

    with places_budget.places_budget_scope("user_interaction"):
        budget = places_budget.current_budget()

        def consume_in_worker(_index: int) -> bool:
            with places_budget.use_budget(budget):
                return places_budget.consume("photo")

        with ThreadPoolExecutor(max_workers=2) as executor:
            allowed = list(executor.map(consume_in_worker, range(2)))

    assert allowed.count(True) == 1
