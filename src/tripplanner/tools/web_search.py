"""Tavily web search — fresh content (blog posts, travel guides, recent reviews).

Sign up free: https://tavily.com  (1 000 searches/month free)

Why: LLM knowledge cuts off ~year before now. For "best things to do in X (2026)",
seasonal closures, new openings, recent traveler tips — search the live web.
"""

from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool

from tripplanner.config import get_settings

_TAVILY_URL = "https://api.tavily.com/search"


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

    payload: dict = {
        "api_key": get_settings().tavily_api_key,
        "query": query,
        "max_results": min(max(max_results, 1), 10),
        "search_depth": search_depth if search_depth in ("basic", "advanced") else "basic",
        "include_answer": True,
    }
    if topic in ("news", "general"):
        payload["topic"] = topic
    resp = httpx.post(_TAVILY_URL, json=payload, timeout=25)
    resp.raise_for_status()
    data = resp.json()
    return {
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

