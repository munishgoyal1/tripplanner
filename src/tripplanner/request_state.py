"""Lazy, request-scoped snapshots of persisted user documents."""

from __future__ import annotations

import contextvars
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, TypeVar

_Value = TypeVar("_Value")
_MISSING = object()
_STATE: contextvars.ContextVar[dict[tuple[str, ...], Any] | None] = (
    contextvars.ContextVar("tripplanner_request_state", default=None)
)


@contextmanager
def request_state_scope() -> Iterator[None]:
    token = _STATE.set({})
    try:
        yield
    finally:
        _STATE.reset(token)


def get_or_load(key: tuple[str, ...], loader: Callable[[], _Value]) -> _Value:
    state = _STATE.get()
    if state is None:
        return loader()
    value = state.get(key, _MISSING)
    if value is _MISSING:
        value = loader()
        state[key] = deepcopy(value)
    return deepcopy(value)


def store(key: tuple[str, ...], value: _Value) -> None:
    state = _STATE.get()
    if state is not None:
        state[key] = deepcopy(value)


def discard(key: tuple[str, ...]) -> None:
    state = _STATE.get()
    if state is not None:
        state.pop(key, None)
