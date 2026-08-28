"""Outbound runtime: circuit-breaker state machine and pooled request policy."""

from __future__ import annotations

import httpx
import pytest

from tripplanner import concurrency, http_client
from tripplanner.circuit_breaker import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    BreakerPolicy,
    CircuitBreaker,
    CircuitBreakerRegistry,
)
from tripplanner.places_budget import places_budget_scope


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _breaker(clock: FakeClock, **policy: object) -> CircuitBreaker:
    return CircuitBreaker(
        "test",
        BreakerPolicy(**policy),  # type: ignore[arg-type]
        clock=clock,
    )


def test_breaker_opens_after_threshold_and_fails_fast() -> None:
    clock = FakeClock()
    breaker = _breaker(clock, failure_threshold=3, open_seconds=30.0)

    for _ in range(2):
        assert breaker.allow()
        breaker.record_failure()
    assert breaker.state == CLOSED

    assert breaker.allow()
    breaker.record_failure()

    assert breaker.state == OPEN
    assert breaker.allow() is False
    assert breaker.short_circuited == 1


def test_breaker_success_resets_failure_run() -> None:
    clock = FakeClock()
    breaker = _breaker(clock, failure_threshold=2)

    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()

    assert breaker.state == CLOSED
    assert breaker.allow()


def test_breaker_half_open_probe_closes_on_success() -> None:
    clock = FakeClock()
    breaker = _breaker(clock, failure_threshold=1, open_seconds=30.0)

    breaker.record_failure()
    assert breaker.allow() is False

    clock.now = 30.0
    assert breaker.state == HALF_OPEN
    assert breaker.allow()
    # Only one probe is admitted while half open.
    assert breaker.allow() is False

    breaker.record_success()
    assert breaker.state == CLOSED
    assert breaker.allow()


def test_breaker_half_open_failure_reopens_for_a_full_cooldown() -> None:
    clock = FakeClock()
    breaker = _breaker(clock, failure_threshold=1, open_seconds=30.0)

    breaker.record_failure()
    clock.now = 30.0
    assert breaker.allow()
    breaker.record_failure()

    assert breaker.state == OPEN
    assert breaker.allow() is False


def test_registry_returns_one_breaker_per_endpoint() -> None:
    registry = CircuitBreakerRegistry()
    first = registry.get("places.googleapis.com")
    second = registry.get("places.googleapis.com")
    other = registry.get("api.tavily.com")

    assert first is second
    assert first is not other
    assert set(registry.snapshot()) == {"places.googleapis.com", "api.tavily.com"}


def test_endpoint_identity_and_policy_lookup() -> None:
    assert http_client.endpoint_for("https://places.googleapis.com/v1/places") == (
        "places.googleapis.com"
    )
    assert http_client.endpoint_for("https://www.example.com/x") == "example.com"

    places = http_client.policy_for("places.googleapis.com")
    unknown = http_client.policy_for("some-new-provider.example")

    assert places.timeout.read == 8.0
    # A brand-new dependency is budgeted by default, with no registration step.
    assert unknown.timeout.read == 12.0


@pytest.mark.parametrize(
    ("url", "headers", "expected"),
    [
        (
            "https://places.googleapis.com/v1/places:searchText",
            {"X-Goog-FieldMask": "places.id,places.rating"},
            ("text_search", "pro"),
        ),
        (
            "https://places.googleapis.com/v1/places:searchText",
            {"X-Goog-FieldMask": "places.id,places.editorialSummary"},
            ("text_search", "enterprise_atmosphere"),
        ),
        (
            "https://places.googleapis.com/v1/places/abc/photos/one/media",
            {},
            ("photo_media", "photo_media"),
        ),
    ],
)
def test_google_operation_classifies_billable_request(
    url: str, headers: dict[str, str], expected: tuple[str, str]
) -> None:
    assert http_client.google_operation(url, {"headers": headers}) == expected


def test_request_uses_the_pooled_client_and_endpoint_budget(monkeypatch) -> None:
    http_client.reset_breakers_for_tests()
    seen: dict = {}

    class FakeClient:
        def request(self, method, url, **kwargs):
            seen.update({"method": method, "url": url, **kwargs})
            return httpx.Response(200, request=httpx.Request(method, url))

    monkeypatch.setattr(http_client, "get_client", FakeClient)

    with places_budget_scope("user_interaction"):
        response = http_client.get("https://places.googleapis.com/v1/places:searchText")

    assert response.status_code == 200
    assert seen["timeout"].read == 8.0


def test_request_denies_unscoped_paid_provider_before_network(monkeypatch) -> None:
    monkeypatch.setattr(
        http_client,
        "get_client",
        lambda: pytest.fail("unscoped provider call reached the network client"),
    )

    with pytest.raises(PermissionError, match="not authorized"):
        http_client.get("https://places.googleapis.com/v1/places:searchText")


def test_repeated_failure_short_circuits_instead_of_paying_the_timeout(monkeypatch) -> None:
    http_client.reset_breakers_for_tests()
    attempts = {"count": 0}

    class FailingClient:
        def request(self, method, url, **_kwargs):
            attempts["count"] += 1
            raise httpx.ConnectTimeout("boom", request=httpx.Request(method, url))

    monkeypatch.setattr(http_client, "get_client", FailingClient)

    for _ in range(4):
        with pytest.raises(httpx.HTTPError):
            http_client.get("https://broken.example/v1/thing")

    with pytest.raises(http_client.CircuitOpenError):
        http_client.get("https://broken.example/v1/thing")

    # The fifth call never reached the transport.
    assert attempts["count"] == 4
    assert http_client.outbound_status()["endpoints"]["broken.example"]["state"] == OPEN


def test_circuit_open_is_an_httpx_error_so_call_sites_still_degrade() -> None:
    assert issubclass(http_client.CircuitOpenError, httpx.HTTPError)


def test_server_errors_count_against_the_breaker(monkeypatch) -> None:
    http_client.reset_breakers_for_tests()

    class ServerErrorClient:
        def request(self, method, url, **_kwargs):
            return httpx.Response(503, request=httpx.Request(method, url))

    monkeypatch.setattr(http_client, "get_client", ServerErrorClient)

    for _ in range(4):
        http_client.get("https://flaky.example/v1/thing")

    assert http_client.outbound_status()["endpoints"]["flaky.example"]["state"] == OPEN


def test_run_parallel_returns_every_branch_and_degrades_failures() -> None:
    def boom() -> str:
        raise RuntimeError("branch failed")

    results = concurrency.run_parallel(
        {"places": lambda: "places", "news": boom, "weather": lambda: "weather"}
    )

    assert results == {"places": "places", "news": None, "weather": "weather"}


def test_run_parallel_is_concurrent_not_sequential() -> None:
    import time

    def slow(value: str):
        def run() -> str:
            time.sleep(0.2)
            return value

        return run

    started = time.monotonic()
    results = concurrency.run_parallel({name: slow(name) for name in ("a", "b", "c")})
    elapsed = time.monotonic() - started

    assert results == {"a": "a", "b": "b", "c": "c"}
    assert elapsed < 0.5
