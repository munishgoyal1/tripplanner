from __future__ import annotations

import httpx
import pytest

from tripplanner import http_client
from tripplanner.web import place_country


@pytest.fixture(autouse=True)
def _clean_cache():
    place_country.reset_cache()
    yield
    place_country.reset_cache()


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestCandidates:
    def test_the_whole_string_is_tried_before_its_parts(self):
        assert place_country._candidates("Lisbon, Portugal")[0] == "Lisbon, Portugal"

    def test_the_most_specific_trailing_part_comes_next(self):
        assert place_country._candidates("Lisbon, Portugal")[1] == "Portugal"

    def test_a_repeated_part_is_only_tried_once(self):
        assert place_country._candidates("Portugal, portugal") == ["Portugal, portugal", "portugal"]

    def test_an_empty_place_has_nothing_to_try(self):
        assert place_country._candidates("   ") == []


class TestResolveCountry:
    def test_a_match_returns_the_country(self, monkeypatch):
        def fake_get(url, **kwargs):
            return _Response(
                {"results": [{"name": "Lisbon", "country": "Portugal", "population": 517802}]}
            )

        monkeypatch.setattr(http_client, "get", fake_get)
        assert place_country.resolve_country("Lisbon") == "Portugal"

    def test_a_repeat_lookup_is_served_from_the_cache(self, monkeypatch):
        calls = []

        def fake_get(url, **kwargs):
            calls.append(kwargs)
            return _Response(
                {"results": [{"name": "Lisbon", "country": "Portugal", "population": 517802}]}
            )

        monkeypatch.setattr(http_client, "get", fake_get)
        place_country.resolve_country("Lisbon")
        place_country.resolve_country("lisbon")
        assert len(calls) == 1

    def test_a_geocoder_with_no_answer_is_remembered(self, monkeypatch):
        calls = []

        def fake_get(url, **kwargs):
            calls.append(kwargs)
            return _Response({"results": []})

        monkeypatch.setattr(http_client, "get", fake_get)
        assert place_country.resolve_country("Nowhereville") == ""
        place_country.resolve_country("Nowhereville")
        assert len(calls) == 1

    def test_a_failed_lookup_is_not_remembered_as_an_answer(self, monkeypatch):
        calls = []

        def fake_get(url, **kwargs):
            calls.append(kwargs)
            raise httpx.ConnectError("offline")

        monkeypatch.setattr(http_client, "get", fake_get)
        assert place_country.resolve_country("Lisbon") == ""
        assert place_country.resolve_country("Lisbon") == ""
        assert len(calls) == 2

    def test_an_empty_place_never_calls_the_network(self, monkeypatch):
        def fail(url, **kwargs):
            raise AssertionError("should not be called")

        monkeypatch.setattr(http_client, "get", fail)
        assert place_country.resolve_country("") == ""
        assert place_country.resolve_country(None) == ""


class TestCrossesBorder:
    def test_two_countries_that_differ_cross_a_border(self):
        assert place_country.crosses_border("India", "Portugal") is True

    def test_the_same_country_does_not(self):
        assert place_country.crosses_border("India", "india") is False

    def test_an_unknown_side_stays_silent(self):
        assert place_country.crosses_border("", "Portugal") is False
        assert place_country.crosses_border("India", "") is False


class TestConfidence:
    """The geocoder matches loosely, so only a clear answer counts as one."""

    def _resolve(self, monkeypatch, place, results):
        def fake_get(url, **kwargs):
            return _Response({"results": results})

        monkeypatch.setattr(http_client, "get", fake_get)
        return place_country.resolve_country(place)

    def test_goa_is_not_italy(self, monkeypatch):
        # The real "Goa" is absent from the results; Genoa is a near-miss and
        # the Philippine municipality is not what an Indian trip means.
        assert (
            self._resolve(
                monkeypatch,
                "Goa",
                [
                    {"name": "Genoa", "country": "Italy", "population": 580097},
                    {"name": "Goa", "country": "Philippines", "population": 20936},
                    {"name": "Goa", "country": "Russia", "population": None},
                ],
            )
            == ""
        )

    def test_bangalore_is_not_pakistan(self, monkeypatch):
        assert (
            self._resolve(
                monkeypatch,
                "Bangalore",
                [{"name": "Bangalore Town", "country": "Pakistan", "population": None}],
            )
            == ""
        )

    def test_the_well_known_place_beats_its_small_namesakes(self, monkeypatch):
        assert (
            self._resolve(
                monkeypatch,
                "Paris",
                [
                    {"name": "Paris", "country": "France", "population": 2138551},
                    {"name": "Paris", "country": "United States", "population": 24782},
                ],
            )
            == "France"
        )

    def test_two_comparable_namesakes_stay_unknown(self, monkeypatch):
        assert (
            self._resolve(
                monkeypatch,
                "Tripoli",
                [
                    {"name": "Tripoli", "country": "Libya", "population": 1150989},
                    {"name": "Tripoli", "country": "Lebanon", "population": 731000},
                ],
            )
            == ""
        )

    def test_accents_do_not_hide_a_match(self, monkeypatch):
        assert (
            self._resolve(
                monkeypatch,
                "Malaga",
                [{"name": "Málaga", "country": "Spain", "population": 578460}],
            )
            == "Spain"
        )

    def test_a_country_name_resolves_to_itself(self, monkeypatch):
        assert (
            self._resolve(
                monkeypatch,
                "India",
                [
                    {"name": "India", "country": "India", "population": 1352617328},
                    {"name": "India", "country": "The Gambia", "population": 529},
                ],
            )
            == "India"
        )
