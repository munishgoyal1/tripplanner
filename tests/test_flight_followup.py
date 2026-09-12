import copy
import json
from contextvars import ContextVar

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tripplanner.graph_policy import is_flight_followup, resolve_completion_policy


def saved_trip():
    return {
        "destination": "Kashmir", "origin": "Bangalore", "status": "draft",
        "day_wise_itinerary": [
            {"day": 1, "title": "Arrival", "stops": [{"name": "Hotel TBD", "kind": "hotel"}]},
            {"day": 2, "title": "Dal Lake", "stops": [{"name": "Dal Lake", "kind": "attraction"}]},
            {"day": 3, "title": "Departure", "stops": [{"name": "Hotel TBD", "kind": "hotel"}]},
        ],
    }


def update_result(index, text):
    return [
        AIMessage(content="", tool_calls=[{
            "name": "update_trip_plan", "args": {}, "id": str(index),
        }]),
        ToolMessage(content=text, tool_call_id=str(index)),
    ]


@pytest.mark.parametrize("after_save", [False, True])
def test_flights_do_not_trigger_unrelated_completion_research(after_save):
    messages = [HumanMessage(content="add flights to and from bangalore for this kashmir trip")]
    if after_save:
        messages += update_result(1, "Trip plan updated.")
    decision = resolve_completion_policy(
        messages=messages, active_trip=saved_trip(), proposal_only=False, has_planning_intent=True,
    )
    assert decision.forced_tool is None


@pytest.mark.parametrize("prompt", [
    "rebuild the entire trip including flights", "add flights and hotels",
    "plan a new trip to Goa with flights",
])
def test_broad_requests_are_not_flight_only(prompt):
    assert not is_flight_followup([HumanMessage(content=prompt)], saved_trip())


@pytest.mark.parametrize("result", [
    "Trip plan updated (no material changes). Status: draft", "Error: invalid chronology",
])
def test_repeated_unproductive_saves_stop_the_turn(result):
    messages = [HumanMessage(content="finish this Kashmir trip")]
    messages += update_result(1, result) + update_result(2, result)
    decision = resolve_completion_policy(
        messages=messages, active_trip=saved_trip(), proposal_only=False, has_planning_intent=True,
    )
    assert decision.stopped_for_no_progress
    assert decision.forced_reason == "no_progress"


def test_previous_turn_noops_do_not_stop_new_request():
    messages = [HumanMessage(content="finish this trip")]
    messages += update_result(1, "Trip plan updated (no material changes).") * 2
    messages += [HumanMessage(content="add return flights")]
    decision = resolve_completion_policy(
        messages=messages, active_trip=saved_trip(), proposal_only=False, has_planning_intent=True,
    )
    assert not decision.stopped_for_no_progress


def test_graph_limits_flight_tools_and_enforces_mutation_scope(monkeypatch):
    from tripplanner import graph

    captured = {}

    class Model:
        def bind_tools(self, tools, **options):
            captured["tools"] = {tool.name for tool in tools}
            return self

        def invoke(self, messages):
            captured["messages"] = messages
            return AIMessage(content="", tool_calls=[{
                "name": "update_trip_plan", "id": "save", "args": {"updates_json": "{}"},
            }])

    monkeypatch.setattr(graph, "_get_llm", Model)
    monkeypatch.setattr(graph, "_CURRENT_TURN_PHASE", ContextVar("test_phase", default=None))
    monkeypatch.setattr(graph, "load_active_trip_dict", saved_trip)
    result = graph.trip_agent({"messages": [HumanMessage(content="add flights from Bangalore")]})
    assert {"search_flights", "get_trip_plan", "update_trip_plan"} <= captured["tools"]
    unrelated = {"search_hotels", "nearby_restaurants", "search_places_with_reviews"}
    assert not unrelated & captured["tools"]
    updates = json.loads(result["messages"][0].tool_calls[0]["args"]["updates_json"])
    assert updates["_edit_scope"] == "flights"


def test_flight_mutation_rejects_middle_day_rewrite(monkeypatch):
    from tripplanner.tools import trip_planner

    plan = saved_trip()
    monkeypatch.setattr(trip_planner, "_load_active_trip", lambda: copy.deepcopy(plan))
    changed = copy.deepcopy(plan["day_wise_itinerary"])
    changed[1]["title"] = "Gulmarg instead"
    result = trip_planner.update_trip_plan.invoke({"updates_json": json.dumps({
        "_edit_scope": "flights", "day_wise_itinerary": changed,
    })})
    assert result.startswith("Error: a flight-only request must preserve")


def test_flight_mutation_does_not_run_whole_trip_repairs(monkeypatch):
    from tripplanner.tools import trip_planner

    plan = saved_trip()
    monkeypatch.setattr(trip_planner, "_load_active_trip", lambda: copy.deepcopy(plan))
    saved = []
    monkeypatch.setattr(trip_planner, "_save_active_trip", lambda value: saved.append(value))

    def unexpected(*args):
        pytest.fail("A flight edit must not repair unrelated sightseeing days")

    for name in (
        "_repair_known_closed_days", "_repair_known_opening_hours",
        "_repair_temporal_infeasibility",
    ):
        monkeypatch.setattr(trip_planner, name, unexpected)
    result = trip_planner.update_trip_plan.invoke({"updates_json": json.dumps({
        "_edit_scope": "flights", "origin": "Bengaluru",
    })})
    assert not result.startswith("Error:")
    assert saved[0]["day_wise_itinerary"][1] == plan["day_wise_itinerary"][1]


def test_stalled_graph_uses_terminal_model_without_tools(monkeypatch):
    from tripplanner import graph

    class Model:
        def bind_tools(self, *args, **kwargs):
            pytest.fail("A stalled turn must not permit another tool call")

        def invoke(self, messages):
            assert "Repeated saves made no progress" in messages[1].content
            return AIMessage(content="Flights remain unresolved; the saved trip is available.")

    monkeypatch.setattr(graph, "_get_llm", Model)
    monkeypatch.setattr(graph, "_CURRENT_TURN_PHASE", ContextVar("test_phase", default=None))
    monkeypatch.setattr(graph, "load_active_trip_dict", saved_trip)
    messages = [HumanMessage(content="add flights from Bangalore")]
    messages += update_result(1, "Trip plan updated (no material changes).")
    messages += update_result(2, "Trip plan updated (no material changes).")
    result = graph.trip_agent({"messages": messages})
    assert not result["messages"][0].tool_calls


def test_complete_prompt_includes_tool_configuration(monkeypatch):
    from tripplanner import graph

    captured = {}
    monkeypatch.setattr(graph, "log_llm_prompt", lambda *args, **kwargs: captured.update(kwargs))
    callback = graph._UsageCallback("test")
    config = {"tools": [{"type": "function", "function": {"name": "search_flights"}}]}
    callback.on_chat_model_start(
        {}, [[HumanMessage(content="add flights")]], invocation_params=config,
    )
    assert json.loads(captured["full_prompt_text"].split("[tool configuration] ")[1]) == config
