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

    _auto_persist_itinerary(
        "Day 1 - Arrival\nVisit **Louvre Museum**.\n"
        "Day 2 - Montmartre\nExplore **Sacré-Cœur**."
    )

    assert len(calls) == 1
    assert "updates_json" in calls[0]


def test_auto_persist_requires_trip_created_in_same_turn() -> None:
    assert not _should_auto_persist_itinerary(set())
    assert not _should_auto_persist_itinerary({"search_hotels"})
    assert _should_auto_persist_itinerary({"create_trip_plan"})
    assert not _should_auto_persist_itinerary(
        {"create_trip_plan", "update_trip_plan"}
    )


def test_tool_timing_does_not_overwrite_chat_request_start() -> None:
    source = inspect.getsource(api.chat_stream)

    assert "tool_started = tool_starts.pop" in source
    assert re.search(r"^\s*started = tool_starts\.pop", source, re.MULTILINE) is None


def test_graph_recursion_uses_explicit_limit_and_best_effort_recovery() -> None:
    source = inspect.getsource(api.chat_stream)

    assert 'config={"recursion_limit": _CHAT_GRAPH_RECURSION_LIMIT}' in source
    assert "except GraphRecursionError" in source


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
