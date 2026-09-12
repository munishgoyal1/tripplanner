import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tripplanner import flight_recorder as recorder
from tripplanner.flight_callbacks import FlightRecorderCallback
from tripplanner.flight_http import AsyncRecordingTransport, RecordingTransport
from tripplanner.flight_middleware import FlightRecorderMiddleware


def test_sanitize_fully_redacts_an_authorization_bearer_header():
    """Regression: applying _INLINE before _BEARER let "Authorization:
    Bearer <token>" strand the real token unredacted, because _INLINE's
    "value" capture for "Authorization:" stopped at the first space (just
    the word "Bearer"), consuming it before _BEARER ever saw the token."""
    text = recorder.sanitize("Authorization: Bearer sk-abc123DEF456")
    assert "sk-abc123DEF456" not in text
    assert "<redacted>" in text


@pytest.fixture
def evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER", "1")
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER_WORKER", "0")
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER_DIR", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    token = recorder.TRACE.set("test-trace")
    def read_events():
        recorder.flush_pending()
        return [event for p in sorted(recorder.root().glob("*.json"))
                for event in recorder._events(json.loads(p.read_text(encoding="utf-8")))]
    yield read_events
    recorder.flush_pending()
    recorder.TRACE.reset(token)


@pytest.mark.parametrize("environment", ["local", "canary", "prod"])
def test_model_callbacks_keep_metadata_in_every_environment(evidence, monkeypatch, environment):
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", environment)
    callback = FlightRecorderCallback()
    prompt = "Plan Kashmir 2027-04-05 for 2 adults" * 10000
    callback.on_chat_model_start({}, [[HumanMessage(content=prompt)]], run_id="model-1")
    callback.on_llm_end(
        LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="Hotel TBD",
                            tool_calls=[
                                {
                                    "name": "search_hotels",
                                    "args": {"city": "Srinagar"},
                                    "id": "call-1",
                                }
                            ],
                        )
                    )
                ]
            ]
        ),
        run_id="model-1",
    )
    events = evidence()
    assert events[0]["payload"]["message_count"] == 1
    assert prompt not in json.dumps(events)
    assert "generations" not in json.dumps(events)
    assert events[1]["duration_ms"] >= 0
    assert {e["trace_id"] for e in events} == {"test-trace"}
    assert recorder.root().name == environment


def test_redacts_credentials_without_masking_dates(evidence):
    recorder.record(
        "test",
        api_key="secret-key",
        headers={"Authorization": "Bearer xyz"},
        url="https://maps.googleapis.com/api?key=secret-value&date=2027-04-05",
        payload='{"access_token":"secret-token"}',
        body={"key": "secret-value", "query": "Kashmir 2027-04-05"},
    )
    text = json.dumps(evidence())
    for secret in ("secret-key", "xyz", "secret-value", "secret-token"):
        assert secret not in text
    assert "2027-04-05" in text


def test_cosmos_chunks_retries_and_checksum(evidence, monkeypatch):
    from tripplanner import storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    stored = {}
    failures = [True]

    def upsert(container, user, doc_id, body):
        assert container == "flight_recorder"
        if failures.pop() if failures else False:
            raise TimeoutError("offline")
        stored[doc_id] = body

    monkeypatch.setattr(storage_cosmos, "upsert_doc", upsert)
    recorder.record("test", payload="完整 itinerary", user_id="user-a")
    original = evidence()[0]
    recorder.drain_once()
    assert evidence() and recorder.status()["last_error"] == "TimeoutError"
    recorder.drain_once()
    assert not evidence()
    assert recorder._events(recorder.decode_chunks(list(stored.values()))) == [original]
    assert recorder.status()["last_error"] == ""
    broken = [dict(next(iter(stored.values())), chunks=2)]
    with pytest.raises(ValueError, match="Incomplete"):
        recorder.decode_chunks(broken)


def test_worker_drain_is_bounded_without_changing_manual_drain(evidence, monkeypatch):
    from tripplanner import storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(storage_cosmos, "upsert_doc", lambda *_args, **_kwargs: None)
    for index in range(3):
        recorder.record("test", index=index, user_id="user-a")
        recorder.flush_pending()

    assert recorder._drain_once(limit=2) == 2
    assert len(evidence()) == 1

    recorder.drain_once()
    assert not evidence()


