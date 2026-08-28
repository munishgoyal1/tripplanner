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
finalises/executes a trip — are listed in ``_STATEFUL_TOOLS``. They bypass
read-through caching and trigger invalidation of user-scoped cache entries
after a successful write.

Two storage backends, picked at call time:

  * Cosmos DB (when ``storage_cosmos.is_enabled()``). Container ``tool_cache``,
    partition ``/user_id``. Each entry carries ``expires_at`` (unix seconds);
    stale rows are deleted lazily on read.
  * In-process dict (everywhere else — CLI, tests, offline). Bounded LRU of
    256 entries per process, also TTL-aware.

Cache scoping
-------------
Most tools return the same result for the same args regardless of who calls
them (weather for Goa is the same for every user). These are keyed ONLY by
``(tool_name, args)`` and stored under the shared user_id ``_global_`` so the
result is reused across all users/sessions.

A small set of tools whose output IS user-specific (preference reads, trip
reads) remain keyed by ``(user_id, tool_name, args)``.

The practical effect: a guest browsing Goa in the morning and another user
(or the same guest in a new session) asking about Goa later in the day will
get instant cached responses for places, weather, visa and events — no extra
API quota consumed.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool

from tripplanner.user_context import get_user_id

# Tools that mutate persistent state — never read/write cache directly.
_STATEFUL_TOOLS: frozenset[str] = frozenset(
    {
        # trip plan lifecycle
        "create_trip_plan",
        "update_trip_plan",
        "finalize_trip",
        "execute_trip",
        "resume_trip",
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

_GLOBAL_USER_ID = "_global_"

# Default TTL is 30 minutes — long enough to dedup within a session, short
# enough that flight prices / hours don't go stale.
_DEFAULT_TTL_SECONDS = 30 * 60

_USER_SCOPE = "user"
_GLOBAL_SCOPE = "global"


@dataclass(frozen=True)
class CachePolicy:
    scope: str
    ttl_seconds: int


# String-valued args on these keys are lower-cased before hashing for global
# tools. This improves hit-rate for semantically equivalent calls where only
# casing differs ("Paris" vs "paris").
_LOWERCASE_KEYS: frozenset[str] = frozenset(
    {
        "city",
        "country",
        "destination",
        "destination_city",
        "from_city",
        "iata_code",
        "origin",
        "origin_city",
        "query",
        "to_city",
    }
)

# Tool-level caching policy: which scope to use and how long a hit remains
# valid. Global means reusable across all users; user means isolated per user.
_CACHE_POLICIES: dict[str, CachePolicy] = {
    # User-specific, frequently read and frequently refreshed.
    "get_travel_preferences": CachePolicy(scope=_USER_SCOPE, ttl_seconds=5 * 60),
    "get_trip_plan": CachePolicy(scope=_USER_SCOPE, ttl_seconds=45),
    "list_past_trips": CachePolicy(scope=_USER_SCOPE, ttl_seconds=2 * 60),
    "recall_relevant_memory": CachePolicy(scope=_USER_SCOPE, ttl_seconds=60),

    # Highly volatile inventory/pricing/search.
    "search_flights_duffel": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=60),
    "verify_flight_offer": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=30),
    "search_flights": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=5 * 60),
    "search_hotels": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=60),
    "search_activities": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=60),
    "search_points_of_interest": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=20 * 60),
    "search_places_with_reviews": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=20 * 60),
    "nearby_restaurants": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=20 * 60),
    "web_search": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=20 * 60),

    # Public data that changes less frequently.
    "get_place_reviews": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=6 * 60 * 60),
    "check_place_hours": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=2 * 60 * 60),
    "get_weather_forecast": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=90 * 60),
    "check_visa_requirements": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=12 * 60 * 60),
    "find_local_events": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=2 * 60 * 60),
    "compute_route": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=6 * 60 * 60),
    "optimize_day_route": CachePolicy(scope=_GLOBAL_SCOPE, ttl_seconds=6 * 60 * 60),
}

_GOOGLE_TTL_SETTINGS: dict[str, str] = {
    "search_places_with_reviews": "google_places_search_cache_ttl_sec",
    "nearby_restaurants": "google_places_search_cache_ttl_sec",
    "get_place_reviews": "google_places_reviews_cache_ttl_sec",
    "check_place_hours": "google_places_hours_cache_ttl_sec",
}

# Per-process LRU when Cosmos is unavailable.
_LOCAL_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()
_LOCAL_MAX = 256


def _normalize_cache_value(value: Any, *, scope: str, key_name: str = "") -> Any:
    """Normalize args so semantically equivalent calls share cache keys."""
    if isinstance(value, str):
        text = " ".join(value.strip().split())
        if scope == _GLOBAL_SCOPE and key_name in _LOWERCASE_KEYS:
            return text.lower()
        return text
    if isinstance(value, dict):
        return {
            str(k): _normalize_cache_value(v, scope=scope, key_name=str(k).lower())
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_normalize_cache_value(v, scope=scope, key_name=key_name) for v in value]
    if isinstance(value, tuple):
        return [_normalize_cache_value(v, scope=scope, key_name=key_name) for v in value]
    return value


def _canonical_args(args: dict[str, Any] | None, *, scope: str) -> str:
    """Stable JSON of normalized args so equivalent calls hash the same."""
    normal = _normalize_cache_value(args or {}, scope=scope)
    return json.dumps(normal, sort_keys=True, default=str)


def _cache_key(tool_name: str, args: dict[str, Any] | None, *, scope: str) -> str:
    """Short, filesystem-safe hash for ``(tool_name, args)``.

    We include the tool name in the digest to avoid any chance of a
    cross-tool collision; the doc id then doubles as a debug label.
    """
    blob = f"{tool_name}|{_canonical_args(args, scope=scope)}".encode()
    digest = hashlib.sha256(blob).hexdigest()[:32]
    return f"{tool_name}-{digest}"


def _resolve_policy(tool_name: str) -> CachePolicy | None:
    if tool_name in _STATEFUL_TOOLS:
        return None
    default = CachePolicy(scope=_USER_SCOPE, ttl_seconds=_DEFAULT_TTL_SECONDS)
    return _CACHE_POLICIES.get(tool_name, default)


def _resolve_user_partition(scope: str, user_id: str) -> str:
    if scope == _GLOBAL_SCOPE:
        return _GLOBAL_USER_ID
    return f"user:{user_id or 'local'}"


def _coerce_result(result: Any) -> str:
    """Tools return strings; coerce defensively just in case."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def _cosmos_get(user_id: str, key: str) -> str | None:
    from tripplanner import storage_cosmos

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
    from tripplanner import storage_cosmos

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
    policy = _resolve_policy(tool_name)
    if policy is None:
        return None
    user_id = get_user_id() or "local"
    partition = _resolve_user_partition(policy.scope, user_id)
    key = _cache_key(tool_name, args, scope=policy.scope)
    # Prefer Cosmos when available so cache survives container restarts.
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            return _cosmos_get(partition, key)
    except Exception:
        # Cosmos can fail (network, perm); fall back to local cache.
        pass
    return _local_get(partition, key)


def cache_store(
    tool_name: str,
    args: dict[str, Any] | None,
    result: Any,
    ttl: int | None = None,
) -> None:
    """Store ``result`` for ``(tool_name, args)``; no-op for stateful tools."""
    policy = _resolve_policy(tool_name)
    if policy is None:
        return
    user_id = get_user_id() or "local"
    partition = _resolve_user_partition(policy.scope, user_id)
    key = _cache_key(tool_name, args, scope=policy.scope)
    value = _coerce_result(result)
    from tripplanner.config import get_settings

    settings = get_settings()
    configured_ttl = getattr(
        settings,
        _GOOGLE_TTL_SETTINGS.get(tool_name, ""),
        policy.ttl_seconds,
    )
    ttl_seconds = settings.cache_ttl(ttl if ttl is not None else configured_ttl)
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            _cosmos_set(partition, key, value, ttl_seconds)
            return
    except Exception:
        # Fall through to local cache on any Cosmos failure.
        pass
    _local_set(partition, key, value, ttl_seconds)


def clear_local_cache() -> None:
    """Test hook: wipe the per-process cache."""
    _LOCAL_CACHE.clear()


def clear_cache_for_user(user_id: str) -> int:
    """Delete cached tool responses for a single user."""
    scoped_user = _resolve_user_partition(_USER_SCOPE, user_id)
    deleted = 0
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            return storage_cosmos.delete_docs("tool_cache", scoped_user)
    except Exception:
        pass

    prefix = f"{scoped_user}|"
    for key in list(_LOCAL_CACHE.keys()):
        if key.startswith(prefix):
            _LOCAL_CACHE.pop(key, None)
            deleted += 1
    return deleted


def _invalidate_user_scoped_cache(user_id: str) -> None:
    """Invalidate user-scoped entries after stateful tool writes."""
    clear_cache_for_user(user_id or "local")


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
        wrapped.append(_build_cached_copy(tool, StructuredTool))
    return wrapped


def _build_cached_copy(tool: BaseTool, structured_tool: Any) -> BaseTool:
    """Return a new StructuredTool that wraps ``tool`` with cache lookup."""
    original_invoke = tool.invoke
    tool_name = tool.name
    policy = _resolve_policy(tool_name)

    def cached_func(*args: Any, **kwargs: Any) -> Any:
        # Local import keeps tools_cache importable in test contexts that
        # haven't initialised logging yet.
        from tripplanner.observability import record_tool_call
        from tripplanner.tools import search_learning

        # Passively learn from search behavior (cabin class, hotel star floor,
        # activity categories). Best-effort and a no-op for non-search tools.
        search_learning.observe(tool_name, kwargs)

        # Normalise tool args. LangChain calls the underlying ``func`` with
        # the parsed kwargs from args_schema, so positional args are rare.
        cache_args = dict(kwargs)
        if args:
            cache_args["__pos"] = list(args)
        refresh = cache_args.pop("refresh", False) is True

        started = time.time()
        user_id = get_user_id() or "local"
        cache_scope = policy.scope if policy else "stateful"

        hit = None if refresh else cache_lookup(tool_name, cache_args)
        if hit is not None:
            record_tool_call(
                tool_name,
                duration_ms=(time.time() - started) * 1000,
                status="ok",
                cache_hit=True,
                user_id=user_id,
                cache_scope=cache_scope,
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
                cache_scope=cache_scope,
                error=type(exc).__name__,
            )
            raise

        record_tool_call(
            tool_name,
            duration_ms=(time.time() - started) * 1000,
            status="ok",
            cache_hit=False,
            user_id=user_id,
            cache_scope=cache_scope,
        )
        if policy is None:
            _invalidate_user_scoped_cache(user_id)
            return result

        if not refresh:
            cache_store(tool_name, cache_args, result, ttl=policy.ttl_seconds)
        return result

    return structured_tool.from_function(
        func=cached_func,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )

