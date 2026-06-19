"""Tests for the per-trip chat transcript store (web/chat_store.py)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tripplanner.web import chat_store

_TEST_CHATS = Path.home() / ".tripplanner_chat_test" / "chats"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat_store, "_CHATS_DIR", _TEST_CHATS)
    _TEST_CHATS.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(_TEST_CHATS.parent, ignore_errors=True)


def _convo() -> list:
    return [
        HumanMessage(content="Plan a trip to Goa"),
        AIMessage(content="Sure! When would you like to go?"),
    ]


def test_save_and_load_roundtrip() -> None:
    chat_store.save("goa_2026-01-10_2026-01-15", _convo())
    loaded = chat_store.load("goa_2026-01-10_2026-01-15")
    assert [m.type for m in loaded] == ["human", "ai"]
    assert loaded[0].content == "Plan a trip to Goa"
    assert loaded[1].content == "Sure! When would you like to go?"


def test_transcript_shape() -> None:
    chat_store.save("goa_2026-01-10_2026-01-15", _convo())
    rows = chat_store.transcript("goa_2026-01-10_2026-01-15")
    assert rows == [
        {"role": "user", "text": "Plan a trip to Goa"},
        {"role": "assistant", "text": "Sure! When would you like to go?"},
    ]


def test_missing_bucket_is_empty() -> None:
    assert chat_store.load("does_not_exist") == []
    assert chat_store.transcript("does_not_exist") == []


def test_general_bucket_for_no_trip() -> None:
    chat_store.save(None, _convo())
    # Stored under the shared "_general" bucket, readable via None.
    assert len(chat_store.load(None)) == 2
    assert (_TEST_CHATS / "chat__general.json").exists()


def test_buckets_are_isolated_per_trip() -> None:
    chat_store.save("mumbai_1_2", [HumanMessage(content="Mumbai chat")])
    chat_store.save("vietnam_3_4", [HumanMessage(content="Vietnam chat")])
    assert chat_store.transcript("mumbai_1_2")[0]["text"] == "Mumbai chat"
    assert chat_store.transcript("vietnam_3_4")[0]["text"] == "Vietnam chat"


def test_blank_turns_are_dropped() -> None:
    chat_store.save(
        "t",
        [HumanMessage(content="hi"), AIMessage(content="   "), AIMessage(content="ok")],
    )
    rows = chat_store.transcript("t")
    assert [r["text"] for r in rows] == ["hi", "ok"]


def test_clear_removes_bucket() -> None:
    chat_store.save("t", _convo())
    chat_store.clear("t")
    assert chat_store.transcript("t") == []


def test_save_overwrites_with_latest() -> None:
    chat_store.save("t", [HumanMessage(content="first")])
    chat_store.save("t", [HumanMessage(content="first"), AIMessage(content="second")])
    rows = chat_store.transcript("t")
    assert [r["text"] for r in rows] == ["first", "second"]

