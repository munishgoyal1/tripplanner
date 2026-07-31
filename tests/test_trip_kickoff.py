from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from tripplanner import graph as graph_mod
from tripplanner.graph import _trip_kickoff_tool_choice


@pytest.fixture(autouse=True)
def _no_active_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph_mod, "load_active_trip_dict", lambda: None)


def _tool_message(name: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": name}])


def test_new_paris_trip_loads_preferences_before_kickoff() -> None:
    messages = [HumanMessage(content="Plan Paris from Delhi for five days in October")]

    assert _trip_kickoff_tool_choice(messages) == "get_travel_preferences"


def test_new_paris_trip_forces_prefilled_kickoff_after_preferences() -> None:
    messages = [
        HumanMessage(content="Plan Paris from Delhi for five days in October"),
        _tool_message("get_travel_preferences"),
    ]

    assert _trip_kickoff_tool_choice(messages) == "request_trip_input"


def test_kickoff_is_not_repeated_after_user_answers() -> None:
    messages = [
        HumanMessage(content="Plan Paris from Delhi for five days in October"),
        _tool_message("get_travel_preferences"),
        _tool_message("request_trip_input"),
        HumanMessage(content="Use these choices for this trip: relaxed pace"),
    ]

    assert _trip_kickoff_tool_choice(messages) is None


def test_non_planning_conversation_has_no_kickoff() -> None:
    assert _trip_kickoff_tool_choice([HumanMessage(content="Hello")]) is None


def test_active_trip_follow_up_has_no_kickoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Paris"},
    )

    assert _trip_kickoff_tool_choice(
        [HumanMessage(content="Make my Paris trip more relaxed")]
    ) is None


def test_active_trip_explicit_new_trip_starts_fresh_kickoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Paris"},
    )

    assert _trip_kickoff_tool_choice(
        [HumanMessage(content="Create a separate new Hawaii trip")]
    ) == "get_travel_preferences"


def test_trip_agent_forces_creation_after_kickoff_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [
        HumanMessage(content="Create a separate new Hawaii trip"),
        _tool_message("get_travel_preferences"),
        _tool_message("request_trip_input"),
        HumanMessage(content="Use these choices and build it"),
    ]
    bound_options: dict = {}

    class FakeBoundModel:
        def invoke(self, _messages: list) -> AIMessage:
            return AIMessage(content="")

    class FakeModel:
        def bind_tools(self, tools: list, **options: object) -> FakeBoundModel:
            bound_options["tools"] = [tool.name for tool in tools]
            bound_options.update(options)
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "load_active_trip_dict", lambda: {"destination": "Paris"})
    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())

    graph_mod.trip_agent({
        "messages": messages,
        "current_agent": "",
        "proposal_only": False,
    })

    assert bound_options["tool_choice"] == "create_trip_plan"
    assert bound_options["tools"] == ["create_trip_plan"]


def test_new_trip_intent_preempts_incomplete_active_trip_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [HumanMessage(content="Create a separate new Hawaii trip")]
    bound_options: dict = {}

    class FakeBoundModel:
        def invoke(self, _messages: list) -> AIMessage:
            return AIMessage(content="")

    class FakeModel:
        def bind_tools(self, tools: list, **options: object) -> FakeBoundModel:
            bound_options["tools"] = [tool.name for tool in tools]
            bound_options.update(options)
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "load_active_trip_dict", lambda: {
        "destination": "Paris",
        "day_wise_itinerary": [],
    })
    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())

    graph_mod.trip_agent({
        "messages": messages,
        "current_agent": "",
        "proposal_only": False,
    })

    assert bound_options["tool_choice"] == "get_travel_preferences"
    assert bound_options["tools"] == ["get_travel_preferences"]


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        ([HumanMessage(content="Plan a Paris trip")], "get_travel_preferences"),
        (
            [
                HumanMessage(content="Plan a Paris trip"),
                _tool_message("get_travel_preferences"),
            ],
            "request_trip_input",
        ),
    ],
)
def test_trip_agent_forces_kickoff_tool(
    monkeypatch: pytest.MonkeyPatch,
    messages: list,
    expected: str,
) -> None:
    bound_options: dict = {}

    class FakeBoundModel:
        def invoke(self, _messages: list) -> AIMessage:
            return AIMessage(content="")

    class FakeModel:
        def bind_tools(self, _tools: list, **options: object) -> FakeBoundModel:
            bound_options.update(options)
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())
    monkeypatch.setattr(graph_mod, "select_tools", lambda *_args, **_kwargs: [])

    graph_mod.trip_agent({
        "messages": messages,
        "current_agent": "",
        "proposal_only": False,
    })

    assert bound_options["tool_choice"] == expected