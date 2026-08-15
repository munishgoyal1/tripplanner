"""Shared pytest fixtures.

The app auto-enables the Cosmos backend whenever ``COSMOS_ENDPOINT`` is set
(see ``storage_cosmos.is_enabled``). Local dev now points ``.env`` at an
isolated local Cosmos account, which would otherwise make the suite read/write
that shared live database instead of the per-test temp dirs each test sets up.

Force Cosmos OFF by default for every test so storage stays hermetic and uses
the monkeypatched local-JSON paths. Tests that specifically exercise the Cosmos
dispatch branch (e.g. ``TestCosmosDispatch``) simply re-patch ``is_enabled`` to
``True`` within the test, which overrides this default.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _force_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    from tripplanner import storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)


@pytest.fixture(autouse=True)
def _disable_debug_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep fixture trips out of the committed debug archive."""
    monkeypatch.setenv("TRIPPLANNER_DEBUG_STORE", "0")


@pytest.fixture(autouse=True)
def _memory_cache_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let the suite reach the shared Redis.

    A developer's ``.env`` may enable it, which made the tests both slow and
    non-hermetic: they read entries another environment had written, and wrote
    their own fixtures back.
    """
    from tripplanner import caching

    monkeypatch.setattr(caching, "_BACKEND", caching.MemoryBackend())
    for cache in list(caching._REGISTRY.values()):
        cache.rebind()
        cache.clear()
