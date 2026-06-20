"""Tests for mid-chat destination switch: carryover distill + chat bucketing."""

from __future__ import annotations

import importlib

from langchain_core.messages import AIMessage, HumanMessage

from tripplanner.web import chat_carryover, chat_store


def test_distill_empty_transcript_returns_blank():
    assert chat_carryover.distill([], "Mexico", "Kashmir") == ""


def test_distill_no_config_returns_blank(monkeypatch):
    # No Azure config -> best-effort returns "".
    from tripplanner import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "azure_openai_endpoint", "", raising=False)
    monkeypatch.setattr(settings, "azure_openai_api_key", "", raising=False)
    msgs = [HumanMessage(content="2 adults, mid budget"), AIMessage(content="Great!")]
    assert chat_carryover.distill(msgs, "Mexico", "Kashmir") == ""


def _use_temp_chats(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_store, "_CHATS_DIR", tmp_path / "chats", raising=False)
    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: False)


def test_persist_turn_no_change_saves_history(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    history = [HumanMessage(content="hi"), AIMessage(content="hello")]
    out = chat_store.persist_turn("mexico_x_y", "mexico_x_y", history)
    assert out == "mexico_x_y"
    assert chat_store.transcript("mexico_x_y") == [
        {"role": "user", "text": "hi"},
        {"role": "assistant", "text": "hello"},
    ]


def test_persist_turn_first_trip_migrates_general(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    history = [HumanMessage(content="plan goa"), AIMessage(content="sure!")]
    out = chat_store.persist_turn(None, "goa_a_b", history)
    assert out == "goa_a_b"
    assert len(chat_store.transcript("goa_a_b")) == 2
    assert chat_store.transcript(None) == []


def test_persist_turn_switch_keeps_prev_and_seeds_new(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    # Mexico bucket already has prior turns.
    mexico = [
        HumanMessage(content="plan mexico, 2 adults"),
        AIMessage(content="Mexico draft ready"),
    ]
    chat_store.save("mexico_x_y", mexico)

    # The switch turn: full history is mexico + the new switch turn.
    history = mexico + [
        HumanMessage(content="actually plan kashmir"),
        AIMessage(content="Switching to Kashmir!"),
    ]
    out = chat_store.persist_turn(
        "mexico_x_y", "kashmir_p_q", history, carryover_text="Carrying over: 2 adults."
    )
    assert out == "kashmir_p_q"

    # Mexico bucket untouched.
    assert chat_store.transcript("mexico_x_y") == [
        {"role": "user", "text": "plan mexico, 2 adults"},
        {"role": "assistant", "text": "Mexico draft ready"},
    ]
    # Kashmir bucket: carryover note + the switch turn only (no Mexico verbatim).
    kashmir = chat_store.transcript("kashmir_p_q")
    assert kashmir == [
        {"role": "assistant", "text": "Carrying over: 2 adults."},
        {"role": "user", "text": "actually plan kashmir"},
        {"role": "assistant", "text": "Switching to Kashmir!"},
    ]


def test_persist_turn_switch_to_existing_appends(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    chat_store.save("kashmir_p_q", [HumanMessage(content="old"), AIMessage(content="prev")])
    history = [
        HumanMessage(content="ignored prior"),
        AIMessage(content="ignored prior reply"),
        HumanMessage(content="back to kashmir"),
        AIMessage(content="resumed"),
    ]
    out = chat_store.persist_turn("mexico_x_y", "kashmir_p_q", history)
    assert out == "kashmir_p_q"
    assert chat_store.transcript("kashmir_p_q") == [
        {"role": "user", "text": "old"},
        {"role": "assistant", "text": "prev"},
        {"role": "user", "text": "back to kashmir"},
        {"role": "assistant", "text": "resumed"},
    ]


def test_module_imports_clean():
    importlib.reload(chat_carryover)
