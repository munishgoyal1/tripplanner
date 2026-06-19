"""Tests for src/tripplanner/observability.py -- PII redaction and the two
log streams (app log + audit log)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tripplanner import observability as obs


@pytest.fixture(autouse=True)
def _isolate_audit_dir(tmp_path, monkeypatch):
    """Point the local audit sink at a temp dir so tests don't write to
    ~/.tripplanner/audit."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    yield


# ---------------------------------------------------------------------------
# redact_text
# ---------------------------------------------------------------------------


def test_redact_email():
    assert obs.redact_text("contact me at alice@example.com today") == (
        "contact me at <email> today"
    )


def test_redact_phone():
    out = obs.redact_text("call +91 98765 43210 please")
    assert "<phone>" in out
    assert "98765" not in out


def test_redact_bearer_token():
    out = obs.redact_text("Authorization: Bearer abc.def-ghi_jkl")
    assert "Bearer <token>" in out
    assert "abc.def-ghi_jkl" not in out


def test_redact_api_key_in_text():
    out = obs.redact_text("api_key=sk_test_abcdefghijklmnop1234")
    assert "<redacted>" in out
    assert "sk_test_abcdefghijklmnop1234" not in out


def test_redact_credit_card():
    out = obs.redact_text("card 4111 1111 1111 1111 expires soon")
    assert "<card>" in out
    assert "4111" not in out


def test_redact_ipv4():
    out = obs.redact_text("client 203.0.113.42 connected")
    assert "<ip>" in out
    assert "203.0.113.42" not in out


def test_redact_non_string_passthrough():
    assert obs.redact_text(42) == 42
    assert obs.redact_text(None) is None


def test_redact_value_recurses_dict_and_list():
    payload = {
        "outer": {"inner": "ping me at bob@host.io"},
        "tags": ["normal", "call 9876543210 now"],
    }
    out = obs.redact_value(payload)
    assert out["outer"]["inner"] == "ping me at <email>"
    assert "<phone>" in out["tags"][1]


# ---------------------------------------------------------------------------
# hash_user_id
# ---------------------------------------------------------------------------


def test_hash_user_id_is_stable():
    assert obs.hash_user_id("google-12345") == obs.hash_user_id("google-12345")


def test_hash_user_id_does_not_leak_input():
    h = obs.hash_user_id("munishgoyal1@gmail.com")
    assert h.startswith("u_")
    assert "munish" not in h
    assert "@" not in h
    assert len(h) == len("u_") + 12


def test_hash_user_id_anon_when_blank():
    assert obs.hash_user_id(None) == "anon"
    assert obs.hash_user_id("") == "anon"


# ---------------------------------------------------------------------------
# PiiRedactingFilter (mutates LogRecord in place)
# ---------------------------------------------------------------------------


def test_filter_scrubs_msg(capsys):
    obs.setup_logging(force=True)
    log = logging.getLogger("test.filter1")
    log.info("user signed up: jane@doe.com from 10.0.0.5")
    out = capsys.readouterr().out
    assert "<email>" in out
    assert "<ip>" in out
    assert "jane@doe.com" not in out
    assert "10.0.0.5" not in out


def test_filter_scrubs_args(capsys):
    obs.setup_logging(force=True)
    log = logging.getLogger("test.filter2")
    log.info("contact = %s", "bob@host.io")
    out = capsys.readouterr().out
    assert "<email>" in out
    assert "bob@host.io" not in out


# ---------------------------------------------------------------------------
# JsonFormatter + app_event end-to-end
# ---------------------------------------------------------------------------


def _emit_and_parse(capsys, kind: str, **fields):
    obs.setup_logging(force=True)
    # Switch to JSON formatter regardless of env -- mirror what we do hosted.
    handler = logging.getLogger().handlers[0]
    handler.setFormatter(obs.JsonFormatter())
    obs.app_event(kind, **fields)
    out = capsys.readouterr().out.strip().splitlines()
    # Just take the last line (app_event records may be flushed last)
    return json.loads(out[-1])


def test_app_event_hashes_user_id(capsys):
    parsed = _emit_and_parse(capsys, "tool_call", user_id="google-99", tool="x", ms=12)
    assert parsed["event_kind"] == "tool_call"
    assert parsed["user"] == obs.hash_user_id("google-99")
    assert "user_id" not in parsed  # raw id never on stdout
    assert parsed["tool"] == "x"
    assert parsed["ms"] == 12


def test_app_event_drops_sensitive_field_names(capsys):
    parsed = _emit_and_parse(
        capsys,
        "user_message",
        user_id="guest-1",
        length=42,
        content="I want to fly to Goa with my wife Megha",
        email="x@y.com",
    )
    assert parsed["length"] == 42
    assert parsed["content"] == "<redacted>"
    assert parsed["email"] == "<redacted>"
    assert "Goa" not in json.dumps(parsed)
    assert "Megha" not in json.dumps(parsed)


def test_app_event_scrubs_pii_in_non_sensitive_field(capsys):
    parsed = _emit_and_parse(
        capsys,
        "external_call",
        user_id="guest-1",
        url="https://api.example.com/?token=abcdefghijklmnop1234",
    )
    assert "<redacted>" in parsed["url"]


# ---------------------------------------------------------------------------
# audit_event -- local file fallback
# ---------------------------------------------------------------------------


def test_audit_event_writes_local_jsonl_with_full_content(monkeypatch):
    # Force the Cosmos path to report "not enabled" so we exercise the
    # local-file fallback.
    from tripplanner import storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)

    obs.audit_event(
        "user_message",
        user_id="google-7",
        content="Plan 5 days in Goa for Munish and Megha",
        email="munish@example.com",
    )

    audit_dir = Path.home() / ".tripplanner" / "audit"
    files = list(audit_dir.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["kind"] == "user_message"
    assert rec["user_id"] == "google-7"
    # Audit sink preserves RAW values (no redaction).
    assert "Munish" in rec["content"]
    assert rec["email"] == "munish@example.com"
    # And it auto-stamps id + ts.
    assert "id" in rec and rec["id"]
    assert rec["ts"].endswith("Z")


def test_audit_event_kinds_are_isolated_per_user(monkeypatch):
    from tripplanner import storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)

    obs.audit_event("session_start", user_id="a")
    obs.audit_event("session_start", user_id="b")

    audit_dir = Path.home() / ".tripplanner" / "audit"
    lines = list(audit_dir.glob("*.jsonl"))[0].read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert {p["user_id"] for p in parsed} == {"a", "b"}


# ---------------------------------------------------------------------------
# audit_enabled_for_user_messages -- env switch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("val,expected", [
    ("1", True),
    ("true", True),
    ("YES", True),
    ("on", True),
    ("0", False),
    ("", False),
    ("no", False),
])
def test_audit_enabled_env_switch(monkeypatch, val, expected):
    monkeypatch.setenv("AUDIT_USER_MESSAGES", val)
    assert obs.audit_enabled_for_user_messages() is expected


def test_audit_enabled_default_off(monkeypatch):
    monkeypatch.delenv("AUDIT_USER_MESSAGES", raising=False)
    assert obs.audit_enabled_for_user_messages() is False


