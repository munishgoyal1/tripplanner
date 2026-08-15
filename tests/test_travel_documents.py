from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tripplanner import storage_cosmos
from tripplanner.user_context import set_user_id
from tripplanner.web import travel_documents


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    root = Path.home() / f".tripplanner_test_documents-{os.getpid()}"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(travel_documents, "_DOCS_FILE", root / "documents.json")
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    set_user_id("local")
    yield
    shutil.rmtree(root, ignore_errors=True)


def _passport(**overrides):
    record = {
        "type": "passport",
        "traveller_key": "self",
        "traveller_name": "Munish",
        "fields": {
            "holder_name": "Munish Kumar",
            "issuing_country": "India",
            "number_last4": "Z 148 7392",
            "expiry": "2031-04-02",
        },
        "provenance": {"source_kind": "image", "confidence": 0.96},
    }
    record.update(overrides)
    return record


class TestMasking:
    def test_identity_number_keeps_only_last_four(self):
        assert travel_documents.mask_identity_number("Z 148 7392") == "7392"

    def test_masking_ignores_punctuation(self):
        assert travel_documents.mask_identity_number("AB-12-34-56 X") == "456X"

    def test_empty_number_masks_to_empty(self):
        assert travel_documents.mask_identity_number(None) == ""

    def test_full_number_never_survives_a_save(self):
        stored = travel_documents.save_document(_passport())
        assert stored["fields"]["number_last4"] == "7392"
        serialized = str(travel_documents.list_documents())
        assert "1487392" not in serialized
        assert "Z 148 7392" not in serialized


class TestFieldAllowlist:
    def test_undeclared_fields_are_dropped(self):
        fields = travel_documents.sanitize_fields(
            "passport",
            {"expiry": "2031-04-02", "blob_path": "/tmp/scan.jpg", "mrz": "P<INDKUMAR<<MUNISH"},
        )
        assert fields == {"expiry": "2031-04-02"}

    def test_raw_number_is_folded_into_the_masked_field(self):
        fields = travel_documents.sanitize_fields("passport", {"number": "Z1487392"})
        assert fields == {"number_last4": "7392"}

    def test_non_iso_dates_are_discarded_rather_than_guessed(self):
        fields = travel_documents.sanitize_fields(
            "passport", {"expiry": "2 April 2031", "issuing_country": "India"}
        )
        assert fields == {"issuing_country": "India"}

    def test_unknown_type_is_refused(self):
        with pytest.raises(travel_documents.DocumentError):
            travel_documents.sanitize_fields("bank_card", {"number": "4111111111111111"})


class TestStorage:
    def test_save_then_list_round_trips(self):
        stored = travel_documents.save_document(_passport())
        rows = travel_documents.list_documents()
        assert [row["id"] for row in rows] == [stored["id"]]
        assert rows[0]["fields"]["issuing_country"] == "India"
        assert rows[0]["status"] == "ready"

    def test_saving_the_same_id_updates_in_place(self):
        first = travel_documents.save_document(_passport())
        updated = dict(_passport(), id=first["id"])
        updated["fields"] = dict(updated["fields"], expiry="2032-01-01")
        travel_documents.save_document(updated)
        rows = travel_documents.list_documents()
        assert len(rows) == 1
        assert rows[0]["fields"]["expiry"] == "2032-01-01"
        assert rows[0]["created_at"] == first["created_at"]

    def test_a_record_never_references_a_file(self):
        stored = travel_documents.save_document(_passport())
        assert "blob_path" not in stored
        assert not any("path" in key for key in stored["fields"])

    def test_delete_removes_only_the_named_record(self):
        first = travel_documents.save_document(_passport())
        travel_documents.save_document(_passport(traveller_key="spouse:priya"))
        assert travel_documents.delete_document(first["id"]) is True
        rows = travel_documents.list_documents()
        assert len(rows) == 1
        assert rows[0]["traveller_key"] == "spouse:priya"

    def test_deleting_an_unknown_record_reports_nothing_removed(self):
        assert travel_documents.delete_document("doc-missing") is False

    def test_clear_all_reports_the_count_removed(self):
        travel_documents.save_document(_passport())
        travel_documents.save_document(_passport(traveller_key="spouse:priya"))
        assert travel_documents.clear_all_documents() == 2
        assert travel_documents.list_documents() == []

    def test_a_record_with_nothing_readable_is_refused(self):
        with pytest.raises(travel_documents.DocumentError):
            travel_documents.save_document(_passport(fields={"mrz": "P<IND"}))


class TestTravellerKey:
    def test_key_is_case_insensitive(self):
        assert travel_documents.traveller_key("Spouse", "Priya") == travel_documents.traveller_key(
            "spouse", "priya"
        )

    def test_missing_name_is_the_account_holder(self):
        assert travel_documents.traveller_key("self", "") == "self"
