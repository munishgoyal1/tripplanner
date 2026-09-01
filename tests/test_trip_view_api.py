from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tripplanner import api, places_budget
from tripplanner.trip_repository import TripConflictError
from tripplanner.web import trip_operations


def test_trip_view_preserves_exact_itinerary_occurrence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_focus = None

    def fake_build_view(focus):
        nonlocal captured_focus
        captured_focus = focus
        return {"focus": focus}

    monkeypatch.setattr(trip_operations, "build_view", fake_build_view)

    response = TestClient(api.app).get(
        "/trip/view",
        params={
            "focus_kind": "attraction",
            "focus_name": "Jag Mandir",
            "focus_day": 2,
            "focus_stop": 1,
        },
    )

    assert response.status_code == 200
    assert captured_focus == {
        "kind": "attraction",
        "name": "Jag Mandir",
        "day": 2,
        "stop": 1,
    }


def test_http_request_authorizes_user_provider_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    def fake_build_view(_focus):
        budget = places_budget.current_budget()
        return {"purpose": budget.purpose if budget else None}

    monkeypatch.setattr(trip_operations, "build_view", fake_build_view)

    response = TestClient(api.app).get("/trip/view")

    assert response.json()["purpose"] == "user_interaction"


def test_corpus_header_selects_budgeted_provider_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    def fake_build_view(_focus):
        budget = places_budget.current_budget()
        return {"purpose": budget.purpose if budget else None}

    monkeypatch.setattr(trip_operations, "build_view", fake_build_view)

    response = TestClient(api.app).get(
        "/trip/view",
        headers={"X-Tripplanner-Paid-Provider-Purpose": "corpus_generation"},
    )

    assert response.json()["purpose"] == "corpus_generation"


def test_test_request_does_not_receive_paid_provider_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build_view(_focus):
        return {"authorized": places_budget.paid_provider_authorized()}

    monkeypatch.setattr(trip_operations, "build_view", fake_build_view)

    response = TestClient(api.app).get("/trip/view")

    assert response.json()["authorized"] is False


def test_budget_what_if_is_generated_only_by_explicit_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_build_budget_what_if():
        nonlocal calls
        calls += 1
        return {"generated_on_demand": True, "proposals": []}

    monkeypatch.setattr(trip_operations, "build_budget_what_if", fake_build_budget_what_if)
    client = TestClient(api.app)

    assert calls == 0
    response = client.post("/trip/budget/what-if")

    assert response.status_code == 200
    assert response.json()["generated_on_demand"] is True
    assert calls == 1


def test_trip_write_conflict_returns_http_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def conflict(*_args, **_kwargs):
        raise TripConflictError("Trip 'goa' changed from revision 2 to 3")

    monkeypatch.setattr(trip_operations, "select", conflict)

    response = TestClient(api.app).post(
        "/trip/select",
        json={"kind": "attraction", "name": "Beach", "user_id": "local"},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "trip_conflict"
