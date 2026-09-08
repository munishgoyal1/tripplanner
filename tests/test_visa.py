"""Tests for tools/visa.py (Tavily-backed visa & entry-rules check)."""

from __future__ import annotations

import json

import httpx
import pytest

from tripplanner.tools import visa


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


def test_visa_missing_destination(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: True)
    out = visa.check_visa_requirements.invoke(
        {"passport_country": "Indian", "destination_country": ""}
    )
    assert "destination_country is required" in out


# ---- passport country resolution ------------------------------------------


def _no_documents(monkeypatch, records=()):
    monkeypatch.setattr(
        "tripplanner.web.travel_documents.list_documents",
        lambda scope="traveler": list(records),
    )


def _profile(monkeypatch, profile):
    monkeypatch.setattr(
        "tripplanner.tools.user_preferences.load_preferences",
        lambda: {"profile": dict(profile)},
    )


def test_passport_country_from_saved_passport(monkeypatch):
    _no_documents(
        monkeypatch,
        [
            {"type": "passport", "traveller_key": "self", "fields": {"issuing_country": "India"}},
            {"type": "insurance", "traveller_key": "self", "fields": {"issuing_country": "Spain"}},
        ],
    )
    _profile(monkeypatch, {"home_country": "Portugal"})
    assert visa._known_passport_country() == ("India", "saved passport", ["India"])


def test_passport_country_falls_back_to_nationality_field(monkeypatch):
    _no_documents(
        monkeypatch,
        [{"type": "passport", "traveller_key": "self", "fields": {"nationality": "British"}}],
    )
    _profile(monkeypatch, {})
    assert visa._known_passport_country()[0] == "British"


def test_passport_country_ignores_other_travellers(monkeypatch):
    _no_documents(
        monkeypatch,
        [
            {
                "type": "passport",
                "traveller_key": "spouse:asha",
                "fields": {"issuing_country": "India"},
            }
        ],
    )
    _profile(monkeypatch, {})
    assert visa._known_passport_country() == ("", "unknown", [])


def test_two_passports_are_ambiguous(monkeypatch):
    _no_documents(
        monkeypatch,
        [
            {"type": "passport", "traveller_key": "self", "fields": {"issuing_country": "India"}},
            {
                "type": "passport",
                "traveller_key": "self",
                "fields": {"issuing_country": "United States"},
            },
        ],
    )
    _profile(monkeypatch, {"passport_country": "Indian"})
    country, source, candidates = visa._known_passport_country()
    assert country == ""
    assert source == "multiple saved passports"
    assert candidates == ["India", "United States"]


def test_passport_country_from_stated_profile(monkeypatch):
    _no_documents(monkeypatch)
    _profile(monkeypatch, {"passport_country": "Indian", "home_country": "Singapore"})
    assert visa._known_passport_country() == ("Indian", "stated profile", ["Indian"])


def test_residence_is_never_used_as_passport_country(monkeypatch):
    _no_documents(monkeypatch)
    _profile(monkeypatch, {"home_country": "India", "home_city": "Bengaluru"})
    assert visa._known_passport_country() == ("", "unknown", [])


def test_visa_asks_once_when_passport_country_unknown(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: True)
    monkeypatch.setattr(visa, "_known_passport_country", lambda: ("", "unknown", []))

    def boom(*a, **k):
        raise AssertionError("must not search without a passport country")

    monkeypatch.setattr(visa, "search_raw", boom)
    out = visa.check_visa_requirements.invoke({"destination_country": "Mexico"})
    assert "update_user_profile(passport_country=" in out
    assert "which passport they will travel on" in out


def test_visa_ask_names_the_saved_passports(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: True)
    monkeypatch.setattr(
        visa, "_known_passport_country", lambda: ("", "multiple saved passports", ["India", "US"])
    )
    out = visa.check_visa_requirements.invoke({"destination_country": "Mexico"})
    assert "India or US" in out


def test_visa_uses_saved_passport_without_being_told(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: True)
    monkeypatch.setattr(
        visa, "_known_passport_country", lambda: ("India", "saved passport", ["India"])
    )
    seen = {}

    def fake_search_raw(query, max_results, search_depth):
        seen["query"] = query
        return {"answer": "", "results": []}

    monkeypatch.setattr(visa, "search_raw", fake_search_raw)
    out = json.loads(visa.check_visa_requirements.invoke({"destination_country": "Mexico"}))
    assert "India passport holders" in seen["query"]
    assert out["passport_country"] == "India"
    assert out["passport_country_source"] == "saved passport"


def test_explicit_passport_country_wins(monkeypatch):
    monkeypatch.setattr(visa, "is_configured", lambda: True)
    monkeypatch.setattr(
        visa,
        "_known_passport_country",
        lambda: (_ for _ in ()).throw(AssertionError("should not resolve")),
    )
    monkeypatch.setattr(visa, "search_raw", lambda *a, **k: {"answer": "", "results": []})
    out = json.loads(
        visa.check_visa_requirements.invoke(
            {"passport_country": "British", "destination_country": "Mexico"}
        )
    )
    assert out["passport_country"] == "British"
    assert out["passport_country_source"] == "provided"


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
