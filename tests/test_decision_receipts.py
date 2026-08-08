from __future__ import annotations

import json
from datetime import datetime, timedelta

from tripplanner.decisions.provenance import (
    build_provenance,
    describe,
    is_expired,
    make_check,
    record_check,
)
from tripplanner.decisions.receipts import receipt_for


def _comparison_output(**extra) -> str:
    payload = {
        "decision_id": "dec_transport_lisbon_porto_2026_05_04",
        "subject": "Lisbon to Porto",
        "chosen": "Train",
        "priced": "full",
        "options": [
            {"id": "opt_train", "label": "Train"},
            {"id": "opt_road", "label": "Drive"},
            {"id": "opt_flight", "label": "Flight"},
        ],
    }
    payload.update(extra)
    return json.dumps(payload)


def test_comparison_receipt_reports_what_was_compared():
    receipt = receipt_for("compare_transport_options", _comparison_output())
    assert receipt is not None
    assert receipt.kind == "transport"
    assert receipt.text == "Compared 3 ways from Lisbon to Porto"
    assert receipt.detail == "train picked, 2 rejected"
    assert receipt.decision_id == "dec_transport_lisbon_porto_2026_05_04"
    assert receipt.priced == "full"


def test_prose_refusal_produces_no_receipt():
    assert receipt_for("compare_transport_options", "Too short to be worth comparing.") is None


def test_comparison_without_a_decision_produces_no_receipt():
    assert receipt_for("compare_transport_options", json.dumps({"options": []})) is None


def test_unmapped_tool_produces_no_receipt():
    assert receipt_for("update_trip_plan", "saved") is None


def test_fixed_tool_names_its_source():
    receipt = receipt_for("search_places_with_reviews", "anything at all")
    assert receipt is not None
    assert receipt.source == "Google Places"
    assert receipt.kind == "places"


def test_receipt_dict_omits_empty_fields():
    receipt = receipt_for("web_search", "results")
    assert receipt is not None
    payload = receipt.as_dict()
    assert set(payload) == {"kind", "text", "source"}


def test_price_check_records_one_row_per_source():
    plan: dict = {}
    record_check(plan, make_check("flights", "Duffel"))
    record_check(plan, make_check("flights", "Duffel"))
    record_check(plan, make_check("lodging", "LiteAPI"))
    assert len(plan["price_checks"]) == 2


def test_expired_check_is_never_described_as_current():
    now = datetime(2026, 5, 4, 9, 0)
    check = make_check("flights", "Duffel", now=now).as_dict()
    later = now + timedelta(hours=2)
    assert is_expired(check, now=later)
    assert "may have changed" in describe(check, now=later)
    assert "may have changed" not in describe(check, now=now)


def test_check_without_expiry_is_treated_as_expired():
    assert is_expired({"provider": "Duffel", "checked_at": "2026-05-04T09:00:00"})


def test_provenance_rows_carry_freshness_and_text():
    now = datetime(2026, 5, 4, 9, 0)
    plan: dict = {}
    record_check(plan, make_check("lodging", "LiteAPI", now=now))
    rows = build_provenance(plan, now=now)
    assert rows == [
        {
            "kind": "lodging",
            "provider": "LiteAPI",
            "checked_at": "2026-05-04T09:00:00",
            "expires_at": "2026-05-04T21:00:00",
            "current": True,
            "text": "Stays priced from LiteAPI on 04 May 09:00.",
        }
    ]


def test_provenance_ignores_malformed_rows():
    assert build_provenance({"price_checks": ["nonsense", {"kind": "flights"}]}) == []
