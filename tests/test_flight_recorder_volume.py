"""The flight recorder keeps the request spine and failures, not every event.

Each recorded event is its own fsync'd file written on the request path, so what
it declines to record is as much a design decision as what it keeps.
"""

from __future__ import annotations

import logging

from tripplanner import observability as obs
from tripplanner.flight_recorder import RecorderLogHandler


def test_routine_success_events_are_not_recorded():
    """The high-volume per-call events cost a file each and say little alone."""
    for kind in (
        "provider_call",
        "llm_call",
        "agent_model_round",
        "tool_call",
        "chat_phase",
        "cache_access",
        "llm_usage",
        "storage_operation",
        "outbound_call",
        "provider_pacing",
    ):
        assert not obs._should_record_event(kind, {"status": "ok"}), kind


def test_request_spine_is_recorded():
    for kind in (
        "chat_operation",
        "api_chat_request",
        "api_chat_response",
        "api_chat_stream_request",
        "api_chat_stream_done",
        "cost_ceiling_would_block",
        "trip_cost_anomaly",
        "api_oauth_login",
    ):
        assert obs._should_record_event(kind, {"status": "ok"}), kind


def test_failures_are_recorded_whatever_their_kind():
    """Narrowing the allowlist must never lose an error."""
    for fields in (
        {"status": "error"},
        {"outcome": "failed"},
        {"error": "boom"},
    ):
        assert obs._should_record_event("provider_call", fields)
        assert obs._should_record_event("some_future_event_nobody_listed", fields)


def test_an_unlisted_success_event_is_quiet_by_default():
    """Quiet by default is the inversion: a new event kind should not silently
    start writing a file per occurrence."""
    assert not obs._should_record_event("some_future_event_nobody_listed", {"status": "ok"})


def test_console_logging_is_not_narrowed_by_the_recorder_allowlist():
    """The two decisions are separate.

    They were one flag, so tightening what reaches disk would also have stopped
    ordinary provider activity showing up in the console you read while working.
    """
    assert obs._should_log_event("provider_call", {"provider": "google", "status": "ok"})
    assert obs._should_log_event("tool_call", {"status": "ok"})
    assert not obs._should_record_event("provider_call", {"provider": "google", "status": "ok"})


def test_info_logs_are_not_mirrored_into_the_recorder():
    """Mirroring INFO turned routine progress into disk writes on the hot path."""
    assert RecorderLogHandler.LEVEL_FLOOR == logging.WARNING

    recorded: list[str] = []
    handler = RecorderLogHandler()

    def fake_record(kind, **payload):
        recorded.append(payload.get("level", ""))

    import tripplanner.flight_recorder as fr

    original = fr.record
    fr.record = fake_record
    try:
        for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
            handler.emit(
                logging.LogRecord(
                    name="tripplanner.something",
                    level=level,
                    pathname=__file__,
                    lineno=1,
                    msg="progress",
                    args=(),
                    exc_info=None,
                )
            )
    finally:
        fr.record = original

    assert recorded == ["WARNING", "ERROR"]
