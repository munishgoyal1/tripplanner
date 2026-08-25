"""Unit tests for the SSE tool-input summarizer used in /chat/stream."""

from __future__ import annotations

import inspect
import re

from tripplanner import api
from tripplanner.api import (
    _auto_persist_itinerary,
    _best_effort_plan_reply,
    _should_auto_persist_itinerary,
    _summarize_tool_input,
)


def test_summarize_none_is_empty() -> None:
    assert _summarize_tool_input(None) == ""


def test_summarize_dict_emits_key_value_pairs() -> None:
    out = _summarize_tool_input({"city": "Paris", "nights": 5})
    assert "city=Paris" in out
    assert "nights=5" in out


def test_summarize_unwraps_input_wrapper() -> None:
    # LangChain often wraps the args in {"input": {...}}.
    out = _summarize_tool_input({"input": {"q": "best ramen"}})
    assert out == "q=best ramen"


def test_summarize_truncates_long_values() -> None:
    long = "x" * 200
    out = _summarize_tool_input({"q": long}, max_len=80)
    assert len(out) <= 80
    # Either the per-value cap (40 chars → "...") or the overall cap (→ "…")
    # has to have kicked in, otherwise we leaked the whole 200-char string.
    assert out.endswith("...") or out.endswith("\u2026")
    assert long not in out


def test_summarize_handles_list_values() -> None:
    out = _summarize_tool_input({"tags": ["a", "b", "c"]})
    assert "tags=" in out
    assert "a" in out and "c" in out


def test_auto_persist_itinerary_invokes_update_tool(monkeypatch) -> None:
    from tripplanner.tools import trip_planner

    calls: list[dict] = []

    class FakeUpdateTool:
        def invoke(self, value: dict) -> None:
            calls.append(value)

    monkeypatch.setattr(trip_planner, "update_trip_plan", FakeUpdateTool())
    monkeypatch.setattr(
        trip_planner,
        "load_active_trip_dict",
        lambda: {"day_wise_itinerary": [{"day": 1}]},
    )

    persisted = _auto_persist_itinerary(
        "Day 1 - Arrival\nVisit **Louvre Museum**.\n"
        "Day 2 - Montmartre\nExplore **Sacré-Cœur**."
    )

    assert persisted
    assert len(calls) == 1
    assert "updates_json" in calls[0]


def test_auto_persist_itinerary_recovers_plain_bullet_stops(monkeypatch) -> None:
    import json

    from tripplanner.tools import trip_planner

    calls: list[dict] = []

    class FakeUpdateTool:
        def invoke(self, value: dict) -> None:
            calls.append(value)

    monkeypatch.setattr(trip_planner, "update_trip_plan", FakeUpdateTool())
    monkeypatch.setattr(
        trip_planner,
        "load_active_trip_dict",
        lambda: {"day_wise_itinerary": [{"day": 1}]},
    )

    _auto_persist_itinerary(
        "Day 1: Arrival in Srinagar\n- Check in to your hotel\n- Shikara ride\n"
        "Day 2: Srinagar sightseeing\n- Visit Dachigam National Park\n- Nishat Bagh"
    )

    updates = json.loads(calls[0]["updates_json"])
    assert updates["day_wise_itinerary"][0]["stops"][0]["name"] == (
        "Check in to your hotel"
    )
    assert updates["day_wise_itinerary"][1]["stops"][0]["name"] == (
        "Visit Dachigam National Park"
    )


def test_auto_persist_reports_rejected_update_as_not_persisted(monkeypatch) -> None:
    from tripplanner.tools import trip_planner

    class FakeUpdateTool:
        def invoke(self, _value: dict) -> str:
            return "Error: rejected itinerary"

    monkeypatch.setattr(trip_planner, "update_trip_plan", FakeUpdateTool())
    monkeypatch.setattr(
        trip_planner,
        "load_active_trip_dict",
        lambda: {"day_wise_itinerary": []},
    )

    assert not _auto_persist_itinerary(
        "Day 1: Arrival\n- Check in\nDay 2: Explore\n- Visit the museum"
    )


