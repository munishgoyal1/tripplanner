"""Tests for WhatsApp chat parser."""

import tempfile
from pathlib import Path

from multiagent.tools.whatsapp_parser import WhatsAppParser


SAMPLE_CHAT = """\
[1/15/23, 2:30:45 PM] John Doe: Hey, can you send me the report by Friday?
[1/15/23, 2:31:00 PM] You: Sure, I'll get it done
[1/15/23, 2:32:10 PM] John Doe: Also please call the dentist to reschedule
[1/15/23, 2:33:00 PM] John Doe: Thanks!
"""

SAMPLE_CHAT_24H = """\
15/01/23, 14:30 - John: Hey, reminder about the meeting tomorrow
15/01/23, 14:31 - You: Got it, thanks
"""


def test_parse_12h_format():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(SAMPLE_CHAT)
        f.flush()
        parser = WhatsAppParser()
        messages = parser.parse_file(f.name)

    assert len(messages) == 4
    assert messages[0].sender == "John Doe"
    assert "report" in messages[0].text
    assert messages[2].sender == "John Doe"
    assert "dentist" in messages[2].text


def test_parse_24h_format():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(SAMPLE_CHAT_24H)
        f.flush()
        parser = WhatsAppParser()
        messages = parser.parse_file(f.name)

    assert len(messages) == 2
    assert messages[0].sender == "John"
    assert "meeting" in messages[0].text


def test_parse_nonexistent_file():
    parser = WhatsAppParser()
    messages = parser.parse_file("nonexistent_chat.txt")
    assert messages == []


def test_fetch_as_text_no_data():
    parser = WhatsAppParser(exports_dir="nonexistent_dir_12345")
    text = parser.fetch_as_text()
    assert "No WhatsApp" in text
