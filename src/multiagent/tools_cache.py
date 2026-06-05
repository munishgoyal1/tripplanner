"""Read-through cache for deterministic tool calls.

The trip agent invokes the same lookups again and again — same flight search,
same place reviews, same weather window — across consecutive user turns and
even across sessions. Re-running them burns Amadeus/Google/Tavily quota and
adds latency for no extra signal.

This module wraps every read-only tool so that:

  1. A canonical cache key is computed from ``(tool_name, args)``.
  2. We look the key up. On hit we return immediately, no tool body executed.
  3. On miss we run the tool, store the result, then return it.

Stateful tools — anything that *writes* to user prefs or trip state, or that
finalises/executes a trip — are listed in ``_STATEFUL_TOOLS`` and are always
passed through untouched.

Two storage backends, picked at call time:

  * Cosmos DB (when ``storage_cosmos.is_enabled()``). Container ``tool_cache``,
    partition ``/user_id``. Each entry carries ``expires_at`` (unix seconds);
    stale rows are deleted lazily on read.
  * In-process dict (everywhere else — CLI, tests, offline). Bounded LRU of
    256 entries per process, also TTL-aware.

The cache is keyed by ``user_id`` so two users hitting the same Tavily query
don't share rows (their personalisation may differ — currency, language,
trip context). For non-personalised calls this is slightly wasteful but
isolation is more important than dedup across tenants.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

from langchain_core.tools import BaseTool

from multiagent.user_context import get_user_id


# Tools that mutate persistent state — never cache, always pass through.
_STATEFUL_TOOLS: frozenset[str] = frozenset(
    {
        # trip plan lifecycle
        "create_trip_plan",
        "update_trip_plan",
        "finalize_trip",
        "execute_trip",
        # user preferences (writes)
        "save_travel_preferences",
        "record_past_trip",
        "record_trip_postmortem",
        "remember_about_user",
        "update_user_profile",
        "add_family_member",
        "add_user_interest",
        "add_user_dislike",
        "record_trip_mention",
    }
)


# Default TTL is 30 minutes — long enough to dedup within a session, short
# enough that flight prices / hours don't go stale.
_DEFAULT_TTL_SECONDS = 30 * 60

# Per-process LRU when Cosmos is unavailable.
_LOCAL_CACHE: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
_LOCAL_MAX = 256


def _canonical_args(args: dict[str, Any] | None) -> str:
    """Stable JSON of args so equivalent calls hash the same."""
    return json.dumps(args or {}, sort_keys=True, default=str)


def _cache_key(tool_name: str, args: dict[str, Any] | None) -> str:
    """Short, filesystem-safe hash for ``(tool_name, args)``.

    We include the tool name in the digest to avoid any chance of a
    cross-tool collision; the doc id then doubles as a debug label.
    """
    blob = f"{tool_name}|{_canonical_args(args)}".encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()[:32]
    return f"{tool_name}-{digest}"


def _coerce_result(result: Any) -> str:
    """Tools return strings; coerce defensively just in case."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def _cosmos_get(user_id: str, key: str) -> str | None:
    from multiagent import storage_cosmos

    doc = storage_cosmos.read_doc("tool_cache", user_id, key)
    if not doc:
        return None
    if float(doc.get("expires_at", 0)) <= time.time():
        # Lazy expiry: delete and miss.
        try:
            storage_cosmos.delete_doc("tool_cache", user_id, key)
        except Exception:
            # Best-effort cleanup; a stale row is fine, we'll skip it.
            pass
        return None
    return doc.get("result")


def _cosmos_set(user_id: str, key: str, value: str, ttl: int) -> None:
    from multiagent import storage_cosmos

    storage_cosmos.upsert_doc(
        "tool_cache",
        user_id,
        key,
        {"result": value, "expires_at": time.time() + ttl},
    )


def _local_get(user_id: str, key: str) -> str | None:
    full = f"{user_id}|{key}"
    entry = _LOCAL_CACHE.get(full)
    if not entry:
        return None
    expires_at, value = entry
    if expires_at <= time.time():
        _LOCAL_CACHE.pop(full, None)
        return None
    _LOCAL_CACHE.move_to_end(full)  # LRU touch
    return value