def test_auto_persist_requires_trip_created_in_same_turn(monkeypatch) -> None:
    from tripplanner.tools import trip_planner

    monkeypatch.setattr(
        trip_planner,
        "load_active_trip_dict",
        lambda: {"destination": "Paris", "day_wise_itinerary": []},
    )
    assert not _should_auto_persist_itinerary(set())
    assert not _should_auto_persist_itinerary({"search_hotels"})
    assert _should_auto_persist_itinerary({"create_trip_plan"})
    assert _should_auto_persist_itinerary({"update_trip_plan"})
    assert _should_auto_persist_itinerary({"create_trip_plan", "update_trip_plan"})


def test_auto_persist_does_not_replace_a_successful_structured_save(monkeypatch) -> None:
    from tripplanner.tools import trip_planner

    monkeypatch.setattr(
        trip_planner,
        "load_active_trip_dict",
        lambda: {"day_wise_itinerary": [{"day": 1, "stops": [{"name": "Louvre"}]}]},
    )

    assert not _should_auto_persist_itinerary({"create_trip_plan", "update_trip_plan"})


def test_tool_timing_does_not_overwrite_chat_request_start() -> None:
    source = inspect.getsource(api.chat_stream)

    assert "tool_started = tool_starts.pop" in source
    assert re.search(r"^\s*started = tool_starts\.pop", source, re.MULTILINE) is None


def test_graph_recursion_uses_explicit_limit_and_best_effort_recovery() -> None:
    source = inspect.getsource(api.chat_stream)

    assert 'config={"recursion_limit": _CHAT_GRAPH_RECURSION_LIMIT}' in source
    assert "except GraphRecursionError" in source


def test_json_chat_handles_budget_exhaustion_like_the_stream() -> None:
    # Native and scripted clients post here; an unhandled overflow returned 500
    # and left the freshly created trip with no itinerary.
    source = inspect.getsource(api.chat)

    assert 'config={"recursion_limit": _CHAT_GRAPH_RECURSION_LIMIT}' in source
    assert "except GraphRecursionError" in source
    assert "_best_effort_plan_reply" in source


def test_recursion_limit_outlasts_the_policy_tool_budget() -> None:
    # The policy degrades gracefully by forcing the still-owed first itinerary
    # save; LangGraph's step counter just raises. A turn that spends every tool
    # phase and both forced saves has to fit, or the trip is saved with no days.
    from tripplanner import graph_policy

    nodes_per_phase = 2
    worst_case = nodes_per_phase * (
        graph_policy.MAX_TOOL_PHASES_PER_TURN + graph_policy.MAX_INITIAL_ITINERARY_UPDATES
    ) + 1
    assert api._CHAT_GRAPH_RECURSION_LIMIT > worst_case


def test_best_effort_plan_reply_reports_saved_plan_gaps(monkeypatch) -> None:
    from tripplanner.tools import trip_planner

    monkeypatch.setattr(
        trip_planner,
        "load_active_trip_dict",
        lambda: {
            "destination": "Punjab",
            "day_wise_itinerary": [{"day": 1, "stops": []}],
        },
    )
    monkeypatch.setattr(
        trip_planner,
        "planning_completion_gaps",
        lambda _trip: ["Day 1 has no planned places beyond the hotel."],
    )

    reply, gap_count = _best_effort_plan_reply()

    assert "saved the best available Punjab itinerary" in reply
    assert "Day 1" in reply
    assert gap_count == 1


def test_json_chat_also_rescues_a_narrated_itinerary() -> None:
    """The agent sometimes writes the plan out instead of saving it.

    The SSE path has recovered that for a while. Without the same net on /chat a
    native or scripted caller keeps a trip with no days, which is what the corpus
    builder produced on 2026-08-16.
    """
    source = inspect.getsource(api.chat)

    assert "_should_auto_persist_itinerary" in source
    assert "_auto_persist_itinerary" in source
