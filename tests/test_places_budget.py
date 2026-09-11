from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from tripplanner import places_budget


def test_authorized_scope_permits_every_paid_call() -> None:
    """The scope is an authorization gate, not a budget.

    Per-scope call caps were retired with the other proxy limits: they throttled
    quality on legitimately complex trips, and spend is now bounded by the
    measured INR ceiling in cost_ledger.py. What must still hold is that an
    authorized scope permits the calls a good itinerary needs.
    """
    with places_budget.places_budget_scope("user_interaction") as budget:
        with ThreadPoolExecutor(max_workers=8) as executor:
            allowed = list(executor.map(lambda _index: budget.consume("text_search"), range(8)))

    assert allowed == [True] * 8


def test_scope_counts_calls_for_telemetry() -> None:
    with places_budget.places_budget_scope("user_interaction") as budget:
        budget.consume("text_search")
        budget.consume("text_search")
        budget.consume("photo")

    assert budget.used == {"text_search": 2, "photo": 1}


def test_unscoped_request_is_denied() -> None:
    """The gate that matters: nothing outside a named scope may spend money.

    Reusable view builders, audits, tests and background warming cannot create
    a scope, so none of them can make a paid Places call.
    """
    assert places_budget.consume("text_search") is False
    assert places_budget.paid_provider_authorized() is False


def test_worker_can_share_active_budget() -> None:
    with places_budget.places_budget_scope("user_interaction"):
        budget = places_budget.current_budget()

        def consume_in_worker(_index: int) -> bool:
            with places_budget.use_budget(budget):
                return places_budget.consume("photo")

        with ThreadPoolExecutor(max_workers=2) as executor:
            allowed = list(executor.map(consume_in_worker, range(2)))

    assert allowed == [True, True]
    assert budget is not None and budget.used["photo"] == 2


def test_worker_without_the_budget_is_still_denied() -> None:
    with places_budget.places_budget_scope("user_interaction"):
        budget = places_budget.current_budget()
    assert budget is not None

    # Outside the scope, sharing nothing, the call is unauthorized.
    assert places_budget.consume("photo") is False
