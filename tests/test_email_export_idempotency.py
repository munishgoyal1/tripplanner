from __future__ import annotations

import smtplib

from azure.communication.email import EmailClient
from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.tools import trip_planner
from tripplanner.web import external_operations, itinerary_export, share


class _Poller:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def result(self) -> dict[str, str]:
        if self.error:
            raise self.error
        return {"status": "Succeeded"}


class _EmailClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[dict, str | None]] = []

    def begin_send(self, message: dict, *, operation_id: str | None = None) -> _Poller:
        self.calls.append((message, operation_id))
        return _Poller(self.error)


def _configure_export(monkeypatch, tmp_path, email_client: _EmailClient) -> TestClient:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(external_operations, "_local_path", lambda: tmp_path / "operations.json")
    monkeypatch.setattr(
        trip_planner,
        "load_active_trip_dict",
        lambda: {"destination": "Goa", "trip_id": "goa-trip"},
    )
    monkeypatch.setattr(trip_planner, "active_trip_id", lambda: "goa-trip")
    monkeypatch.setattr(itinerary_export, "build_export_html", lambda *args, **kwargs: "<p>Goa</p>")
    monkeypatch.setattr(share, "mint_for_active_trip", lambda: "share-token")
    monkeypatch.setattr(
        EmailClient,
        "from_connection_string",
        lambda connection_string: email_client,
    )
    monkeypatch.setenv("AZURE_COMMUNICATION_CONNECTION_STRING", "endpoint=test")
    monkeypatch.setenv("AZURE_COMMUNICATION_EMAIL_SENDER", "sender@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    return TestClient(api.app)


def _payload(request_id: str, *, email: str = "traveler@example.com") -> dict:
    return {
        "user_id": "local",
        "email": email,
        "include_photos": True,
        "include_map_circuit": True,
        "template": "detailed",
        "request_id": request_id,
    }


def test_email_export_replays_without_second_provider_send(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    email_client = _EmailClient()
    client = _configure_export(monkeypatch, tmp_path, email_client)

    first = client.post("/trip/export/email", json=_payload("send-1"))
    replay = client.post("/trip/export/email", json=_payload("send-1"))

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert len(email_client.calls) == 1
    assert email_client.calls[0][1] == external_operations.provider_operation_id("send-1")


def test_email_export_rejects_request_id_reuse_for_different_payload(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    email_client = _EmailClient()
    client = _configure_export(monkeypatch, tmp_path, email_client)

    first = client.post("/trip/export/email", json=_payload("send-1"))
    conflict = client.post(
        "/trip/export/email",
        json=_payload("send-1", email="other@example.com"),
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"] == "idempotency_conflict"
    assert len(email_client.calls) == 1


def test_ambiguous_acs_failure_retries_acs_without_smtp_fallback(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    email_client = _EmailClient(TimeoutError("polling timed out"))
    client = _configure_export(monkeypatch, tmp_path, email_client)
    smtp_calls = 0

    class _SMTP:
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            nonlocal smtp_calls
            smtp_calls += 1

    monkeypatch.setattr(smtplib, "SMTP", _SMTP)

    first = client.post("/trip/export/email", json=_payload("send-uncertain"))
    retry = client.post("/trip/export/email", json=_payload("send-uncertain"))

    assert first.status_code == 503
    assert retry.status_code == 503
    assert first.json()["error"] == "email_delivery_uncertain"
    assert len(email_client.calls) == 2
    assert email_client.calls[0][1] == email_client.calls[1][1]
    assert smtp_calls == 0


def test_new_request_id_allows_new_explicit_send(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    email_client = _EmailClient()
    client = _configure_export(monkeypatch, tmp_path, email_client)

    first = client.post("/trip/export/email", json=_payload("send-1"))
    second = client.post("/trip/export/email", json=_payload("send-2"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(email_client.calls) == 2
    assert email_client.calls[0][1] != email_client.calls[1][1]
