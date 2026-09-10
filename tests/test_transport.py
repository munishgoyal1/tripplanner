"""Tests for tripplanner.web.transport's transfer-mode resolution.

_resolved_transfer_mode is the map-rendering classification used by
day_journey.py, itinerary_view.py, and map_pins.py to decide whether a
transport stop opens an intercity leg (pin + road-circuit connection) or
stays part of a local, closed-circuit day. It's deliberately separate from
_intercity_transfer_mode, which _canonical_transport_name still uses
unchanged to decide whether raw text already names its own mode.
"""

from __future__ import annotations

from tripplanner.web.transport import _intercity_transfer_mode, _resolved_transfer_mode


def test_unlabeled_two_place_transport_stop_defaults_to_drive():
    assert _resolved_transfer_mode("Srinagar to Gulmarg", "transport") == "Drive"


def test_explicit_keyword_passes_through_unchanged():
    for name, expected in (
        ("Flight: Delhi to Srinagar", "Flight"),
        ("Train: Delhi to Agra", "Train"),
        ("Bus: Manali to Leh", "Bus"),
        ("Drive: Bangalore to Coorg", "Drive"),
    ):
        assert _resolved_transfer_mode(name, "transport") == expected
        # And the fallback agrees with the explicit keyword either way.
        assert _intercity_transfer_mode(name, "transport") == expected


def test_local_taxi_round_trip_is_not_promoted_to_intercity():
    """A same-destination taxi hop ("Taxi: Hotel to Fort Aguada") must stay
    local -- it names two places in travel order just like an intercity leg,
    but "Taxi" is an explicit local-only signal."""
    assert _resolved_transfer_mode("Taxi: Taj Exotica Resort to Fort Aguada", "transport") is None
    assert _resolved_transfer_mode("Walking tour: Old Town to Harbor", "transport") is None


def test_non_transport_kind_never_defaults():
    assert _resolved_transfer_mode("Srinagar to Gulmarg", "attraction") is None
    assert _resolved_transfer_mode("Srinagar to Gulmarg", "hotel") is None


def test_single_place_name_has_nothing_to_default():
    assert _resolved_transfer_mode("Gulmarg Cottage", "transport") is None


def test_flight_kind_still_resolves_to_flight():
    assert _resolved_transfer_mode("Delhi to Srinagar", "flight") == "Flight"
