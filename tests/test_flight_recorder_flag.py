import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

from tripplanner import config, debug_store, flight_http, flight_recorder, http_client
from tripplanner.flight_middleware import FlightRecorderMiddleware


def forbidden(*args, **kwargs):
    pytest.fail("Disabled recorder performed capture work")


@pytest.mark.parametrize("value, expected", [
    (None, False), ("0", False), ("false", False), ("off", False),
    ("", False), ("typo", False), ("1", True), (" TRUE ", True),
    ("on", True), ("yes", True),
])
def test_master_flag_defaults_off_and_requires_explicit_opt_in(monkeypatch, value, expected):
    monkeypatch.delenv("TRIPPLANNER_FLIGHT_RECORDER", raising=False)
    if value is not None:
        monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER", value)
    assert config.Settings().flight_recorder_enabled is expected
    assert flight_recorder.enabled() is expected


@pytest.mark.parametrize("environment", ["local", "canary", "prod"])
def test_environment_profiles_disable_recording(environment):
    path = Path(__file__).parents[1] / "config/environments" / f"{environment}.env"
    assert dotenv_values(path)["TRIPPLANNER_FLIGHT_RECORDER"] == "0"


def test_disabled_recording_skips_serialization_worker_and_archive(monkeypatch):
    monkeypatch.setenv("TRIPPLANNER_DEBUG_STORE", "1")
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER_VERBOSE", "1")
    monkeypatch.setattr(flight_recorder, "sanitize", forbidden)
    monkeypatch.setattr(flight_recorder, "_start_worker", forbidden)
    monkeypatch.setattr(flight_recorder, "root", forbidden)
    monkeypatch.setattr(debug_store, "users_root", forbidden)
    before = len(flight_recorder._pending)
    flight_recorder.record("trip.saved", trip=object())
    assert debug_store.capture_trip({"trip_id": "trip"}, "user") is None
    assert len(flight_recorder._pending) == before
    assert not flight_recorder.capture_provider_bodies()


def test_disabled_model_options_do_not_construct_callbacks_or_clients(monkeypatch):
    monkeypatch.setattr(flight_http, "_model_recording_options", forbidden)
    assert flight_http.model_recording_options() == {}
    assert flight_http.model_recording_options(sensitive=True) == {}


def test_model_and_graph_keep_usage_without_recorder_callbacks(monkeypatch):
    from tripplanner import graph
    from tripplanner.flight_callbacks import ToolRecorderCallback

    monkeypatch.setattr(graph, "AzureChatOpenAI", lambda **kwargs: kwargs)
    model = graph._build_llm.__wrapped__("endpoint", "key", "deployment", "version")
    assert len(model["callbacks"]) == 1
    assert isinstance(model["callbacks"][0], graph._UsageCallback)
    assert "http_client" not in model
    assert "http_async_client" not in model
    compiled = graph.build_graph()
    assert not (getattr(compiled, "config", None) or {}).get("callbacks")
    monkeypatch.setenv("TRIPPLANNER_FLIGHT_RECORDER", "1")
    recorded = graph.build_graph()
    assert isinstance(recorded.config["callbacks"][0], ToolRecorderCallback)


@pytest.mark.parametrize("status", [200, 503])
def test_disabled_provider_request_bypasses_capture_even_on_failure(monkeypatch, status):
    response = httpx.Response(status, content=b"body")
    calls = []
    def send(*args, **kwargs):
        calls.append((args, kwargs))
        return response
    monkeypatch.setattr(http_client, "_request", send)
    monkeypatch.setattr(uuid, "uuid4", forbidden)
    monkeypatch.setattr(flight_http, "body_data", forbidden)
    monkeypatch.setattr(flight_recorder, "record", forbidden)
    assert http_client.request("POST", "https://example.test", json={"x": 1}) is response
    assert calls == [(("POST", "https://example.test"), {
        "endpoint": None, "log_context": None, "json": {"x": 1},
    })]


def test_disabled_provider_exception_is_preserved(monkeypatch):
    error = RuntimeError("provider failed")
    def send(*args, **kwargs):
        raise error
    monkeypatch.setattr(http_client, "_request", send)
    monkeypatch.setattr(flight_recorder, "record", forbidden)
    with pytest.raises(RuntimeError) as caught:
        http_client.get("https://example.test")
    assert caught.value is error


@pytest.mark.asyncio
async def test_disabled_middleware_passes_original_stream_functions(monkeypatch):
    from tripplanner import flight_middleware
    monkeypatch.setattr(flight_middleware, "BodyCapture", forbidden)
    receive, send = object(), object()
    scope = {"type": "http", "path": "/chat"}
    async def app(actual_scope, actual_receive, actual_send):
        assert actual_scope is scope
        assert actual_receive is receive
        assert actual_send is send
        return "complete"
    assert await FlightRecorderMiddleware(app)(scope, receive, send) == "complete"


@pytest.mark.asyncio
async def test_disabled_transports_preserve_response_without_capture(monkeypatch):
    monkeypatch.setattr(flight_http, "Capture", forbidden)
    response = httpx.Response(200, content=b"data: hello\n\n")
    transport = httpx.MockTransport(lambda request: response)
    request = httpx.Request("POST", "https://example.test", content=b"request")
    assert flight_http.RecordingTransport(transport).handle_request(request) is response
    result = await flight_http.AsyncRecordingTransport(transport).handle_async_request(request)
    assert result is response
