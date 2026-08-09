"""The fare port, and the honest absence of a source."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tripplanner.decisions.models import FareBasis, TransportMode, UnpricedReason
from tripplanner.providers import fares
from tripplanner.providers.fares import FareQuote, FareRequest, quote_fare


class StubSource:
    def __init__(self, name, modes, quote_value=None, raises=False):
        self.name = name
        self.modes = frozenset(modes)
        self._quote = quote_value
        self._raises = raises
        self.calls = 0

    def quote(self, request: FareRequest):
        self.calls += 1
        if self._raises:
            raise RuntimeError("provider down")
        return self._quote


@pytest.fixture(autouse=True)
def no_ambient_ground_providers(monkeypatch):
    """These tests cover the source chain, not whichever provider .env happens to configure."""
    for getter in ("get_train_provider", "get_coach_provider", "get_ferry_provider"):
        monkeypatch.setattr(fares, getter, lambda: None)
    # The fare cache is process-global; one test's stub quote must not answer the next.
    fares._FARE_CACHE.clear()
    yield
    fares._FARE_CACHE.clear()


@pytest.fixture
def request_for_train():
    return FareRequest(
        mode=TransportMode.TRAIN,
        from_place="Lisbon",
        to_place="Porto",
        date="2026-05-04",
        travellers=2,
        currency="EUR",
    )


@pytest.fixture
def clean_registry():
    added: list[str] = []

    def add(source):
        fares.register_source(source)
        added.append(source.name)
        return source

    yield add
    for name in added:
        fares.unregister_source(name)


def test_rail_is_unpriced_when_its_registered_source_cannot_cover_the_route(request_for_train):
    # A rail source is registered, so the honest answer is "not covered", not "no source".
    quote, reason = quote_fare(request_for_train)
    assert quote is None
    assert reason is UnpricedReason.OUT_OF_COVERAGE


def test_a_registered_source_prices_the_hop(request_for_train, clean_registry):
    clean_registry(
        StubSource(
            "stub-rail",
            {TransportMode.TRAIN},
            FareQuote(
                amount=39.5,
                currency="EUR",
                provider="stub-rail",
                basis=FareBasis.PER_TRAVELLER,
                checked_at=datetime.now(UTC),
            ),
        )
    )
    quote, reason = quote_fare(request_for_train)
    assert reason is None
    assert quote is not None
    assert quote.amount == 39.5
    assert quote.provider == "stub-rail"


def test_a_failing_source_degrades_to_unpriced_instead_of_raising(
    request_for_train, clean_registry
):
    clean_registry(StubSource("broken", {TransportMode.TRAIN}, raises=True))
    quote, reason = quote_fare(request_for_train)
    assert quote is None
    assert reason is UnpricedReason.SOURCE_FAILED


def test_the_next_source_is_tried_when_the_first_declines(request_for_train, clean_registry):
    second = clean_registry(
        StubSource(
            "backup",
            {TransportMode.TRAIN},
            FareQuote(amount=42, currency="EUR", provider="backup"),
        )
    )
    first = clean_registry(StubSource("primary", {TransportMode.TRAIN}, None))
    quote, _ = quote_fare(request_for_train)
    assert first.calls == 1
    assert second.calls == 1
    assert quote is not None
    assert quote.provider == "backup"


def test_a_source_is_not_asked_about_a_mode_it_does_not_cover(request_for_train, clean_registry):
    ferry_only = clean_registry(
        StubSource(
            "ferries",
            {TransportMode.FERRY},
            FareQuote(amount=10, currency="EUR", provider="ferries"),
        )
    )
    quote, reason = quote_fare(request_for_train)
    assert ferry_only.calls == 0
    assert quote is None
    assert reason is UnpricedReason.OUT_OF_COVERAGE


def test_a_range_quote_keeps_its_upper_bound():
    quote = FareQuote(amount=25, amount_max=60, currency="EUR", provider="aggregator")
    assert quote.amount_max == 60
