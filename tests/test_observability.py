"""Tests for src/tripplanner/observability.py -- PII redaction and the two
log streams (app log + audit log)."""

from __future__ import annotations

import json
import logging
import time
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


def test_model_rate_limit_fields_whitelists_safe_headers_only():
    class Response:
        status_code = 429
        headers = {
            "retry-after-ms": "1250",
            "x-ratelimit-remaining-requests": "29",
            "x-ratelimit-remaining-tokens": "0",
            "authorization": "secret",
        }
        body = "prompt and provider response must not be logged"

    rate_limit_error_type = type("RateLimitError", (Exception,), {})
    error = rate_limit_error_type("contains private provider text")
    error.response = Response()
    error.status_code = 429
    error.code = "429"

    fields = obs.model_rate_limit_fields(error, "gpt-4-1-local")

    assert fields == {
        "model_provider": "azure_openai",
        "model_deployment": "gpt-4-1-local",
        "rate_limit_scope": "tokens",
        "provider_status": 429,
        "provider_error_code": "429",
        "retry_after_ms": 1250,
        "remaining_requests": 29,
        "remaining_tokens": 0,
    }
    assert "secret" not in json.dumps(fields)
    assert "prompt" not in json.dumps(fields)


def test_model_rate_limit_fields_ignores_other_errors():
    assert obs.model_rate_limit_fields(RuntimeError("private"), "gpt-4-1-local") == {}


def test_terminal_chat_event_includes_safe_rate_limit_details(monkeypatch):
    from tripplanner import api

    rate_limit_error_type = type("RateLimitError", (Exception,), {})
    error = rate_limit_error_type("private provider response")
    error.status_code = 429
    error.code = "rate_limit_exceeded"
    error.response = type(
        "Response",
        (),
        {
            "status_code": 429,
            "headers": {
                "retry-after": "2",
                "x-ratelimit-remaining-requests": "28",
                "x-ratelimit-remaining-tokens": "0",
            },
        },
    )()
    captured = {}
    monkeypatch.setattr(
        api,
        "app_event",
        lambda kind, **fields: captured.update(kind=kind, **fields),
    )

    api._record_chat_operation(
        time.monotonic(),
        user_id="google-owner",
        transport="sse",
        outcome="error",
        exception=error,
    )

    assert captured["kind"] == "chat_operation"
    assert captured["error"] == "RateLimitError"
    assert captured["provider_status"] == 429
    assert captured["model_deployment"]
    assert captured["rate_limit_scope"] == "tokens"
    assert captured["retry_after_ms"] == 2000
    assert "private" not in json.dumps(captured)


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


def test_optional_app_log_file_is_rotating_json_and_redacted(tmp_path, monkeypatch):
    target = tmp_path / "diagnostics" / "app.jsonl"
    monkeypatch.setenv("APP_LOG_PATH", str(target))
    obs.setup_logging(force=True)

    logging.getLogger("test.file").error("failed for alice@example.com")

    parsed = json.loads(target.read_text(encoding="utf-8").strip())
    assert parsed["level"] == "ERROR"
    assert parsed["msg"] == "failed for <email>"
    assert "alice@example.com" not in target.read_text(encoding="utf-8")


def test_json_exception_trace_is_redacted(capsys):
    obs.setup_logging(force=True)
    handler = logging.getLogger().handlers[0]
    handler.setFormatter(obs.JsonFormatter())

    try:
        raise RuntimeError("token=abcdefghijklmnop1234 for alice@example.com")
    except RuntimeError:
        logging.getLogger("test.exception").exception("provider failed")

    parsed = json.loads(capsys.readouterr().out.strip())
    assert "<redacted>" in parsed["exc"]
    assert "<email>" in parsed["exc"]
    assert "abcdefghijklmnop1234" not in parsed["exc"]
    assert "alice@example.com" not in parsed["exc"]


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


