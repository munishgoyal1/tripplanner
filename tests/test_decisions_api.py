"""The override endpoints: applying, undoing, stale writes and the feature flag."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.config import get_settings
from tripplanner.decisions.models import (
    Decision,
    DecisionScope,
    FareBasis,
    Option,
    Price,
    Rule,
    TransportMode,
)
from tripplanner.decisions.store import upsert_decision
from tripplanner.tools import trip_planner
from tripplanner.web import trip_view

DECISION_ID = "dec_transport_mode_lisbon_porto"
SECOND_DECISION_ID = "dec_transport_mode_porto_coimbra"


def _option(
    option_id: str, mode: TransportMode, label: str, amount: float, duration: int
) -> Option:
    return Option(
        id=option_id,
        mode=mode,
        label=label,
        price=Price(amount=amount, currency="EUR", basis=FareBasis.PER_PARTY),
        duration_min=duration,
        door_to_door_min=duration + 120,
    )


def _plan() -> dict:
    plan = {
        "trip_id": "t1",
        "destination": "Portugal",
        "travelers": "2 adults",
        "currency": "EUR",
        "total_cost": 1000.0,
        "updated_at": "2026-05-01T10:00:00",
        "day_wise_itinerary": [
            {
                "day": 2,
                "stops": [
                    {
                        "name": "Train: Lisbon to Porto",
                        "kind": "transport",
                        "time": "09:00",
                        "duration_min": 165,
                        "price": 120.0,
                    }
                ],
            }
            ,
            {
                "day": 3,
                "stops": [
                    {
                        "name": "Train: Porto to Coimbra",
                        "kind": "transport",
                        "time": "09:00",
                        "duration_min": 165,
                        "price": 120.0,
                    }
                ],
            },
        ],
    }
    upsert_decision(
        plan,
        Decision(
            id=DECISION_ID,
            created_at=datetime.now(UTC),
            scope=DecisionScope(day=2, from_place="Lisbon", to_place="Porto"),
            subject="Lisbon to Porto",
            rule=Rule(code="door_to_door_time", text="Fastest door to door."),
            chosen_option_id="opt_train",
            options=[
                _option("opt_train", TransportMode.TRAIN, "Train", 120.0, 165),
                _option("opt_air", TransportMode.FLIGHT, "Flight", 286.0, 60),
            ],
        ),
    )
    upsert_decision(
        plan,
        Decision(
            id=SECOND_DECISION_ID,
            created_at=datetime.now(UTC),
            scope=DecisionScope(day=3, from_place="Porto", to_place="Coimbra"),
            subject="Porto to Coimbra",
            rule=Rule(code="door_to_door_time", text="Fastest door to door."),
            chosen_option_id="opt_train",
            options=[
                _option("opt_train", TransportMode.TRAIN, "Train", 120.0, 165),
                _option("opt_air", TransportMode.FLIGHT, "Flight", 286.0, 60),
            ],
        ),
    )
    return plan


@pytest.fixture
def client(monkeypatch) -> TestClient:  # type: ignore[no-untyped-def]
    plan = _plan()
    monkeypatch.setattr(trip_planner, "_load_active_trip", lambda: plan)
    monkeypatch.setattr(trip_planner, "load_active_trip_dict", lambda: plan)
    monkeypatch.setattr(trip_planner, "_save_active_trip", lambda saved: plan.update(saved))
    monkeypatch.setattr(trip_view, "build_view", lambda p, focus: {"has_trip": True})
    monkeypatch.setattr(trip_view, "build_itinerary", lambda p: {"days": []})
    get_settings.cache_clear()
    monkeypatch.delenv("DECISIONS_UI_ENABLED", raising=False)
    client = TestClient(api.app)
    client.plan = plan  # type: ignore[attr-defined]
    yield client
    get_settings.cache_clear()


def test_override_returns_the_new_total_and_the_trip_in_one_call(client: TestClient) -> None:
    response = client.post(
        f"/trip/decisions/{DECISION_ID}/override",
        json={"option_id": "opt_air", "user_id": "local"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["option_id"] == "opt_air"
    assert body["total_cost"] == pytest.approx(1166.0)
    assert body["delta"] == pytest.approx(166.0)
    assert body["view"] == {"has_trip": True}
    assert body["itinerary"] == {"days": []}


def test_restore_puts_the_agents_choice_back(client: TestClient) -> None:
    client.post(
        f"/trip/decisions/{DECISION_ID}/override",
        json={"option_id": "opt_air", "user_id": "local"},
    )
    response = client.delete(f"/trip/decisions/{DECISION_ID}/override")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["total_cost"] == pytest.approx(1000.0)
    assert client.plan["day_wise_itinerary"][0]["stops"][0]["kind"] == "transport"  # type: ignore[attr-defined]


def test_a_stale_write_is_refused_with_the_current_trip(client: TestClient) -> None:
    response = client.post(
        f"/trip/decisions/{DECISION_ID}/override",
        json={"option_id": "opt_air", "updated_at": "2026-01-01T00:00:00"},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["ok"] is False
    assert body["stale"] is True
    assert body["view"] == {"has_trip": True}
    assert client.plan["total_cost"] == pytest.approx(1000.0)  # type: ignore[attr-defined]


def test_a_matching_revision_is_accepted(client: TestClient) -> None:
    response = client.post(
        f"/trip/decisions/{DECISION_ID}/override",
        json={"option_id": "opt_air", "updated_at": "2026-05-01T10:00:00"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_batch_override_commits_all_changes_and_returns_synchronized_views(
    client: TestClient,
) -> None:
    response = client.post(
        "/trip/decisions/overrides",
        json={
            "changes": [
                {"decision_id": DECISION_ID, "option_id": "opt_air"},
                {"decision_id": SECOND_DECISION_ID, "option_id": "opt_air"},
            ],
            "updated_at": "2026-05-01T10:00:00",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert len(body["results"]) == 2
    assert body["total_cost"] == pytest.approx(1332.0)
    assert body["view"] == {"has_trip": True}
    assert body["itinerary"] == {"days": []}
    assert client.plan["total_cost"] == pytest.approx(1332.0)  # type: ignore[attr-defined]


def test_batch_override_is_atomic_when_one_change_is_invalid(client: TestClient) -> None:
    response = client.post(
        "/trip/decisions/overrides",
        json={
            "changes": [
                {"decision_id": DECISION_ID, "option_id": "opt_air"},
                {"decision_id": SECOND_DECISION_ID, "option_id": "missing"},
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["failed_change"] == {
        "decision_id": SECOND_DECISION_ID,
        "option_id": "missing",
    }
    assert client.plan["total_cost"] == pytest.approx(1000.0)  # type: ignore[attr-defined]
    assert client.plan["decisions"][0]["chosen_option_id"] == "opt_train"  # type: ignore[attr-defined]


def test_batch_override_rejects_a_stale_revision_without_partial_changes(
    client: TestClient,
) -> None:
    response = client.post(
        "/trip/decisions/overrides",
        json={
            "changes": [{"decision_id": DECISION_ID, "option_id": "opt_air"}],
            "updated_at": "2026-01-01T00:00:00",
        },
    )

    assert response.status_code == 409
    assert response.json()["stale"] is True
    assert response.json()["results"] == []
    assert client.plan["total_cost"] == pytest.approx(1000.0)  # type: ignore[attr-defined]


def test_unknown_decision_is_a_plain_refusal_not_a_crash(client: TestClient) -> None:
    response = client.post(
        "/trip/decisions/dec_nope/override", json={"option_id": "opt_air"}
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_the_flag_off_hides_the_endpoints(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DECISIONS_UI_ENABLED", "0")
    get_settings.cache_clear()

    response = client.post(
        f"/trip/decisions/{DECISION_ID}/override", json={"option_id": "opt_air"}
    )

    assert response.status_code == 404
    assert client.plan["total_cost"] == pytest.approx(1000.0)  # type: ignore[attr-defined]
