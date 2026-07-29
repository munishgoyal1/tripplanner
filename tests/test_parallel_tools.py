"""Parallel tool execution test for the LangGraph ToolNode.

Verifies that when the LLM emits multiple tool_calls in one assistant turn,
ToolNode runs them concurrently — not serially. Without this guarantee the
agent's "parallel tool calls" prompt rule would silently regress to a
sequential round-trip per tool.
"""

from __future__ import annotations

import operator
import time
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

    tool_messages = [m for m in out["messages"] if hasattr(m, "content") and m.content in {"one", "two", "three"}]
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


def test_initial_itinerary_gate_stops_after_update(monkeypatch) -> None:
    from tripplanner import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "London", "day_wise_itinerary": []},
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


def test_new_trip_retries_incomplete_researched_plan_once(monkeypatch) -> None:
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

    requirement = graph_mod._trip_update_requirement(messages)

    assert requirement is not None
    assert "No concrete hotel is selected" in requirement


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
