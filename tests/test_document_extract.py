from __future__ import annotations

import base64

import pytest

from tripplanner.web import document_extract

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"


class TestContentSniffing:
    def test_a_jpeg_is_recognised_by_its_bytes(self):
        assert document_extract.detect_image_type(JPEG) == "image/jpeg"

    def test_a_png_is_recognised_by_its_bytes(self):
        assert document_extract.detect_image_type(PNG) == "image/png"

    def test_a_heic_is_recognised_by_its_brand(self):
        assert document_extract.detect_image_type(HEIC) == "image/heic"

    def test_a_jpeg_name_on_an_svg_does_not_help_it(self):
        with pytest.raises(document_extract.ExtractionError, match="web file"):
            document_extract.detect_image_type(b'<svg xmlns="http://www.w3.org/2000/svg">')

    def test_html_is_refused(self):
        with pytest.raises(document_extract.ExtractionError, match="web file"):
            document_extract.detect_image_type(b"<!DOCTYPE html><html><body>hi</body>")

    def test_an_archive_is_refused(self):
        with pytest.raises(document_extract.ExtractionError, match="archive"):
            document_extract.detect_image_type(b"PK\x03\x04" + b"\x00" * 16)

    def test_an_executable_is_refused(self):
        with pytest.raises(document_extract.ExtractionError, match="archive or a program"):
            document_extract.detect_image_type(b"MZ\x90\x00" + b"\x00" * 16)

    def test_a_pdf_is_refused_with_a_reason_rather_than_guessed_at(self):
        with pytest.raises(document_extract.ExtractionError, match="PDFs are not read yet"):
            document_extract.detect_image_type(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3")


class TestPayloadLimits:
    def test_an_oversized_upload_is_refused(self):
        oversized = base64.b64encode(b"\x00" * (document_extract.MAX_BYTES + 1)).decode()
        with pytest.raises(document_extract.ExtractionError, match="larger than 6 MB"):
            document_extract.decode_payload(oversized)

    def test_an_empty_upload_is_refused(self):
        with pytest.raises(document_extract.ExtractionError, match="empty"):
            document_extract.decode_payload("")

    def test_undecodable_input_is_refused(self):
        with pytest.raises(document_extract.ExtractionError, match="could not be decoded"):
            document_extract.decode_payload("not base64 !!!")


class TestProposals:
    def test_an_unknown_document_type_is_refused_before_any_model_call(self):
        with pytest.raises(document_extract.ExtractionError, match="Unknown document type"):
            document_extract.extract("bank_card", text="4111 1111 1111 1111")

    def test_empty_input_is_refused_before_any_model_call(self):
        with pytest.raises(document_extract.ExtractionError, match="photo or paste"):
            document_extract.extract("passport", text="   ")

    def test_proposals_carry_a_label_confidence_and_masking_flag(self, monkeypatch):
        monkeypatch.setattr(
            document_extract,
            "_invoke",
            lambda kind, content: {
                "fields": {"number": "Z1487392", "expiry": "2031-04-02", "mrz": "P<IND"},
                "confidence": {"number_last4": 0.94, "expiry": 0.99},
            },
        )
        result = document_extract.extract("passport", text="passport text")
        by_key = {field["key"]: field for field in result["fields"]}
        assert set(by_key) == {"number_last4", "expiry"}
        assert by_key["number_last4"]["value"] == "7392"
        assert by_key["number_last4"]["masked"] is True
        assert by_key["expiry"]["confidence"] == 0.99
        assert by_key["expiry"]["label"] == "Expiry"
        assert result["source_kind"] == "text"

    def test_a_read_that_finds_nothing_reports_it_rather_than_saving(self, monkeypatch):
        monkeypatch.setattr(document_extract, "_invoke", lambda kind, content: {"fields": {}})
        with pytest.raises(document_extract.ExtractionError, match="Nothing readable"):
            document_extract.extract("passport", text="blurry")
