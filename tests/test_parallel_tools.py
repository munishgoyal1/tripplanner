"""Parallel tool execution test for the LangGraph ToolNode.

Verifies that when the LLM emits multiple tool_calls in one assistant turn,
ToolNode runs them concurrently — not serially. Without this guarantee the
agent's "parallel tool calls" prompt rule would silently regress to a
sequential round-trip per tool.
"""

from __future__ import annotations

import operator
import time
from types import SimpleNamespace
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode


@tool
def slow_one() -> str:
    """A deliberately slow tool that sleeps 300ms."""
    time.sleep(0.3)
    return "one"


@tool
def slow_two() -> str:
    """A deliberately slow tool that sleeps 300ms."""
    time.sleep(0.3)
    return "two"


@tool
def slow_three() -> str:
    """A deliberately slow tool that sleeps 300ms."""
    time.sleep(0.3)
    return "three"


class _State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]


def _make_graph(tools):
    g = StateGraph(_State)
    g.add_node("tools", ToolNode(tools))
    g.set_entry_point("tools")
    g.add_edge("tools", END)
    return g.compile()


def test_tool_node_runs_parallel_tool_calls_concurrently() -> None:
    app = _make_graph([slow_one, slow_two, slow_three])
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "slow_one", "args": {}, "id": "c1"},
            {"name": "slow_two", "args": {}, "id": "c2"},
            {"name": "slow_three", "args": {}, "id": "c3"},
        ],
    )
    start = time.monotonic()
    out = app.invoke({"messages": [ai]})
    elapsed = time.monotonic() - start

    # Three 300ms sleeps run in parallel should finish well under the serial
    # 900ms. Be generous on the CI ceiling but still well below the serial
    # baseline.
    assert elapsed < 0.7, f"ToolNode ran serially (took {elapsed:.2f}s)"

    tool_messages = [
        message
        for message in out["messages"]
        if hasattr(message, "content") and message.content in {"one", "two", "three"}
    ]
    assert len(tool_messages) == 3
    contents = sorted(tm.content for tm in tool_messages)
    assert contents == ["one", "three", "two"]


def test_tool_node_single_call_still_works() -> None:
    """Regression guard: a single tool_call still returns one ToolMessage."""
    app = _make_graph([slow_one])
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "slow_one", "args": {}, "id": "c1"}],
    )
    out = app.invoke({"messages": [ai]})
    tool_messages = [m for m in out["messages"] if hasattr(m, "content") and m.content == "one"]
    assert len(tool_messages) == 1


def test_trip_agent_binds_tools_with_parallel_flag() -> None:
    """Guard against silent removal of parallel_tool_calls=True in graph.py."""
    import inspect

    from tripplanner import graph as graph_mod

    src = inspect.getsource(graph_mod.trip_agent)
    assert "parallel_tool_calls=True" in src


