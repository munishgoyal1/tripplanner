from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from tripplanner import graph as graph_mod
from tripplanner.graph import _trip_creation_tool_choice, _trip_kickoff_tool_choice


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

    assert _trip_kickoff_tool_choice(messages) == "recommend_trip_duration"


def test_direct_mode_does_not_force_a_prefilled_review_after_duration_advice() -> None:
    messages = [
        HumanMessage(content="Plan Paris from Delhi for five days in October"),
        _tool_message("get_travel_preferences"),
        _tool_message("recommend_trip_duration"),
    ]

    assert _trip_kickoff_tool_choice(messages) is None


def test_kickoff_is_not_repeated_after_user_answers() -> None:
    messages = [
        HumanMessage(content="Plan Paris from Delhi for five days in October"),
        _tool_message("get_travel_preferences"),
        _tool_message("recommend_trip_duration"),
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


def test_explicit_destination_switch_requires_new_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "London"},
    )

    assert _trip_creation_tool_choice(
        [HumanMessage(content="plan a trip to hawaii")]
    ) == "create_trip_plan"


def test_destination_switch_asks_the_kickoff_before_creating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Mussoorie"},
    )

    assert _trip_kickoff_tool_choice(
        [HumanMessage(content="plan a trip to dehradun")]
    ) == "get_travel_preferences"


def test_duration_advice_leaves_the_optional_input_request_to_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Mussoorie"},
    )
    messages = [
        HumanMessage(content="plan a trip to dehradun"),
        _tool_message("get_travel_preferences"),
        _tool_message("recommend_trip_duration"),
    ]

    assert _trip_kickoff_tool_choice(messages) is None


def test_same_destination_follow_up_still_has_no_kickoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "Dehradun"},
    )

    assert _trip_kickoff_tool_choice(
        [HumanMessage(content="plan my trip to Dehradun in more detail")]
    ) is None


def test_day_trip_switch_has_no_kickoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "London"},
    )

    assert _trip_kickoff_tool_choice(
        [HumanMessage(content="Plan a day trip to Oxford")]
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


def test_active_destination_follow_up_does_not_create_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "London"},
    )

    assert _trip_creation_tool_choice(
        [HumanMessage(content="Plan my trip to London in more detail")]
    ) is None


def test_day_trip_does_not_replace_active_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        graph_mod,
        "load_active_trip_dict",
        lambda: {"destination": "London"},
    )

    assert _trip_creation_tool_choice(
        [HumanMessage(content="Plan a day trip to Oxford")]
    ) is None


def test_trip_agent_forces_creation_after_kickoff_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [
        HumanMessage(content="Create a separate new Hawaii trip"),
        _tool_message("get_travel_preferences"),
        _tool_message("recommend_trip_duration"),
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
            "recommend_trip_duration",
        ),
        (
            [
                HumanMessage(content="Plan a Paris trip"),
                _tool_message("get_travel_preferences"),
                _tool_message("recommend_trip_duration"),
            ],
            None,
        ),
    ],
)
def test_trip_agent_forces_kickoff_tool(
    monkeypatch: pytest.MonkeyPatch,
    messages: list,
    expected: str | None,
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

    if expected is None:
        assert "tool_choice" not in bound_options
    else:
        assert bound_options["tool_choice"] == expected


def test_direct_mode_hides_the_optional_input_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    bound_tools: list[str] = []

    class FakeBoundModel:
        def invoke(self, _messages: list) -> AIMessage:
            return AIMessage(content="")

    class FakeModel:
        def bind_tools(self, tools: list, **_options: object) -> FakeBoundModel:
            bound_tools.extend(tool.name for tool in tools)
            return FakeBoundModel()

    monkeypatch.setattr(graph_mod, "_get_llm", lambda: FakeModel())
    monkeypatch.setattr(graph_mod, "_interactive_trip_questions", lambda: False)

    graph_mod.trip_agent({
        "messages": [
            HumanMessage(content="Plan a Paris trip"),
            _tool_message("get_travel_preferences"),
            _tool_message("recommend_trip_duration"),
        ],
        "current_agent": "",
        "proposal_only": False,
    })

    assert "request_trip_input" not in bound_tools