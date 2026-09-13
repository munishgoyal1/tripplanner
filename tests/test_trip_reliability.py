from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tripplanner import model_recovery, ops_metrics
from tripplanner.hotel_research import current_hotel_research, lodging_concern
from tripplanner.tools import hotel_search
from tripplanner.web.day_journey import plan_day_journeys
from tripplanner.web.itinerary_view import _measure_local_route
from tripplanner.web.map_view import build


@pytest.fixture(autouse=True)
def no_recovery_delay(monkeypatch):
    from contextvars import ContextVar

    from tripplanner import graph as graph_mod

    monkeypatch.setattr(graph_mod, "_CURRENT_TURN_PHASE", ContextVar("test-phase", default=None))
    monkeypatch.setattr(model_recovery.time, "sleep", lambda _: None)
    ops_metrics.reset()


@pytest.mark.parametrize("failure", [httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout])
def test_model_recovery_retries_only_current_call(failure):
    history = [
        HumanMessage(content="Add flights"),
        AIMessage(content="", tool_calls=[{"name": "save", "args": {}, "id": "saved"}]),
        ToolMessage(content="Already saved", tool_call_id="saved"),
    ]
    calls = []

    def invoke(messages):
        calls.append(messages)
        if len(calls) == 1:
            raise failure("stream broke")
        return AIMessage(content="Saved")

    reply = model_recovery.invoke_model(SimpleNamespace(invoke=invoke), history)
    assert reply.content == "Saved"
    assert calls == [history, history]
    assert ops_metrics.snapshot()["model_recovery"] == {
        "calls": 1,
        "recovered": 1,
        "exhausted": 0,
        "recovery_rate": 1.0,
    }


@pytest.mark.parametrize("failure,count", [(httpx.RemoteProtocolError, 2), (ValueError, 1)])
def test_model_recovery_is_bounded_and_does_not_retry_programming_errors(failure, count):
    calls = []

    def invoke(messages):
        calls.append(messages)
        raise failure("failure")

    with pytest.raises(failure):
        model_recovery.invoke_model(SimpleNamespace(invoke=invoke), [])
    assert len(calls) == count
    assert ops_metrics.snapshot()["model_recovery"]["exhausted"] == count - 1


def test_reliability_rates_have_independent_denominators():
    assert ops_metrics.snapshot()["chat_turns"]["completion_rate"] is None
    ops_metrics.record_chat_turn("a", "completed", 10)
    ops_metrics.record_chat_turn("b", "error", 20)
    ops_metrics.record_model_recovery("recovered")
    ops_metrics.record_model_recovery("exhausted")
    assert ops_metrics.snapshot()["chat_turns"]["completion_rate"] == 0.5
    assert ops_metrics.snapshot()["model_recovery"]["recovery_rate"] == 0.5


def _property(city="Srinagar"):
    return {
        "name": "Lake Hotel",
        "place_id": "lake-hotel",
        "address": f"Lake Road, {city}",
        "rating": 4.5,
        "types": ["lodging"],
        "lat": 34.1,
        "lng": 74.8,
    }


@pytest.mark.parametrize("inventory", ["unconfigured", "empty", "error"])
def test_one_grounded_hotel_survives_missing_room_offers(monkeypatch, inventory):
    monkeypatch.setattr(
        hotel_search,
        "get_hotel_providers",
        lambda: [] if inventory == "unconfigured" else [object()],
    )
    monkeypatch.setattr(hotel_search.amadeus_client, "is_configured", lambda: False)
    monkeypatch.setattr(
        hotel_search,
        "run_provider_chain",
        lambda **_: SimpleNamespace(
            value=[], errors=["test: no availability" if inventory == "empty" else "test: timeout"]
        ),
    )
    calls = []
    monkeypatch.setattr(
        hotel_search,
        "search_places_with_reviews",
        SimpleNamespace(invoke=lambda args: calls.append(args) or json.dumps([_property()])),
    )
    result = json.loads(
        hotel_search.search_hotels.invoke(
            {"city": "Srinagar", "checkin": "2027-04-05", "checkout": "2027-04-12"}
        )
    )
    assert len(calls) == 1
    assert result["hotel_research"]["candidate_count"] == 1
    assert result["hotel_research"]["status"] == "candidates_available"
    assert result["quote_status"] == "unverified"
    assert result["candidates"][0]["name"] == "Lake Hotel"
    assert "price" not in result["candidates"][0]