def test_llm_allows_token_bucket_recovery(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    captured: dict = {}

    class FakeAzureChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(graph_mod, "AzureChatOpenAI", FakeAzureChatOpenAI)
    monkeypatch.setattr(
        graph_mod,
        "get_settings",
        lambda: SimpleNamespace(
            azure_openai_endpoint="https://example.openai.azure.com",
            azure_openai_api_key="test-key",
            azure_openai_deployment="test-deployment",
            azure_openai_api_version="2024-10-21",
        ),
    )

    graph_mod._get_llm()

    assert captured["max_retries"] == 3
    # A stalled call must fail fast instead of holding the SDK's 600s default.
    assert captured["timeout"] == 90.0
    # One uncapped turn emitted the whole 32k output window and starved the quota.
    assert captured["max_tokens"] == 8192


def test_usage_callback_records_model_latency_context_and_tokens(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    events: list[tuple[str, dict]] = []
    usage_calls: list[dict] = []
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(graph_mod.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        graph_mod,
        "app_event",
        lambda kind, **fields: events.append((kind, fields)),
    )
    monkeypatch.setattr(
        graph_mod,
        "record_usage",
        lambda _user_id, **fields: usage_calls.append(fields),
    )
    callback = graph_mod._UsageCallback("gpt-4.1-test")
    callback.on_chat_model_start(
        {},
        [[HumanMessage(content="Plan a short Punjab trip")]],
    )
    callback.on_llm_end(SimpleNamespace(llm_output={
        "token_usage": {"prompt_tokens": 1200, "completion_tokens": 300},
    }))

    assert events == [("llm_call", {
        "status": "ok",
        "model": "gpt-4.1-test",
        "ms": 250.0,
        "message_count": 1,
        "prompt_chars": 24,
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "cached_tokens": 0,
    })]
    assert usage_calls == [{
        "model": "gpt-4.1-test",
        "prompt_tokens": 1200,
        "completion_tokens": 300,
    }]


def test_usage_callback_records_model_error_latency(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    events: list[tuple[str, dict]] = []
    ticks = iter([10.0, 10.5])
    monkeypatch.setattr(graph_mod.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        graph_mod,
        "app_event",
        lambda kind, **fields: events.append((kind, fields)),
    )
    callback = graph_mod._UsageCallback("gpt-4.1-test")
    callback.on_chat_model_start(
        {},
        [[HumanMessage(content="Plan a short Punjab trip")]],
    )
    callback.on_llm_error(TimeoutError("timed out"))

    assert events == [("llm_call", {
        "status": "error",
        "model": "gpt-4.1-test",
        "ms": 500.0,
        "message_count": 1,
        "prompt_chars": 24,
        "error": "TimeoutError",
    })]


def test_trip_agent_compacts_tool_results_only_for_model_input(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    captured_messages: list[BaseMessage] = []

    class FakeBoundModel:
        def invoke(self, messages):
            captured_messages.extend(messages)
            return AIMessage(content="Done")

    class FakeModel:
        def bind_tools(self, _tools, **_options):
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())
    monkeypatch.setattr(graph_mod, "select_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(graph_mod, "load_active_trip_dict", lambda: {})
    full_result = "R" * 5_000
    tool_messages = [
        ToolMessage(content=full_result, tool_call_id=f"research-{index}")
        for index in range(14)
    ]
    messages: list[BaseMessage] = [HumanMessage(content="Plan Rajasthan"), *tool_messages]

    graph_mod.trip_agent({
        "messages": messages,
        "current_agent": "",
        "proposal_only": False,
    })

    sent_results = [
        message for message in captured_messages if isinstance(message, ToolMessage)
    ]
    assert len(sent_results) == len(tool_messages)
    assert sum(len(str(message.content)) for message in sent_results) <= 12_000
    assert all("truncated for synthesis" in str(message.content) for message in sent_results)
    assert all(message.content == full_result for message in tool_messages)


def test_model_tool_result_budget_is_strict_for_large_batches() -> None:
    from tripplanner import graph as graph_mod

    tool_messages = [
        ToolMessage(content="R" * 5_000, tool_call_id=f"research-{index}")
        for index in range(60)
    ]

    compacted = graph_mod._messages_for_model(tool_messages)

    assert sum(len(str(message.content)) for message in compacted) <= 12_000


def test_trip_agent_forces_initial_itinerary_after_creation(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    bound_options: dict = {}

    class FakeBoundModel:
        def invoke(self, _messages):
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "update_trip_plan",
                    "args": {"updates_json": '{"day_wise_itinerary": []}'},
                    "id": "update-1",
                }],
            )

    class FakeModel:
        def bind_tools(self, _tools, **options):
            bound_options.update(options)
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "London", "day_wise_itinerary": []},
    )
    messages = [
        HumanMessage(content="Plan a London trip"),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "create_trip_plan",
                "args": {
                    "destination": "London",
                    "departure_date": "2026-08-25",
                    "return_date": "2026-08-31",
                },
                "id": "create-1",
            }],
        ),
        ToolMessage(content="Created", tool_call_id="create-1"),
    ]

    result = graph_mod.trip_agent({
        "messages": messages,
        "current_agent": "",
        "proposal_only": False,
    })

    assert bound_options["tool_choice"] == "update_trip_plan"
    assert result["messages"][0].tool_calls[0]["name"] == "update_trip_plan"


def test_initial_itinerary_gate_stops_after_successful_update(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "London",
            "day_wise_itinerary": [{"day": 1, "stops": ["Westminster"]}],
        },
    )
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "create_trip_plan", "args": {}, "id": "create-1"}],
        ),
        ToolMessage(content="Created", tool_call_id="create-1"),
        AIMessage(
            content="",
            tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "update-1"}],
        ),
    ]

    assert graph_mod._trip_update_requirement(messages) is None


def test_empty_active_trip_is_repaired_on_later_planning_turn(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Paris", "day_wise_itinerary": []},
    )

    requirement = graph_mod._trip_update_requirement([
        HumanMessage(content="Why is my itinerary pane blank?"),
    ])

    assert requirement is not None
    assert "required updates_json" in requirement


def test_empty_itinerary_retries_one_failed_update(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Paris", "day_wise_itinerary": []},
    )
    messages = [
        HumanMessage(content="Build my Paris itinerary"),
        AIMessage(
            content="",
            tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "update-1"}],
        ),
        ToolMessage(content="Error: updates_json is required", tool_call_id="update-1"),
    ]

    assert graph_mod._trip_update_requirement(messages) is not None


def test_existing_itinerary_retries_one_failed_mutation(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "Madhya Pradesh",
            "day_wise_itinerary": [{"day": 1, "city": "Indore", "stops": []}],
        },
    )
    messages = [
        HumanMessage(content="Change the Indore hotel"),
        AIMessage(
            content="",
            tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "update-1"}],
        ),
        ToolMessage(
            content="Error: hotel location must match the active trip destination.",
            tool_call_id="update-1",
        ),
    ]

    requirement = graph_mod._trip_update_requirement(messages)

    assert requirement is not None
    assert "was not saved" in requirement
    assert "before claiming the itinerary changed" in requirement


def test_existing_itinerary_failed_mutation_retry_is_bounded(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "Madhya Pradesh",
            "day_wise_itinerary": [{"day": 1, "city": "Indore", "stops": []}],
        },
    )
    messages = [HumanMessage(content="Change the Indore hotel")]
    for attempt in range(2):
        call_id = f"update-{attempt}"
        messages.extend([
            AIMessage(
                content="",
                tool_calls=[{"name": "update_trip_plan", "args": {}, "id": call_id}],
            ),
            ToolMessage(
                content="Error: hotel location must match the active trip destination.",
                tool_call_id=call_id,
            ),
        ])

    assert graph_mod._trip_update_requirement(messages) is None


def test_empty_itinerary_retry_is_bounded(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Paris", "day_wise_itinerary": []},
    )
    messages = [HumanMessage(content="Build my Paris itinerary")]
    for attempt in range(2):
        call_id = f"update-{attempt}"
        messages.extend([
            AIMessage(
                content="",
                tool_calls=[{"name": "update_trip_plan", "args": {}, "id": call_id}],
            ),
            ToolMessage(content="Error: updates_json is required", tool_call_id=call_id),
        ])

    assert graph_mod._trip_update_requirement(messages) is None


def test_trip_agent_forces_hotel_search_when_draft_keeps_placeholder(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    bound_options: dict = {}
    bound_tool_names: list[str] = []

    class FakeBoundModel:
        def invoke(self, _messages):
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_hotels",
                    "args": {"city_code": "PAR"},
                    "id": "hotel-1",
                }],
            )

    class FakeModel:
        def bind_tools(self, tools, **options):
            bound_options.update(options)
            bound_tool_names.extend(tool.name for tool in tools)
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel (TBD)", "kind": "hotel"},
                    {"name": "Louvre Museum", "kind": "attraction"},
                ],
            }],
            "selected_hotels": [],
        },
    )
    messages = [
        HumanMessage(content="Build my Paris itinerary"),
        AIMessage(
            content="",
            tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "draft-1"}],
        ),
        ToolMessage(content="Hotel planning incomplete", tool_call_id="draft-1"),
    ]

    result = graph_mod.trip_agent({
        "messages": messages,
        "current_agent": "",
        "proposal_only": False,
    })

    assert bound_options["tool_choice"] == "search_hotels"
    assert bound_tool_names == ["search_hotels"]
    assert result["messages"][0].tool_calls[0]["name"] == "search_hotels"