def _local_set(user_id: str, key: str, value: str, ttl: int) -> None:
    full = f"{user_id}|{key}"
    _LOCAL_CACHE[full] = (time.time() + ttl, value)
    _LOCAL_CACHE.move_to_end(full)
    while len(_LOCAL_CACHE) > _LOCAL_MAX:
        _LOCAL_CACHE.popitem(last=False)


def cache_lookup(tool_name: str, args: dict[str, Any] | None) -> str | None:
    """Return a cached result, or ``None`` on miss / stateful tool."""
    if tool_name in _STATEFUL_TOOLS:
        return None
    user_id = get_user_id() or "local"
    key = _cache_key(tool_name, args)
    # Prefer Cosmos when available so cache survives container restarts.
    try:
        from multiagent import storage_cosmos

        if storage_cosmos.is_enabled():
            return _cosmos_get(user_id, key)
    except Exception:
        # Cosmos can fail (network, perm); fall back to local cache.
        pass
    return _local_get(user_id, key)


def cache_store(
    tool_name: str,
    args: dict[str, Any] | None,
    result: Any,
    ttl: int = _DEFAULT_TTL_SECONDS,
) -> None:
    """Store ``result`` for ``(tool_name, args)``; no-op for stateful tools."""
    if tool_name in _STATEFUL_TOOLS:
        return
    user_id = get_user_id() or "local"
    key = _cache_key(tool_name, args)
    value = _coerce_result(result)
    try:
        from multiagent import storage_cosmos

        if storage_cosmos.is_enabled():
            _cosmos_set(user_id, key, value, ttl)
            return
    except Exception:
        # Fall through to local cache on any Cosmos failure.
        pass
    _local_set(user_id, key, value, ttl)


def clear_local_cache() -> None:
    """Test hook: wipe the per-process cache."""
    _LOCAL_CACHE.clear()


def wrap_tools_with_cache(tools: list[BaseTool]) -> list[BaseTool]:
    """Return a parallel list of tools whose ``invoke`` is cache-aware.

    We build a *new* StructuredTool per input so we never mutate the original
    @tool singletons — tests and other call sites that import the originals
    must keep their non-cached behaviour. The cache lives only on the copy
    used by the graph's ToolNode.
    """
    from langchain_core.tools import StructuredTool

    wrapped: list[BaseTool] = []
    for tool in tools:
        if tool.name in _STATEFUL_TOOLS:
            wrapped.append(tool)
            continue
        wrapped.append(_build_cached_copy(tool, StructuredTool))
    return wrapped


def _build_cached_copy(tool: BaseTool, StructuredTool: Any) -> BaseTool:
    """Return a new StructuredTool that wraps ``tool`` with cache lookup."""
    original_invoke = tool.invoke
    tool_name = tool.name

    def cached_func(*args: Any, **kwargs: Any) -> Any:
        # Local import keeps tools_cache importable in test contexts that
        # haven't initialised logging yet.
        from multiagent.observability import record_tool_call

        # Normalise tool args. LangChain calls the underlying ``func`` with
        # the parsed kwargs from args_schema, so positional args are rare.
        cache_args = dict(kwargs)
        if args:
            cache_args["__pos"] = list(args)

        started = time.time()
        user_id = get_user_id() or "local"

        hit = cache_lookup(tool_name, cache_args)
        if hit is not None:
            record_tool_call(
                tool_name,
                duration_ms=(time.time() - started) * 1000,
                status="ok",
                cache_hit=True,
                user_id=user_id,
            )
            return hit

        try:
            # Delegate to the original tool — its full invoke pipeline (args
            # parsing, callbacks, error handling) stays intact.
            result = original_invoke(kwargs if kwargs else (args[0] if args else {}))
        except Exception as exc:
            record_tool_call(
                tool_name,
                duration_ms=(time.time() - started) * 1000,
                status="error",
                cache_hit=False,
                user_id=user_id,
                error=type(exc).__name__,
            )
            raise

        record_tool_call(
            tool_name,
            duration_ms=(time.time() - started) * 1000,
            status="ok",
            cache_hit=False,
            user_id=user_id,
        )
        cache_store(tool_name, cache_args, result)
        return result

    return StructuredTool.from_function(
        func=cached_func,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )
