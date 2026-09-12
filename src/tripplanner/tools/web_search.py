"""Tavily web search — fresh content (blog posts, travel guides, recent reviews).

Sign up free: https://tavily.com  (1 000 searches/month free)

Why: LLM knowledge cuts off ~year before now. For "best things to do in X (2026)",
seasonal closures, new openings, recent traveler tips — search the live web.
"""

from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool

from tripplanner import http_client
from tripplanner.caching import get_cache
from tripplanner.config import get_settings

_TAVILY_URL = "https://api.tavily.com/search"

# Tavily is billed per search and had no cache at all, so the destination
# overview bought the same "latest travel news for <destination>" every time the
# planner was opened. Six hours is well inside how fast travel news moves, and
# the shared volatile TTL policy still governs it.
_SEARCH_TTL_S = 6 * 60 * 60
_WEB_SEARCH_CACHE = get_cache("web-search", default_ttl_seconds=_SEARCH_TTL_S)


def is_configured() -> bool:
    return bool(get_settings().tavily_api_key)


def search_raw(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str | None = None,
) -> dict:
    """Run a Tavily search and return parsed structured data.

    Shared by the ``web_search`` agent tool and the SPA destination-overview
    endpoint. Returns ``{"answer": str, "results": [{title, url, content}]}``.
    Raises ``RuntimeError`` when not configured and ``httpx.HTTPError`` on
    transport failures so callers can decide how to surface the problem.
    """
    if not is_configured():
        raise RuntimeError("Tavily web search not configured (set TAVILY_API_KEY).")

    depth = search_depth if search_depth in ("basic", "advanced") else "basic"
    results = min(max(max_results, 1), 10)
    cache_key = "|".join(
        [" ".join(query.lower().split()), str(results), depth, topic or ""]
    )
    cached = _WEB_SEARCH_CACHE.get(cache_key)
    if isinstance(cached, dict):
        from tripplanner.provider_usage import record_cache_hit

        record_cache_hit(provider="tavily", operation="request")
        return cached

    payload: dict = {
        "api_key": get_settings().tavily_api_key,
        "query": query,
        "max_results": results,
        "search_depth": depth,
        "include_answer": True,
    }
    if topic in ("news", "general"):
        payload["topic"] = topic
    resp = http_client.post(_TAVILY_URL, json=payload)
    resp.raise_for_status()
    data = resp.json()
    out = {
        "answer": data.get("answer", "") or "",
        "results": [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content", "") or "")[:400],
            }
            for r in data.get("results", [])
        ],
    }
    _WEB_SEARCH_CACHE.set(cache_key, out)
    return out


@tool
def web_search(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
    """Search the live web for fresh travel content (guides, reviews, news, tips).

    Use when:
      - User asks about current events, recent openings, seasonal advice
      - You need traveler tips beyond your training data
      - Filling gaps that structured APIs don't cover (e.g. "is monsoon safe in Goa?")

    Args:
        query: Search query, e.g. "best beaches in Goa for families 2026".
        max_results: 1-10. Default 5.
        search_depth: "basic" (fast) or "advanced" (deeper, slower, ~2x credits).
    """
    if not is_configured():
        return (
            "Tavily web search not configured. "
            "Set TAVILY_API_KEY in .env. Get a free key at https://tavily.com"
        )

    try:
        out = search_raw(query, max_results=max_results, search_depth=search_depth)
    except httpx.HTTPError as e:
        return f"Web search failed: {e}"

    return json.dumps(out, indent=2)