@pytest.mark.parametrize(
    "raw,reason",
    [
        ("No places found.", "no_results"),
        ("Google Places search failed", "provider_unavailable"),
        (json.dumps([_property("Pahalgam")]), "no_suitable_property"),
    ],
)
def test_hotel_tbd_has_a_city_specific_reason(monkeypatch, raw, reason):
    monkeypatch.setattr(
        hotel_search, "search_places_with_reviews", SimpleNamespace(invoke=lambda _: raw)
    )
    result = hotel_search._places_fallback(
        "Srinagar", "2027-04-05", "2027-04-12", 5, "no_availability"
    )
    messages = [
        HumanMessage(content="Plan Kashmir"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_hotels", "id": "hotels", "args": {"city": "Srinagar"}}],
        ),
        ToolMessage(content=result, tool_call_id="hotels"),
    ]
    research = current_hotel_research(messages)
    assert research["srinagar"]["reason"] == reason
    concern = lodging_concern(
        {"name": "Hotel TBD - Srinagar"}, {"lodging_research": research}, "2027-04-07"
    )
    assert "Hotel TBD:" in concern and "no matching hotel research" not in concern
    assert "no matching hotel research" in lodging_concern(
        {"name": "Hotel TBD - Gulmarg"}, {"lodging_research": research}, "2027-04-07"
    )
    assert current_hotel_research([*messages, HumanMessage(content="New dates")]) == {}


def test_itinerary_measures_local_stops_on_both_sides_of_transfers():
    stops = [
        {"name": "Srinagar Hotel", "kind": "hotel"},
        {"name": "Breakfast", "kind": "meal"},
        {"name": "Drive: Srinagar to Gulmarg", "kind": "transport"},
        {"name": "Gondola", "kind": "attraction"},
        {"name": "Lunch", "kind": "meal"},
        {"name": "Drive: Gulmarg to Srinagar", "kind": "transport"},
        {"name": "Gardens", "kind": "attraction"},
        {"name": "Srinagar Hotel", "kind": "hotel"},
    ]
    coords = {
        name.casefold(): point
        for name, point in [
            ("Srinagar Hotel", (34.1, 74.8)),
            ("Breakfast", (34.11, 74.8)),
            ("Gondola", (34.04, 74.39)),
            ("Lunch", (34.05, 74.40)),
            ("Gardens", (34.15, 74.87)),
        ]
    }
    local, groups = _measure_local_route(stops, coords)
    assert len(groups) == 3
    assert [len(group) for group in groups] == [2, 2, 2]
    assert local[0]["name"] == "Srinagar Hotel"
    assert stops[1]["travel_from_previous"]
    assert "travel_from_previous" not in stops[3]
    assert stops[4]["travel_from_previous"]


def test_unresolved_flight_preserves_both_ground_segments_without_bridge():
    coords = {
        "Hotel A": (34.1, 74.8),
        "Park A": (34.11, 74.81),
        "Hotel B": (28.6, 77.2),
        "Park B": (28.61, 77.21),
    }
    pins = [
        {
            "id": name,
            "name": name,
            "_source_name": name,
            "kind": "hotel" if "Hotel" in name else "attraction",
            "selected": True,
            "lat": coord[0],
            "lng": coord[1],
            "day": 3,
        }
        for name, coord in coords.items()
    ]
    lookup = {pin["name"]: pin for pin in pins}
    stops = [{"name": name, "kind": lookup[name]["kind"]} for name in coords]
    stops.insert(2, {"name": "Flight: Srinagar to Delhi", "kind": "flight"})
    entry = {"day": 3, "stops": stops}
    journey = plan_day_journeys([entry], resolve_pin=lambda name, _: lookup.get(name))[0][3]
    assert journey.completed_segments == [["Hotel A", "Park A"]]
    view = build({"day_wise_itinerary": [entry]}, "India", pins, None, {3: entry}, True)
    edges = {(leg["from_pin_id"], leg["to_pin_id"]) for leg in view["days"][0]["legs"]}
    assert edges == {("Hotel A", "Park A"), ("Hotel B", "Park B")}


