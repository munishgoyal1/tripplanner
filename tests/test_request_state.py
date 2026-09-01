from __future__ import annotations

from tripplanner import request_state


def test_request_state_loads_once_and_returns_isolated_copies() -> None:
    calls = 0

    def load() -> dict[str, list[str]]:
        nonlocal calls
        calls += 1
        return {"notes": ["saved"]}

    with request_state.request_state_scope():
        first = request_state.get_or_load(("trip", "user", "active"), load)
        first["notes"].append("caller mutation")
        second = request_state.get_or_load(("trip", "user", "active"), load)

        assert calls == 1
        assert second == {"notes": ["saved"]}


def test_request_state_exposes_writes_then_expires_after_request() -> None:
    calls = 0

    def load() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"revision": calls}

    key = ("trip", "user", "active")
    with request_state.request_state_scope():
        assert request_state.get_or_load(key, load) == {"revision": 1}
        request_state.store(key, {"revision": 2})
        assert request_state.get_or_load(key, load) == {"revision": 2}

    with request_state.request_state_scope():
        assert request_state.get_or_load(key, load) == {"revision": 2}

    assert calls == 2
