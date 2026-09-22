"""The access probe must report what the account actually answered, or refuse to run."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tripplanner.providers.models import HotelOffer, Money, QuoteStatus

SCRIPT = Path(__file__).parents[1] / "scripts" / "liteapi_access_probe.py"


def load_probe():
    spec = importlib.util.spec_from_file_location("liteapi_access_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Dataclass field resolution needs the module registered before it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def args(probe, **overrides):
    parsed = probe.argparse.Namespace(
        capability="hotels",
        city="Goa",
        checkin="2026-12-01",
        checkout="2026-12-03",
        origin="DEL",
        destination="GOI",
        departure_date="2026-12-01",
        return_date="",
        adults=2,
        rooms=1,
        children_ages=[],
        nationality="IN",
        currency="INR",
        cabin="ECONOMY",
        max_results=5,
        markdown=False,
        out="",
    )
    for key, value in overrides.items():
        setattr(parsed, key, value)
    return parsed


def offer() -> HotelOffer:
    return HotelOffer(
        provider="liteapi",
        provider_ref={"rate_id": "opaque-handle"},
        hotel_name="Garden Hotel",
        search_destination="Goa",
        room_name="Double",
        total=Money(amount=70000, currency="INR", mandatory_costs_complete=True, all_in=True),
        quoted_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        status=QuoteStatus.LIVE,
    )


def test_a_denial_is_recorded_as_evidence_rather_than_retried(monkeypatch):
    probe = load_probe()

    class Denied:
        def search_hotels(self, query):
            raise RuntimeError("403 Forbidden: hotel search is not entitled for this account")

    monkeypatch.setattr(probe, "get_hotel_provider", lambda: Denied())
    result = probe.probe_hotels(args(probe))
    assert result.outcome == "denied_or_failed"
    assert "403" in result.detail and "RuntimeError" in result.detail
    assert result.offers == 0 and result.evidence == {}


def test_offer_evidence_summarizes_freshness_and_links_without_opaque_handles(monkeypatch):
    probe = load_probe()
    monkeypatch.setattr(
        probe, "get_hotel_provider", lambda: type("P", (), {"search_hotels": lambda s, q: [offer()]})()
    )
    result = probe.probe_hotels(args(probe))
    assert result.outcome == "answered_with_offers" and result.offers == 1
    assert result.evidence["currencies"] == ["INR"]
    assert result.evidence["mandatory_costs_complete"] == 1
    assert result.evidence["carries_expiry"] == 1
    # LiteAPI hotel offers carry no link, which is why rows stay copy-the-details.
    assert result.evidence["carries_url"] == 0

    block = probe.markdown([result], "https://api.liteapi.travel/v3.0", "2026-09-22T10:00:00+00:00")
    assert "not vendor permission" in block and "opaque-handle" not in block
    assert "hotel_search | answered_with_offers" in block


def test_an_empty_answer_is_not_a_failure_and_no_provider_is(monkeypatch):
    probe = load_probe()
    monkeypatch.setattr(
        probe, "get_hotel_provider", lambda: type("P", (), {"search_hotels": lambda s, q: []})()
    )
    assert probe.probe_hotels(args(probe)).outcome == "answered_empty"

    monkeypatch.setattr(probe, "get_hotel_provider", lambda: None)
    missing = probe.probe_hotels(args(probe))
    assert missing.outcome == "not_configured"


def test_the_probe_refuses_to_run_without_a_configured_key(monkeypatch, capsys):
    probe = load_probe()
    monkeypatch.setattr(probe, "get_settings", lambda: type("S", (), {"liteapi_api_key": ""})())
    monkeypatch.setattr(
        probe.argparse.ArgumentParser, "parse_args", lambda self, *a, **k: args(probe)
    )
    with pytest.raises(SystemExit) as exit_info:
        raise SystemExit(probe.main())
    assert exit_info.value.code == 2
    assert "LITEAPI_API_KEY is not set" in capsys.readouterr().out
