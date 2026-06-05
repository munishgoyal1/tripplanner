"""Tests for tools/visa.py (Tavily-backed visa & entry-rules check)."""

from __future__ import annotations

import json

import httpx
import pytest

from multiagent.tools import visa


# ---- pure helpers ---------------------------------------------------------


def test_build_query_includes_all_inputs():
    q = visa._build_query("Indian", "France", "tourism", 7)
    assert "Indian passport holders" in q
    assert "France" in q
    assert "tourism" in q
    assert "stay 7 days" in q
    assert "official source" in q


def test_build_query_omits_days_when_zero():
    q = visa._build_query("Indian", "France", "tourism", None)
    assert "stay" not in q


# ---- @tool: check_visa_requirements --------------------------------------


def test_visa_not_configured(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: False)
    out = visa.check_visa_requirements.invoke(
        {"passport_country": "Indian", "destination_country": "France"}
    )
    assert "not configured" in out.lower()


def test_visa_missing_inputs(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: True)
    out = visa.check_visa_requirements.invoke(
        {"passport_country": "", "destination_country": "France"}
    )
    assert "required" in out.lower()


def test_visa_returns_structured_envelope(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: True)
    fake_results = [
        {"title": "Schengen Visa Info", "url": "https://schengenvisainfo.com/india/", "content": "Indians need Schengen visa..."},
        {"title": "Random blog", "url": "https://traveltips.example.com/", "content": "Some blog..."},
        {"title": "MEA India", "url": "https://www.mea.gov.in/visa-info", "content": "Official guidance..."},
        {"title": "Travel Forum", "url": "https://forum.example.com/", "content": "User posts..."},
        {"title": "Embassy of France", "url": "https://france.embassy.gov.in/", "content": "Apply via VFS..."},
    ]

    def fake_search_raw(query, max_results, search_depth):
        assert max_results == 8
        assert search_depth == "advanced"
        assert "France" in query and "Indian" in query
        return {"answer": "Indian nationals need a Schengen visa for France.", "results": fake_results}

    monkeypatch.setattr(visa, "search_raw", fake_search_raw)
    out = json.loads(
        visa.check_visa_requirements.invoke(
            {
                "passport_country": "Indian",
                "destination_country": "France",
                "purpose": "tourism",
                "length_of_stay_days": 7,
            }
        )
    )
    assert out["passport_country"] == "Indian"
    assert out["destination_country"] == "France"
    assert out["length_of_stay_days"] == 7
    assert "Schengen" in out["summary"]
    assert len(out["results"]) == 5
    # Preferred sources (mea.gov.in, schengenvisainfo, embassy.gov) should come first.
    urls = [r["url"] for r in out["results"]]
    assert urls[0] in {
        "https://schengenvisainfo.com/india/",
        "https://www.mea.gov.in/visa-info",
        "https://france.embassy.gov.in/",
    }
    # The non-preferred result should be ranked AFTER all preferred ones.
    blog_idx = urls.index("https://traveltips.example.com/")
    preferred_idx = next(
        i for i, u in enumerate(urls) if "mea.gov.in" in u or "schengenvisainfo" in u
    )
    assert preferred_idx < blog_idx
    assert "disclaimer" in out


def test_visa_propagates_search_error(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: True)

    def boom(*a, **k):
        raise httpx.HTTPError("network down")

    monkeypatch.setattr(visa, "search_raw", boom)
    out = visa.check_visa_requirements.invoke(
        {"passport_country": "Indian", "destination_country": "France"}
    )
    assert "Visa search failed" in out
