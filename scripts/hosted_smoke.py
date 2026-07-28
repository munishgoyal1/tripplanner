"""Smoke-test a deployed tripplanner environment through its public HTTP API."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@dataclass
class Response:
    status: int
    headers: Any
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class _AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.paths.append(str(values["src"]))
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.paths.append(str(values["href"]))


def _request(url: str, *, data: dict[str, Any] | None = None, follow: bool = True) -> Response:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    opener = build_opener() if follow else build_opener(_NoRedirect())
    for attempt in range(1, 4):
        try:
            with opener.open(request, timeout=45) as response:
                return Response(response.status, response.headers, response.read())
        except HTTPError as error:
            if error.code in {502, 503, 504} and attempt < 3:
                time.sleep(attempt * 2)
                continue
            return Response(error.code, error.headers, error.read())
        except (TimeoutError, URLError):
            if attempt == 3:
                raise
            time.sleep(attempt * 2)
    raise AssertionError("unreachable")


class SmokeSuite:
    def __init__(self, base_url: str, environment: str, deep: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.environment = environment
        self.deep = deep
        self.failures: list[str] = []

    def _check(self, name: str, check) -> None:  # type: ignore[no-untyped-def]
        try:
            detail = check() or "ok"
            print(f"  [PASS] {name:24} {detail}")
        except Exception as error:
            self.failures.append(name)
            print(f"  [FAIL] {name:24} {type(error).__name__}: {error}")

    def _get_json(self, path: str) -> Any:
        response = _request(f"{self.base_url}{path}")
        assert response.status == 200, f"HTTP {response.status}"
        return response.json()

    def run(self) -> bool:
        print(f"Hosted smoke tests: {self.environment} ({self.base_url})")
        smoke_user = f"smoke-{self.environment}-readonly"
        expected_callback = f"{self.base_url}/api/auth/callback/google"

        def spa() -> str:
            response = _request(f"{self.base_url}/")
            text = response.body.decode("utf-8", errors="replace")
            assert response.status == 200 and '<div id="root">' in text, "SPA root not served"
            return "React shell served"

        def spa_assets() -> str:
            index = _request(f"{self.base_url}/")
            parser = _AssetParser()
            parser.feed(index.body.decode("utf-8", errors="replace"))
            assert parser.paths, "SPA references no scripts or stylesheets"
            for path in parser.paths:
                response = _request(urljoin(f"{self.base_url}/", path))
                assert response.status == 200 and response.body, f"missing asset: {path}"
            return f"{len(parser.paths)} referenced assets served"

        def health() -> str:
            assert self._get_json("/api/health") == {"status": "ok"}
            return "status=ok"

        def api_contract() -> str:
            paths = self._get_json("/api/openapi.json").get("paths", {})
            required = {
                "/chat/stream",
                "/trip/view",
                "/trip/map",
                "/trip/itinerary",
                "/trips",
                "/preferences",
                "/auth/login/google",
                "/health",
            }
            missing = sorted(required - set(paths))
            assert not missing, f"missing API routes: {', '.join(missing)}"
            return f"{len(required)} critical routes present"

        def auth_config() -> str:
            payload = self._get_json("/api/auth/config")
            assert payload.get("google") is True, "Google OAuth disabled"
            assert payload.get("redirect_uri") == expected_callback, payload.get("redirect_uri")
            return "callback is environment-owned"

        def auth_redirect() -> str:
            response = _request(
                f"{self.base_url}/api/auth/login/google?redirect=/", follow=False
            )
            assert response.status == 302, f"HTTP {response.status}"
            location = response.headers.get("Location", "")
            parsed = urlparse(location)
            assert parsed.netloc == "accounts.google.com", "not redirected to Google"
            assert parse_qs(parsed.query).get("redirect_uri") == [expected_callback]
            cookie = response.headers.get("Set-Cookie", "")
            assert "mg_oauth_state=" in cookie and "HttpOnly" in cookie and "Secure" in cookie
            return "Google redirect and secure state cookie valid"

        def maps_config() -> str:
            payload = self._get_json("/api/maps/config")
            assert payload.get("enabled") is True and payload.get("key"), "Maps disabled"
            return "enabled"

        def anonymous_auth() -> str:
            assert self._get_json("/api/auth/me") == {"authenticated": False}
            return "anonymous session valid"

        def data_reads() -> str:
            query = urlencode({"user_id": smoke_user})
            trips = self._get_json(f"/api/trips?{query}")
            preferences = self._get_json(f"/api/preferences?{query}")
            usage = self._get_json(f"/api/usage?{query}")
            view = self._get_json(f"/api/trip/view?{query}")
            history = self._get_json(f"/api/chat/history?{query}")
            itinerary = self._get_json(f"/api/trip/itinerary?{query}")
            map_view = self._get_json(f"/api/trip/map?{query}")
            metrics = self._get_json("/api/metrics/tools")
            guest_query = urlencode({"user_id": f"web-{smoke_user}"})
            guest = self._get_json(f"/api/account/guest-data-summary?{guest_query}")
            assert isinstance(trips.get("trips"), list)
            assert isinstance(preferences, dict) and "display_name" in preferences
            assert usage.get("user_id") == smoke_user
            assert isinstance(view, dict)
            assert isinstance(history.get("messages"), list)
            assert isinstance(itinerary, dict) and isinstance(itinerary.get("days"), list)
            assert isinstance(map_view, dict) and isinstance(map_view.get("pins"), list)
            assert isinstance(metrics.get("tools"), dict)
            assert guest == {"has_data": False, "trip_count": 0}
            return "workspace, itinerary, map, metrics and guest reads valid"

        def deep_chat() -> str:
            response = _request(
                f"{self.base_url}/api/chat",
                data={
                    "message": "Reply with exactly PONG. Do not call tools.",
                    "user_id": f"smoke-{self.environment}-deep",
                    "proposal_only": True,
                },
            )
            assert response.status == 200, f"HTTP {response.status}"
            payload = response.json()
            assert "PONG" in str(payload.get("reply", "")).upper(), "unexpected model reply"
            return f"agent={payload.get('agent', 'unknown')}"

        checks = [
            ("SPA", spa),
            ("SPA assets", spa_assets),
            ("Health", health),
            ("API contract", api_contract),
            ("OAuth config", auth_config),
            ("OAuth redirect", auth_redirect),
            ("Maps config", maps_config),
            ("Anonymous auth", anonymous_auth),
            ("Data-plane reads", data_reads),
        ]
        if self.deep:
            checks.append(("Azure OpenAI chat", deep_chat))
        for name, check in checks:
            self._check(name, check)
        print(f"\nResult: {'FAIL' if self.failures else 'PASS'} ({len(checks)} checks)")
        return not self.failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--environment", choices=("canary", "production"), required=True)
    parser.add_argument("--deep", action="store_true")
    args = parser.parse_args()

    try:
        return 0 if SmokeSuite(args.base_url, args.environment, args.deep).run() else 1
    except (TimeoutError, URLError) as error:
        print(f"Hosted smoke tests could not reach the app: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