def test_uploader_reports_periodically_and_when_caught_up():
    assert not recorder._upload_report_due(25, 25, 25, 10)
    assert recorder._upload_report_due(25, 500, 25, 60)
    assert recorder._upload_report_due(4, 29, 25, 12)
    assert not recorder._upload_report_due(0, 0, 25, 120)


def test_low_level_successes_become_one_interaction_flight_summary(
    evidence, monkeypatch, tmp_path
):
    from tripplanner import storage_cosmos
    from tripplanner.observability import app_event
    from tripplanner.usage_attribution import usage_scope

    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)

    with usage_scope("user_action", interaction_id="flow-1", route="GET /trip/workspace"):
        for _index in range(100):
            app_event("cache_access", cache="google_places", result="memory_hit")

    events = evidence()
    assert not [event for event in events if event["kind"] == "log.cache_access"]
    summaries = [event for event in events if event["kind"] == "log.flow_summary"]
    assert len(summaries) == 1
    assert summaries[0]["cache_hits"] == 100


def test_http_attempts_preserve_errors_retry_number_and_body(evidence):
    responses = [429, 200]

    def upstream(request):
        return httpx.Response(responses.pop(0), json={"result": "hotel TBD"})

    with httpx.Client(transport=RecordingTransport(httpx.MockTransport(upstream))) as client:
        for retry in range(2):
            response = client.post(
                "https://model.example/chat",
                json={"prompt": "Kashmir"},
                headers={"x-stainless-retry-count": str(retry)},
            )
            assert response.json()["result"] == "hotel TBD"
    events = evidence()
    assert [e["retry_count"] for e in events if e["kind"] == "http.attempt"] == ["0", "1"]
    assert [e["status"] for e in events if e["kind"] == "http.result"] == [429, 200]
    assert len({e["attempt_id"] for e in events}) == 2


async def test_async_stream_records_partial_failure(evidence):
    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"partial":"hello"}\n\n'
            raise httpx.ReadError("lost connection")

    async def upstream(request):
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=BrokenStream()
        )

    async with httpx.AsyncClient(
        transport=AsyncRecordingTransport(httpx.MockTransport(upstream))
    ) as client:
        with pytest.raises(httpx.ReadError):
            await client.post("https://model.example/chat", json={"prompt": "hello"})
    terminal = evidence()[-1]
    assert terminal["outcome"] == "error"
    assert '"partial":"hello"' in terminal["body"]


async def test_middleware_preserves_sse_and_authenticated_owner(evidence):
    from tripplanner.user_context import set_user_id

    async def app(scope, receive, send):
        set_user_id("google-test")
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            }
        )
        await send({"type": "http.response.body", "body": b"data: one\n\n", "more_body": True})
        await send({"type": "http.response.body", "body": b"data: two\n\n"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=FlightRecorderMiddleware(app)), base_url="http://test"
    ) as client:
        response = await client.post("/chat/stream", json={"message": "Plan Kashmir"})
    assert response.text == "data: one\n\ndata: two\n\n"
    terminal = evidence()[-1]
    assert terminal["complete"] is True
    assert terminal["user_id"] == "google-test"
    assert terminal["request"]["omitted"] == "metadata only"
    assert terminal["response"]["bytes"] == len(response.content)


def test_trace_export_includes_research_before_trip_created(evidence):
    recorder.record("llm.start", user_id="user-a", messages=["Plan Kashmir"])
    recorder.record("trip.saved", user_id="user-a", trip_id="kashmir-2027-04-05")
    events = recorder.export_events("user-a", trip_id="kashmir-2027-04-05")
    assert [e["kind"] for e in events] == ["llm.start", "trip.saved"]
    assert recorder.export_events("user-b") == []


def test_recorder_failure_cannot_fail_planning(evidence, monkeypatch):
    monkeypatch.setattr(recorder, "root", lambda: (_ for _ in ()).throw(OSError("disk full")))
    recorder.record("llm.start", prompt="still plan the trip")