def test_trip_agent_falls_back_to_google_when_hotel_provider_is_unavailable(
    monkeypatch,
) -> None:
    from tripplanner import graph as graph_mod

    bound_options: dict = {}

    class FakeBoundModel:
        def invoke(self, _messages):
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_places_with_reviews",
                    "args": {"query": "family-friendly 4-star hotels", "city": "Paris"},
                    "id": "places-1",
                }],
            )

    class FakeModel:
        def bind_tools(self, _tools, **options):
            bound_options.update(options)
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
            }],
            "selected_hotels": [],
        },
    )
    messages = [
        HumanMessage(content="Build my Paris itinerary"),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "search_hotels",
                "args": {"city": "Paris"},
                "id": "hotel-1",
            }],
        ),
        ToolMessage(
            content="Amadeus API not configured. Falling back to general knowledge.",
            tool_call_id="hotel-1",
        ),
    ]

    result = graph_mod.trip_agent({
        "messages": messages,
        "current_agent": "",
        "proposal_only": False,
    })

    assert bound_options["tool_choice"] == "search_places_with_reviews"
    assert result["messages"][0].tool_calls[0]["name"] == "search_places_with_reviews"


def test_hotel_fallback_uses_successful_result_from_parallel_batch() -> None:
    from tripplanner import graph as graph_mod

    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search_hotels", "args": {}, "id": "hotel-1"},
                {"name": "search_hotels", "args": {}, "id": "hotel-2"},
            ],
        ),
        ToolMessage(
            content="No hotels found for Amritsar.",
            tool_call_id="hotel-1",
        ),
        ToolMessage(
            content='[{"name": "The Oberoi Sukhvilas", "city": "Chandigarh"}]',
            tool_call_id="hotel-2",
        ),
    ]

    assert graph_mod._trip_hotel_fallback_requirement(messages) is None


def test_new_trip_requires_enriched_update_after_research(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "London",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Tower of London", "kind": "attraction"}],
            }],
            "selected_hotels": [],
        },
    )
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "create_trip_plan", "args": {}, "id": "create-1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "draft-1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_hotels", "args": {}, "id": "hotel-1"}],
        ),
    ]

    requirement = graph_mod._trip_update_requirement(messages)

    assert requirement is not None
    assert "Research is complete" in requirement
    assert "strongest real hotel" in requirement


def test_new_trip_does_not_rewrite_incomplete_researched_plan_twice(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "London",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
            }],
            "selected_hotels": [],
        },
    )
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "create_trip_plan", "args": {}, "id": "create-1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_hotels", "args": {}, "id": "hotel-1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "update-1"}],
        ),
    ]

    assert graph_mod._trip_update_requirement(messages) is None


def test_new_trip_completion_retry_is_bounded(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "London",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
            }],
            "selected_hotels": [],
        },
    )
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "create_trip_plan", "args": {}, "id": "create-1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_hotels", "args": {}, "id": "hotel-1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "update-1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "update_trip_plan", "args": {}, "id": "update-2"}],
        ),
    ]

    assert graph_mod._trip_update_requirement(messages) is None


def test_trip_agent_ends_with_summary_at_tool_phase_budget(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    captured_messages: list[BaseMessage] = []

    class FakeModel:
        def invoke(self, messages):
            captured_messages.extend(messages)
            return AIMessage(content="Saved the best available plan.")

        def bind_tools(self, *_args, **_kwargs):
            raise AssertionError("tool budget must disable tools")

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Punjab", "day_wise_itinerary": []},
    )
    messages: list[BaseMessage] = [HumanMessage(content="Plan Punjab")]
    for phase in range(graph_mod._MAX_TOOL_PHASES_PER_TURN):
        call_id = f"tool-{phase}"
        messages.extend([
            AIMessage(
                content="",
                tool_calls=[{"name": "update_trip_plan", "args": {}, "id": call_id}],
            ),
            ToolMessage(content="Saved", tool_call_id=call_id),
        ])

    result = graph_mod.trip_agent({
        "messages": messages,
        "current_agent": "",
        "proposal_only": False,
    })

    assert result["messages"][0].content == "Saved the best available plan."
    assert any("bounded planning-tool budget" in str(message.content)
               for message in captured_messages)


def test_proposal_only_never_forces_initial_itinerary(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    bound_options: dict = {}

    class FakeBoundModel:
        def invoke(self, _messages):
            return AIMessage(content="Review only")

    class FakeModel:
        def bind_tools(self, _tools, **options):
            bound_options.update(options)
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "London", "day_wise_itinerary": []},
    )
    graph_mod.trip_agent({
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "create_trip_plan",
                    "args": {},
                    "id": "create-1",
                }],
            ),
        ],
        "current_agent": "",
        "proposal_only": True,
    })

    assert "tool_choice" not in bound_options
