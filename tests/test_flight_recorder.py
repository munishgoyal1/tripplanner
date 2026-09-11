import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tripplanner import flight_recorder as recorder
from tripplanner.flight_callbacks import FlightRecorderCallback
from tripplanner.flight_http import AsyncRecordingTransport, RecordingTransport
from tripplanner.flight_middleware import FlightRecorderMiddleware


@pytest.fixture
def evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER", "1")
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER_WORKER", "0")
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER_DIR", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    token = recorder.TRACE.set("test-trace")
    yield lambda: [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(recorder.root().glob("*.json"))
    ]
    recorder.TRACE.reset(token)


@pytest.mark.parametrize("environment", ["local", "canary", "prod"])
def test_records_full_prompts_in_every_environment(evidence, monkeypatch, environment):
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
    assert events[0]["payload"]["messages"][0][0]["content"] == prompt
    assert events[1]["payload"]["response"]["generations"][0][0]["message"]["tool_calls"]
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
    assert recorder.decode_chunks(list(stored.values())) == original
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

    assert recorder._drain_once(limit=2) == 2
    assert len(evidence()) == 1

    recorder.drain_once()
    assert not evidence()


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
    assert terminal["request"] == {"message": "Plan Kashmir"}
    assert terminal["response"] == response.text


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
    assert "Ujjain" in json.dumps(events)


def test_multichunk_payload_roundtrips_without_truncation(evidence, monkeypatch):
    import base64
    import os

    from tripplanner import storage_cosmos

    stored = []
    monkeypatch.setattr(storage_cosmos, "upsert_doc", lambda *args: stored.append(args[-1]))
    recorder.record("test", content=base64.b64encode(os.urandom(300000)).decode())
    original = evidence()[0]
    recorder._upload(original)
    assert len(stored) > 1
    assert recorder.decode_chunks(stored) == original
    with pytest.raises(ValueError, match="Incomplete"):
        recorder.decode_chunks(stored[:-1])