def test_sensitive_document_model_does_not_record_content(evidence):
    callback = FlightRecorderCallback(sensitive=True)
    callback.on_chat_model_start({}, [[HumanMessage(content="passport raw text")]], run_id="doc")
    callback.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=AIMessage(content="passport raw text"))]]),
        run_id="doc",
    )
    assert "passport raw text" not in json.dumps(evidence())


def test_real_openai_sdk_retry_is_a_separate_attempt(evidence):
    from openai import OpenAI

    statuses = [429, 200]

    def upstream(request):
        status = statuses.pop(0)
        payload = (
            {"error": {"message": "busy", "type": "rate_limit"}}
            if status == 429
            else {
                "id": "reply-1",
                "object": "chat.completion",
                "created": 1,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Kashmir plan"},
                    }
                ],
            }
        )
        return httpx.Response(status, json=payload, headers={"retry-after-ms": "1"})

    with httpx.Client(transport=RecordingTransport(httpx.MockTransport(upstream))) as client:
        sdk = OpenAI(
            api_key="never-record-this-key",
            base_url="https://model.example/v1",
            http_client=client,
            max_retries=1,
        )
        reply = sdk.chat.completions.create(
            model="test", messages=[{"role": "user", "content": "Plan Kashmir"}]
        )
    assert reply.choices[0].message.content == "Kashmir plan"
    assert [e["retry_count"] for e in evidence() if e["kind"] == "http.attempt"] == ["0", "1"]
    assert "never-record-this-key" not in json.dumps(evidence())


def test_graph_tools_inherit_one_trace_without_http(evidence):
    from langchain_core.tools import tool
    from langgraph.graph import END, StateGraph

    from tripplanner.flight_callbacks import ToolRecorderCallback

    @tool
    def local_advice(destination: str) -> str:
        """Return fixture advice."""
        return f"{destination}: verify ritual admission"

    graph = StateGraph(dict)
    graph.add_node(
        "research", lambda state: {"advice": local_advice.invoke({"destination": "Ujjain"})}
    )
    graph.set_entry_point("research")
    graph.add_edge("research", END)
    token = recorder.TRACE.set("")
    try:
        graph.compile().with_config(callbacks=[ToolRecorderCallback()]).invoke({})
    finally:
        recorder.TRACE.reset(token)
    events = evidence()
    assert {e["kind"] for e in events} >= {"graph.start", "graph.end", "tool.start", "tool.end"}
    assert len({e["trace_id"] for e in events}) == 1
    assert "Ujjain" not in json.dumps(events)


def test_multichunk_payload_roundtrips_without_truncation(evidence, monkeypatch):
    import base64
    import os

    from tripplanner import storage_cosmos

    stored = []
    monkeypatch.setattr(storage_cosmos, "upsert_doc", lambda *args: stored.append(args[-1]))
    original = {"kind": "test", "event_id": "large", "user_id": "test", "trace_id": "test-trace",
                "recorded_at": "2026-09-12",
                "content": base64.b64encode(os.urandom(300000)).decode()}
    recorder._upload(original)
    assert len(stored) > 1
    assert recorder.decode_chunks(stored) == original
    with pytest.raises(ValueError, match="Incomplete"):
        recorder.decode_chunks(stored[:-1])


def test_events_are_batched_off_the_callers_disk_path(evidence, monkeypatch):
    syncs = []
    monkeypatch.setattr(recorder.os, "fsync", lambda fd: syncs.append(fd))
    for index in range(25):
        recorder.record("log.tool_call", user_id="batch-user", index=index)
    assert not list(recorder.root().glob("*.json"))
    assert not syncs
    assert len(evidence()) == 25
    assert len(syncs) == 1
    assert len(list(recorder.root().glob("*.json"))) == 1
    assert len(recorder.export_events("batch-user")) == 25


