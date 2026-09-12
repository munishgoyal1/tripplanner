"""Tavily is billed per search and had no cache of any kind.

``/destination/overview`` asks it for "latest travel news for <destination>" and
that endpoint is part of every planner page load, so re-opening a finished trip
bought the same answer again each time.
"""

from __future__ import annotations

import httpx
import pytest

from tripplanner.tools import web_search


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(web_search, "is_configured", lambda: True)
    web_search._WEB_SEARCH_CACHE.clear()
    yield
    web_search._WEB_SEARCH_CACHE.clear()


def _response(title: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"answer": "a", "results": [{"title": title, "url": "u", "content": "c"}]},
        request=httpx.Request("POST", web_search._TAVILY_URL),
    )


def test_repeat_search_is_served_from_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_post(_url, **kwargs):
        calls.append(kwargs)
        return _response("Kashmir reopens")

    monkeypatch.setattr(web_search.http_client, "post", fake_post)

    first = web_search.search_raw("news for Kashmir", max_results=3, topic="news")
    second = web_search.search_raw("News   for  Kashmir ", max_results=3, topic="news")

    assert second == first
    assert len(calls) == 1


def test_a_different_query_is_not_served_from_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_post(_url, **kwargs):
        calls.append(kwargs)
        return _response("something")

    monkeypatch.setattr(web_search.http_client, "post", fake_post)

    web_search.search_raw("news for Kashmir", topic="news")
    web_search.search_raw("news for Kerala", topic="news")
    web_search.search_raw("news for Kashmir", topic="general")

    assert len(calls) == 3


def test_a_failed_search_is_not_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []

    def failing_post(url, **_kwargs):
        attempts.append(url)
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(web_search.http_client, "post", failing_post)

    for _ in range(2):
        with pytest.raises(httpx.HTTPError):
            web_search.search_raw("news for Kashmir", topic="news")

    assert len(attempts) == 2
