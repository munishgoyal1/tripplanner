from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tripplanner import api
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