def test_failed_batch_write_counts_loss_and_removes_partial_file(evidence, monkeypatch):
    monkeypatch.setattr(recorder, "_dropped_events", 0)
    monkeypatch.setattr(recorder.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("full")))
    recorder.record("test")
    recorder.flush_pending()
    assert recorder.status()["dropped_events"] == 1
    assert not list(recorder.root().glob("*.tmp"))
    assert not evidence()


def test_queue_overload_is_bounded_and_failure_gets_priority(evidence, monkeypatch):
    monkeypatch.setattr(recorder, "_QUEUE_MAX_EVENTS", 2)
    monkeypatch.setattr(recorder, "_dropped_events", 0)
    for _ in range(3):
        recorder.record("log.tool_call")
    recorder.record("llm.error", error="connection closed")
    assert recorder.status()["queued_events"] == 2
    assert recorder.status()["dropped_events"] == 2
    assert any(event["kind"] == "llm.error" for event in evidence())


def test_bodies_are_bounded_and_success_has_no_payload(evidence):
    from tripplanner.flight_http import BodyCapture, Capture

    capture = BodyCapture()
    capture.append(b"x" * 1000000)
    assert len(capture.data) == 65536
    assert capture.body("text/plain", True)["truncated"] is True
    assert "excerpt" not in capture.body("text/plain", False)
    attempt = Capture(httpx.Request("POST", "https://model.example", json={"prompt": "large"}),
                      sensitive=False)
    attempt.status = 200
    attempt.append(b"data: [DO")
    attempt.append(b"NE]\n\n")
    attempt.end("interrupted")
    result = evidence()[-1]
    assert result["outcome"] == "complete"
    assert result["body"]["omitted"] == "metadata only"


def test_graph_callback_does_not_duplicate_model_or_nested_tool(evidence):
    from tripplanner.flight_callbacks import ToolRecorderCallback

    callback = ToolRecorderCallback()
    callback.on_chat_model_start({}, [[HumanMessage(content="secret itinerary")]], run_id="llm")
    callback.on_tool_start({"name": "update"}, "big input", run_id="outer")
    callback.on_tool_start({"name": "update"}, "big input", run_id="inner", parent_run_id="outer")
    callback.on_tool_end("big result", run_id="inner", parent_run_id="outer")
    callback.on_tool_end("big result", run_id="outer")
    assert [event["kind"] for event in evidence()] == ["tool.start", "tool.end"]


def test_retention_enforces_age_and_disk_cap(tmp_path):
    import os
    import time

    from tripplanner.diagnostic_retention import prune

    for name in ("expired.json", "old.json", "new.json"):
        (tmp_path / name).write_bytes(b"x" * 10)
    os.utime(tmp_path / "expired.json", (0, 0))
    os.utime(tmp_path / "old.json", (time.time() - 2, time.time() - 2))
    prune(tmp_path, "*.json", max_bytes=10, max_age=100)
    assert [path.name for path in tmp_path.glob("*.json")] == ["new.json"]


def test_six_large_successful_model_requests_have_small_evidence(evidence):
    content = "large itinerary context " * 10000
    callback = FlightRecorderCallback()
    with httpx.Client(transport=RecordingTransport(httpx.MockTransport(
        lambda request: httpx.Response(200, json={"reply": content})
    ))) as client:
        for index in range(6):
            callback.on_chat_model_start({}, [[HumanMessage(content=content)]], run_id=str(index))
            response = client.post("https://model.example/chat", json={"prompt": content})
            callback.on_llm_end(None, run_id=str(index))
            assert response.json()["reply"] == content
    events = evidence()
    assert len(events) == 24
    assert len(json.dumps(events).encode()) < 25000
    assert content not in json.dumps(events)


def test_verbose_http_capture_is_opt_in_and_bounded(evidence, monkeypatch):
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER_VERBOSE", "1")
    content = "z" * 100000
    with httpx.Client(transport=RecordingTransport(httpx.MockTransport(
        lambda request: httpx.Response(200, text=content)
    ))) as client:
        assert client.post("https://model.example/chat", content=content).text == content
    events = evidence()
    assert events[0]["body"]["truncated"] is True
    assert events[1]["body"]["truncated"] is True
    assert len(events[1]["body"]["excerpt"]) == 65536
