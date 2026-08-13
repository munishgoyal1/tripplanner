"""Pure per-endpoint circuit-breaker state machine.

A remote dependency that is down costs the full timeout on *every* call, so one
sick provider drags the whole planning turn into the tail. The breaker turns a
repeated failure into an immediate, cheap "unavailable" so the caller can fall
through to the next source in milliseconds instead of seconds.

This module owns the decision only. Transport, policy lookup, and telemetry live
in :mod:`tripplanner.http_client`, the same way ``graph_policy`` owns the pure
rules for ``graph``.

States
------
``closed``      normal; failures accumulate.
``open``        fail fast until ``open_seconds`` has elapsed.
``half_open``   a bounded number of probes may pass; one success closes the
                breaker, one failure re-opens it for another cooldown.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


@dataclass(frozen=True)
class BreakerPolicy:
    """How tolerant a single endpoint is before it is taken out of rotation."""

    failure_threshold: int = 4
    open_seconds: float = 30.0
    half_open_max_probes: int = 1


DEFAULT_BREAKER_POLICY = BreakerPolicy()


class CircuitBreaker:
    """Thread-safe breaker for one endpoint."""

    def __init__(
        self,
        name: str,
        policy: BreakerPolicy = DEFAULT_BREAKER_POLICY,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.policy = policy
        self._clock = clock
        self._lock = Lock()
        self._state = CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._probes_in_flight = 0
        self.short_circuited = 0

    def allow(self) -> bool:
        """Return ``True`` when a call may be attempted right now."""
        with self._lock:
            if self._state == CLOSED:
                return True
            if self._state == OPEN:
                if self._clock() - self._opened_at < self.policy.open_seconds:
                    self.short_circuited += 1
                    return False
                self._state = HALF_OPEN
                self._probes_in_flight = 0
            if self._probes_in_flight >= max(1, self.policy.half_open_max_probes):
                self.short_circuited += 1
                return False
            self._probes_in_flight += 1
            return True

    def record_success(self) -> None:
        with self._lock:
            self._state = CLOSED
            self._consecutive_failures = 0
            self._probes_in_flight = 0

    def record_failure(self) -> None:
        with self._lock:
            self._probes_in_flight = 0
            self._consecutive_failures += 1
            if (
                self._state == HALF_OPEN
                or self._consecutive_failures >= max(1, self.policy.failure_threshold)
            ):
                self._state = OPEN
                self._opened_at = self._clock()

    @property
    def state(self) -> str:
        """Current state, resolving an expired cooldown to ``half_open``."""
        with self._lock:
            if (
                self._state == OPEN
                and self._clock() - self._opened_at >= self.policy.open_seconds
            ):
                return HALF_OPEN
            return self._state

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "consecutive_failures": self._consecutive_failures,
            "short_circuited": self.short_circuited,
        }


class CircuitBreakerRegistry:
    """Lazily creates one breaker per endpoint name."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, name: str, policy: BreakerPolicy = DEFAULT_BREAKER_POLICY) -> CircuitBreaker:
        with self._lock:
            breaker = self._breakers.get(name)
            if breaker is None:
                breaker = CircuitBreaker(name, policy, clock=self._clock)
                self._breakers[name] = breaker
            return breaker

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            breakers = dict(self._breakers)
        return {name: breaker.status() for name, breaker in breakers.items()}

    def reset(self) -> None:
        with self._lock:
            self._breakers.clear()
