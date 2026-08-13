"""Shared fan-out for independent remote work.

Composite responses are assembled from several unrelated sources — a destination
overview is Places *and* fresh news, a comparison is one provider *and* an FX
rate. Running them one after another makes the response as slow as their sum
when it only has to be as slow as the slowest.

:func:`run_parallel` is the one place that knows how to do that: a shared bounded
worker pool, a wall-clock deadline, and per-branch degradation. A branch that
fails or overruns yields ``None`` instead of failing the whole response, which
matches how every provider call site already degrades.

Only use this for genuinely independent work. Nested fan-out from inside a
branch is fine — helpers such as ``places_cache`` own their own pool — but a
branch must never wait on another branch of the same call.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, TypeVar

T = TypeVar("T")
log = logging.getLogger(__name__)

_MAX_WORKERS = 16

_lock = Lock()
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=_MAX_WORKERS, thread_name_prefix="fanout"
            )
        return _executor


def run_parallel(
    tasks: Mapping[str, Callable[[], T]], *, timeout: float | None = None
) -> dict[str, T | None]:
    """Run every task concurrently and return results keyed by task name.

    A task that raises or exceeds ``timeout`` contributes ``None``.
    """
    if not tasks:
        return {}
    if len(tasks) == 1:
        name, task = next(iter(tasks.items()))
        return {name: _safe(name, task)}

    executor = _get_executor()
    futures = {name: executor.submit(task) for name, task in tasks.items()}
    deadline = None if timeout is None else time.monotonic() + timeout
    results: dict[str, Any] = {}
    for name, future in futures.items():
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        try:
            results[name] = future.result(timeout=remaining)
        except Exception as exc:
            future.cancel()
            log.warning("parallel branch %s failed: %s", name, type(exc).__name__)
            results[name] = None
    return results


def _safe(name: str, task: Callable[[], T]) -> T | None:
    try:
        return task()
    except Exception as exc:
        log.warning("parallel branch %s failed: %s", name, type(exc).__name__)
        return None


def shutdown_for_tests() -> None:
    global _executor
    with _lock:
        executor, _executor = _executor, None
    if executor is not None:
        executor.shutdown(wait=False)
