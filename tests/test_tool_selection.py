"""Tests for phase-based tool binding (``trip_agent.select_tools``).

The heavy search/enrichment tools are bound only once a planning session is
active; greetings and pure preference-gathering turns stay lean to trim
per-turn prompt tokens.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tripplanner.agents import trip_agent


@pytest.fixture(autouse=True)
def _no_active_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default: no active trip on disk, so selection hinges on the messages.
    monkeypatch.setattr(trip_agent, "_load_active_trip", lambda: None)


def _names(tools: list) -> set[str]:
    return {t.name for t in tools}


def test_core_tools_subset_of_full() -> None:
    assert set(_names(trip_agent._CORE_TOOLS)).issubset(_names(trip_agent.TRIP_TOOLS))
    assert _names(trip_agent.TRIP_TOOLS) == _names(
        trip_agent._CORE_TOOLS
    ) | _names(trip_agent._SEARCH_TOOLS)


def test_greeting_binds_core_only() -> None:
    tools = trip_agent.select_tools([HumanMessage(content="Hi, I'm Munish from Bengaluru")])
    assert _names(tools) == _names(trip_agent._CORE_TOOLS)
    assert "request_trip_input" in _names(tools)
    assert "search_flights_duffel" not in _names(tools)


def test_planning_intent_binds_search() -> None:
    tools = trip_agent.select_tools([HumanMessage(content="plan a 5-day trip to Goa")])
    assert "search_flights_duffel" in _names(tools)
    assert "search_hotels" in _names(tools)


def test_active_trip_binds_search_even_without_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trip_agent, "_load_active_trip", lambda: {"destination": "Goa"})
    tools = trip_agent.select_tools([HumanMessage(content="make it cheaper")])
    assert "search_hotels" in _names(tools)


def test_prior_planning_tool_call_binds_search() -> None:
    msgs = [
        HumanMessage(content="hello"),
        AIMessage(
            content="",
            tool_calls=[{"name": "create_trip_plan", "args": {}, "id": "1"}],
        ),
    ]
    tools = trip_agent.select_tools(msgs)
    assert "search_flights_duffel" in _names(tools)


def test_active_trip_without_destination_stays_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trip_agent, "_load_active_trip", lambda: {"destination": ""})
    tools = trip_agent.select_tools([HumanMessage(content="thanks!")])
    assert _names(tools) == _names(trip_agent._CORE_TOOLS)


def test_proposal_only_binds_no_mutating_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trip_agent, "_load_active_trip", lambda: {"destination": "Goa"})

    tools = trip_agent.select_tools(
        [HumanMessage(content="review my crowded Day 3")],
        proposal_only=True,
    )

    assert "get_trip_plan" in _names(tools)
    assert "compute_route" in _names(tools)
    assert not (_names(tools) & trip_agent._MUTATING_TOOL_NAMES)