@pytest.mark.parametrize(
    "day_city, hotel_location", [("Srinagar", {}), ("", {}), ("", {"destination": "Kashmir"})]
)
def test_city_placeholder_cannot_borrow_a_name_only_hotel_in_another_city(day_city, hotel_location):
    from tripplanner.tools.trip_planner import _sync_replaced_hotel_anchors

    plan = {
        "destination": "Kashmir",
        "day_wise_itinerary": [
            {"city": day_city, "stops": [{"name": "Hotel TBD - Srinagar", "kind": "hotel"}]}
        ],
    }
    assert not _sync_replaced_hotel_anchors(
        plan, [], [{"name": "Pine N Peak, Pahalgam", **hotel_location}]
    )
    assert plan["day_wise_itinerary"][0]["stops"][0]["name"] == "Hotel TBD - Srinagar"


def test_graph_attaches_actual_hotel_research_to_the_save(monkeypatch):
    from tripplanner import graph as graph_mod

    research = {
        "city": "Srinagar",
        "checkin": "2027-04-05",
        "checkout": "2027-04-12",
        "reason": "rate_and_availability_unverified",
        "status": "candidates_available",
    }
    history = [
        HumanMessage(content="Choose the hotel"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_hotels", "id": "hotels", "args": {"city": "Srinagar"}}],
        ),
        ToolMessage(
            content=json.dumps({"hotel_research": research, "candidates": [_property()]}),
            tool_call_id="hotels",
        ),
    ]

    class Model:
        def bind_tools(self, *args, **kwargs):
            return self

        def invoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "update_trip_plan",
                        "id": "save",
                        "args": {
                            "updates_json": json.dumps(
                                {"selected_hotels": [{"name": "Lake Hotel"}]}
                            )
                        },
                    }
                ],
            )

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: Model())
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {
            "destination": "Kashmir",
            "selected_hotels": [],
            "day_wise_itinerary": [{"day": 1}],
        },
    )
    output = graph_mod.trip_agent(
        {"messages": history, "current_agent": "", "proposal_only": False}
    )
    patch = json.loads(output["messages"][0].tool_calls[0]["args"]["updates_json"])
    assert patch["lodging_research"]["srinagar"]["reason"] == research["reason"]
    assert lodging_concern({"name": "Lake Hotel"}, patch).startswith("Recommended property;")


def test_kashmir_style_return_drive_connects_first_grounded_stop():
    coords = {
        "Srinagar Hotel": (34.1, 74.8),
        "Gondola": (34.04, 74.39),
        "Lunch": (34.05, 74.4),
        "Gardens": (34.15, 74.87),
    }
    pins = [
        {
            "id": name,
            "name": name,
            "_source_name": name,
            "day": 3,
            "kind": "hotel" if "Hotel" in name else "meal" if name == "Lunch" else "attraction",
            "selected": True,
            "lat": point[0],
            "lng": point[1],
        }
        for name, point in coords.items()
    ]
    lookup = {pin["name"]: pin for pin in pins}
    stops = [{"name": name, "kind": lookup[name]["kind"]} for name in coords]
    stops.insert(1, {"name": "Drive: Srinagar to Gulmarg", "kind": "transport"})
    stops.insert(4, {"name": "Drive: Gulmarg to Srinagar", "kind": "transport"})
    stops.append({"name": "Srinagar Hotel", "kind": "hotel"})
    entry = {"day": 3, "stops": stops}
    view = build({"day_wise_itinerary": [entry]}, "Kashmir", pins, None, {3: entry}, True)
    edges = {(leg["from_pin_id"], leg["to_pin_id"]) for leg in view["days"][0]["legs"]}
    assert ("Srinagar Hotel", "Gondola") in edges
    assert ("Gondola", "Lunch") in edges
    assert ("Lunch", "Gardens") in edges
    assert ("Gardens", "Srinagar Hotel") in edges


