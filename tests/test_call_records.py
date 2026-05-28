"""Tests for call records parser."""

import json
import tempfile
from pathlib import Path

from multiagent.tools.call_records_parser import CallRecordParser


def test_parse_csv():
    csv_content = """\
number,name,type,date,duration
+1234567890,John Doe,Incoming,2024-01-15 14:30,120
+0987654321,Jane Smith,Missed,2024-01-15 15:00,0
+1112223333,Bob,Outgoing,2024-01-15 16:00,300
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        f.flush()
        parser = CallRecordParser()
        records = parser.parse_csv(f.name)

    assert len(records) == 3
    assert records[0].contact_name == "John Doe"
    assert records[0].call_type == "incoming"
    assert records[1].call_type == "missed"
    assert records[2].call_type == "outgoing"
    assert records[2].duration_seconds == 300


def test_parse_google_takeout_json():
    takeout_data = [
        {"phoneNumber": "+1234567890", "name": "Dr. Smith", "callType": "MISSED", "timestamp": "2024-01-15T10:00:00Z", "duration": 0},
        {"phoneNumber": "+0987654321", "name": "Mom", "callType": "INCOMING", "timestamp": "2024-01-15T11:00:00Z", "duration": 600},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(takeout_data, f)
        f.flush()
        parser = CallRecordParser()
        records = parser.parse_google_takeout(f.name)

    assert len(records) == 2
    assert records[0].call_type == "missed"
    assert records[0].contact_name == "Dr. Smith"
    assert records[1].duration_seconds == 600


def test_normalize_call_type():
    parser = CallRecordParser()
    assert parser._normalize_call_type("MISSED") == "missed"
    assert parser._normalize_call_type("Outgoing") == "outgoing"
    assert parser._normalize_call_type("Incoming") == "incoming"
    assert parser._normalize_call_type("Received") == "incoming"
    assert parser._normalize_call_type("Rejected") == "rejected"


def test_parse_duration():
    parser = CallRecordParser()
    assert parser._parse_duration("120") == 120
    assert parser._parse_duration("1:30") == 90
    assert parser._parse_duration("bad") == 0


def test_fetch_as_text_no_data():
    parser = CallRecordParser(data_dir="nonexistent_dir_12345")
    text = parser.fetch_as_text()
    assert "No call records" in text
