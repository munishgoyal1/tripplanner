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

from langchain_core.messages import AIMessage, BaseMessage
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

    from multiagent import graph as graph_mod

    src = inspect.getsource(graph_mod.trip_agent)
    assert "parallel_tool_calls=True" in src
