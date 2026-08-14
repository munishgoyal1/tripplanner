"""The holiday calendar must fail as unknown, never as an empty year.

A dropped request that cached itself as "no holidays" would silently restore the
exact confidence this feature exists to remove, so the distinction between an
empty answer and no answer is what these tests are mostly about.
"""

from __future__ import annotations

import httpx
import pytest

from tripplanner.web import holidays


class _Response:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> object:
        return self._payload


_ROWS = [
    {"date": "2026-08-15", "localName": "Independence Day", "name": "Independence Day",
     "global": True},
    {"date": "2026-10-02", "localName": "Gandhi Jayanti", "name": "Gandhi Jayanti",
     "global": True},
    {"date": "2026-04-14", "localName": "Regional Feast", "name": "Regional Feast",
     "global": False},
]


@pytest.fixture(autouse=True)
def _clean() -> None:
    holidays.reset_cache()
    yield
    holidays.reset_cache()


def test_a_named_holiday_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(holidays.http_client, "get", lambda *a, **k: _Response(_ROWS))
    assert holidays.holiday_on("IN", "2026-08-15") == "Independence Day"


def test_an_ordinary_day_is_an_answer_not_a_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(holidays.http_client, "get", lambda *a, **k: _Response(_ROWS))
    assert holidays.holiday_on("IN", "2026-08-16") == ""


def test_a_regional_holiday_says_nothing_about_this_city(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(holidays.http_client, "get", lambda *a, **k: _Response(_ROWS))
    assert holidays.holiday_on("IN", "2026-04-14") == ""


def test_a_failed_lookup_is_unknown_and_is_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def failing(url: str, **_kwargs: object) -> _Response:
        calls.append(url)
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(holidays.http_client, "get", failing)
    assert holidays.holiday_on("IN", "2026-08-15") is None
    assert holidays.holiday_on("IN", "2026-08-15") is None
    assert len(calls) == 2


def test_a_country_the_source_does_not_cover_is_a_known_empty_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(holidays.http_client, "get", lambda *a, **k: _Response([], 404))
    assert holidays.holiday_on("XX", "2026-08-15") == ""


def test_a_successful_year_is_fetched_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def counting(url: str, **_kwargs: object) -> _Response:
        calls.append(url)
        return _Response(_ROWS)

    monkeypatch.setattr(holidays.http_client, "get", counting)
    holidays.holiday_on("IN", "2026-08-15")
    holidays.holiday_on("IN", "2026-10-02")
    assert len(calls) == 1


def test_a_nonsense_country_or_date_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(holidays.http_client, "get", lambda *a, **k: _Response(_ROWS))
    assert holidays.holiday_on("", "2026-08-15") is None
    assert holidays.holiday_on("India", "2026-08-15") is None
    assert holidays.holiday_on("IN", "not-a-date") is None
