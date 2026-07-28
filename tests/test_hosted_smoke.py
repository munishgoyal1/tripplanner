from __future__ import annotations

import json
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import quote

import scripts.hosted_smoke as hosted_smoke
from scripts.hosted_smoke import Response, SmokeSuite


def _response(
    payload: object, status: int = 200, headers: dict[str, str] | None = None
) -> Response:
    body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
    return Response(status, headers or {}, body)


def test_read_only_suite_validates_hosted_contract(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    base = "https://canary.example.com"
    callback = f"{base}/api/auth/callback/google"

    def fake_request(url: str, **kwargs) -> Response:  # type: ignore[no-untyped-def]
        if url == f"{base}/":
            return _response('<div id="root"></div>')
        if url.endswith("/api/health"):
            return _response({"status": "ok"})
        if url.endswith("/api/auth/config"):
            return _response({"google": True, "redirect_uri": callback})
        if "/api/auth/login/google" in url:
            location = (
                "https://accounts.google.com/o/oauth2/v2/auth?redirect_uri="
                f"{quote(callback, safe='')}"
            )
            return _response(
                "",
                302,
                {"Location": location, "Set-Cookie": "mg_oauth_state=x; HttpOnly; Secure"},
            )
        if url.endswith("/api/maps/config"):
            return _response({"enabled": True, "key": "browser-key"})
        if url.endswith("/api/auth/me"):
            return _response({"authenticated": False})
        if "/api/trips?" in url:
            return _response({"trips": []})
        if "/api/preferences?" in url:
            return _response({"display_name": ""})
        if "/api/usage?" in url:
            return _response({"user_id": "smoke-canary-readonly"})
        if "/api/trip/view?" in url:
            return _response({})
        raise AssertionError(url)

    monkeypatch.setattr(hosted_smoke, "_request", fake_request)
    assert SmokeSuite(f"{base}/", "canary").run() is True


def test_suite_fails_for_cross_environment_oauth_callback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        hosted_smoke,
        "_request",
        lambda *args, **kwargs: _response(
            {"google": True, "redirect_uri": "http://localhost:5173/api/auth/callback/google"}
        ),
    )
    suite = SmokeSuite("https://prod.example.com", "production")
    expected = "https://prod.example.com/api/auth/callback/google"

    def validate_callback() -> None:
        assert suite._get_json("/api/auth/config")["redirect_uri"] == expected

    suite._check("OAuth config", validate_callback)
    assert suite.failures == ["OAuth config"]


def test_base_url_is_normalized() -> None:
    suite = SmokeSuite("https://canary.example.com/", "canary")
    assert suite.base_url == "https://canary.example.com"


def test_request_retries_transient_gateway_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class SuccessfulResponse:
        status = 200
        headers = Message()

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args) -> None:  # type: ignore[no-untyped-def]
            return None

        def read(self) -> bytes:
            return b'{}'

    class RetryOpener:
        calls = 0

        def open(self, request, timeout):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls < 3:
                raise HTTPError(request.full_url, 503, "cold start", Message(), None)
            return SuccessfulResponse()

    opener = RetryOpener()
    monkeypatch.setattr(hosted_smoke, "build_opener", lambda *args: opener)
    monkeypatch.setattr(hosted_smoke.time, "sleep", lambda seconds: None)

    response = hosted_smoke._request("https://canary.example.com/api/health")

    assert response.status == 200
    assert opener.calls == 3