@pytest.mark.parametrize("persistent", [False, True])
def test_sse_model_recovery_discards_fragments_and_never_replays_saved_tools(
    monkeypatch, persistent
):
    import asyncio

    from fastapi.testclient import TestClient
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk
    from langchain_core.tools import tool
    from langgraph.graph import END, StateGraph
    from langgraph.prebuilt import ToolNode

    from tripplanner import api
    from tripplanner import graph as graph_mod
    from tripplanner.graph import AgentState
    from tripplanner.request_limits import chat_admission

    class DisconnectingModel(BaseChatModel):
        attempts: int = 0

        @property
        def _llm_type(self):
            return "fault-injection"

        def _generate(self, *args, **kwargs):
            raise AssertionError("SSE must exercise model streaming")

        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            self.attempts += 1
            if persistent or self.attempts == 1:
                yield ChatGenerationChunk(message=AIMessageChunk(content="Discard this fragment"))
                raise httpx.RemoteProtocolError("connection closed during response")
            yield ChatGenerationChunk(message=AIMessageChunk(content="Flights saved"))

    saved_tools = []
    saved_chats = []

    @tool
    def save_flight():
        """Save the chosen flight once."""
        saved_tools.append("saved")
        return "Flight saved"

    model = DisconnectingModel()

    def trip_agent(state):
        return {
            "messages": [model_recovery.invoke_model(model, state["messages"])],
            "current_agent": "trip",
        }

    builder = StateGraph(AgentState)
    builder.add_node("tools", ToolNode([save_flight]))
    builder.add_node("trip_agent", trip_agent)
    builder.set_entry_point("tools")
    builder.add_edge("tools", "trip_agent")
    builder.add_edge("trip_agent", END)
    monkeypatch.setattr(graph_mod, "app_graph", builder.compile())

    async def reserve(*_args):
        return None

    history = [
        HumanMessage(content="Add flights"),
        AIMessage(content="", tool_calls=[{"name": "save_flight", "args": {}, "id": "save-once"}]),
    ]
    monkeypatch.setattr(api, "_reserve_cost", reserve)
    monkeypatch.setattr(api, "_completed_chat_request", lambda _: None)
    monkeypatch.setattr(api, "_load_chat_request", lambda _: ("kashmir", history, None))
    monkeypatch.setattr(api, "_save_chat", lambda *args: saved_chats.append(args) or "kashmir")
    monkeypatch.setattr(api, "_schedule_learning_sweep", lambda *_: None)
    monkeypatch.setattr(api, "_should_auto_persist_itinerary", lambda _: False)
    asyncio.run(chat_admission.reset())
    try:
        response = TestClient(api.app).post(
            "/chat/stream",
            json={
                "user_id": "recovery-test",
                "message": "Add flights",
                "request_id": "recover-once",
            },
        )
    finally:
        asyncio.run(chat_admission.reset())
    assert response.status_code == 200
    assert model.attempts == 2
    assert saved_tools == ["saved"]
    assert "Discard this fragment" not in response.text
    assert ("event: error" in response.text) is persistent
    reply = saved_chats[-1][2][-1].content
    assert reply == ("(interrupted)" if persistent else "Flights saved")
    metrics = ops_metrics.snapshot()
    assert metrics["chat_turns"]["completion_rate"] == (0 if persistent else 1)
    assert metrics["model_recovery"]["recovery_rate"] == (0 if persistent else 1)


def test_closing_sse_before_completion_counts_as_interrupted(monkeypatch):
    import asyncio
    import time

    from starlette.requests import Request

    from tripplanner import api
    from tripplanner.chat_turn import AdmittedTurn

    class Coordinator:
        async def admit(self, **kwargs):
            return AdmittedTurn(
                started=time.monotonic(),
                transport="sse",
                user_id="cancel-test",
                request_id="cancel",
                permit=None,
                history_trip_id="kashmir",
                history=[],
                base_history=[],
            )

        async def close(self, turn):
            pass

    monkeypatch.setattr(api, "_set_request_user", lambda *args: "cancel-test")
    monkeypatch.setattr(api, "_chat_turn_coordinator", lambda *args: Coordinator())

    async def run():
        response = await api.chat_stream(
            api.ChatRequest(message="Add flights", request_id="cancel"),
            Request({"type": "http", "headers": []}),
        )
        assert "event: progress" in await anext(response.body_iterator)
        await response.body_iterator.aclose()

    asyncio.run(run())
    assert ops_metrics.snapshot()["chat_turns"]["outcomes"] == {"interrupted": 1}
    assert ops_metrics.snapshot()["chat_turns"]["completion_rate"] == 0
