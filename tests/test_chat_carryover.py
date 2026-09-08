"""Tests for mid-chat destination switch: carryover distill + chat bucketing."""

from __future__ import annotations

import copy
import importlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tripplanner import storage_cosmos
from tripplanner.web import chat_carryover, chat_store


def _spoken(rows: list[dict]) -> list[dict]:
    """What was said, without the display timing stored beside it."""
    return [{"role": row["role"], "text": row["text"]} for row in rows]



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
    turn = [HumanMessage(content="hi"), AIMessage(content="hello")]
    out = chat_store.persist_turn("mexico_x_y", "mexico_x_y", [], turn)
    assert out == "mexico_x_y"
    assert _spoken(chat_store.transcript("mexico_x_y")) == [
        {"role": "user", "text": "hi"},
        {"role": "assistant", "text": "hello"},
    ]


def test_persist_turn_first_trip_migrates_general(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    turn = [HumanMessage(content="plan goa"), AIMessage(content="sure!")]
    out = chat_store.persist_turn(None, "goa_a_b", [], turn)
    assert out == "goa_a_b"
    assert len(chat_store.transcript("goa_a_b")) == 2
    assert chat_store.transcript(None) == []


def test_first_trip_retries_source_copy_when_general_changes_before_delete(monkeypatch):
    initial_rows = [
        {"role": "user", "text": "plan goa"},
        {"role": "assistant", "text": "sure!"},
    ]
    extended_rows = initial_rows + [{"role": "user", "text": "concurrent turn"}]
    reads = iter(
        [
            storage_cosmos.VersionedDocument(
                body={"messages": initial_rows}, version='"v1"'
            ),
            storage_cosmos.VersionedDocument(
                body={"messages": extended_rows}, version='"v2"'
            ),
        ]
    )
    migrated: list[tuple[str, dict]] = []
    appended: list[tuple[str | None, list[dict], list[dict]]] = []
    deleted: list[str] = []
    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(chat_store.storage_cosmos, "read_doc_versioned", lambda *_: next(reads))
    monkeypatch.setattr(
        chat_store,
        "_merge_migrated_document",
        lambda tid, body: migrated.append((tid, body)),
    )

    def delete_if_version(_container, _user, _doc_id, version):
        deleted.append(version)
        if version == '"v1"':
            raise storage_cosmos.WriteConflictError("changed")

    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "delete_doc_if_version",
        delete_if_version,
    )
    monkeypatch.setattr(
        chat_store,
        "_append_rows",
        lambda tid, base, suffix, **_kwargs: appended.append((tid, base, suffix)),
    )

    turn = [HumanMessage(content="plan goa"), AIMessage(content="sure!")]
    out = chat_store.persist_turn(None, "goa_a_b", [], turn)

    assert out == "goa_a_b"
    assert migrated == [
        ("goa_a_b", {"messages": initial_rows}),
        ("goa_a_b", {"messages": extended_rows}),
    ]
    assert appended == [
        (
            "goa_a_b",
            [],
            [
                {"role": "user", "text": "plan goa"},
                {"role": "assistant", "text": "sure!"},
            ],
        ),
        (
            "goa_a_b",
            [],
            [
                {"role": "user", "text": "plan goa"},
                {"role": "assistant", "text": "sure!"},
            ],
        )
    ]
    assert deleted == ['"v1"', '"v2"']


def test_first_trip_append_failure_keeps_general_source(monkeypatch):
    source = storage_cosmos.VersionedDocument(
        body={"messages": [{"role": "user", "text": "plan goa"}]},
        version='"v1"',
    )
    deleted: list[str] = []
    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "read_doc_versioned",
        lambda *_: source,
    )
    monkeypatch.setattr(chat_store, "_merge_migrated_document", lambda *_: None)

    def fail_append(*_args, **_kwargs):
        raise storage_cosmos.WriteConflictError("destination changed")

    monkeypatch.setattr(chat_store, "_append_rows", fail_append)
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "delete_doc_if_version",
        lambda *_args: deleted.append("deleted"),
    )

    with pytest.raises(storage_cosmos.WriteConflictError):
        chat_store.persist_turn(
            None,
            "goa_a_b",
            [],
            [HumanMessage(content="plan goa"), AIMessage(content="sure!")],
        )

    assert deleted == []


def test_switch_carryover_replays_after_cosmos_create_conflict(monkeypatch):
    concurrent = [
        {"role": "user", "text": "concurrent turn"},
        {"role": "assistant", "text": "concurrent reply"},
    ]
    state: dict[str, object] = {"body": None, "version": 0}

    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "read_doc",
        lambda *_args: copy.deepcopy(state["body"]),
    )

    def read_versioned(*_args):
        if state["body"] is None:
            return None
        return storage_cosmos.VersionedDocument(
            copy.deepcopy(state["body"]), str(state["version"])
        )

    def create(*_args):
        state["body"] = {"messages": concurrent}
        state["version"] = 1
        raise storage_cosmos.WriteConflictError("created")

    def replace(_container, _user, _doc_id, body, _version):
        state["body"] = copy.deepcopy(body)

    monkeypatch.setattr(chat_store.storage_cosmos, "read_doc_versioned", read_versioned)
    monkeypatch.setattr(chat_store.storage_cosmos, "create_doc_if_absent", create)
    monkeypatch.setattr(chat_store.storage_cosmos, "replace_doc_if_version", replace)

    chat_store.persist_turn(
        "mexico-trip",
        "goa-trip",
        [],
        [HumanMessage(content="switch to goa"), AIMessage(content="Goa is ready")],
        carryover_text="Carrying over: 2 adults.",
    )

    assert [row["text"] for row in state["body"]["messages"]] == [  # type: ignore[index]
        "concurrent turn",
        "concurrent reply",
        "Carrying over: 2 adults.",
        "switch to goa",
        "Goa is ready",
    ]


def test_retry_reconciles_general_after_first_trip_append_failure(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    chat_store.persist_turn(
        None,
        None,
        [],
        [HumanMessage(content="hello"), AIMessage(content="Hi")],
    )
    original_append = chat_store._append_rows
    monkeypatch.setattr(
        chat_store,
        "_append_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            storage_cosmos.WriteConflictError("destination changed")
        ),
    )

    with pytest.raises(storage_cosmos.WriteConflictError):
        chat_store.persist_turn(
            None,
            "goa_a_b",
            chat_store.load(None),
            [HumanMessage(content="plan goa"), AIMessage(content="Done")],
            request_id="create-goa",
        )

    monkeypatch.setattr(chat_store, "_append_rows", original_append)
    chat_store.reconcile_general("goa_a_b")
    retry_base = chat_store.load_for_request("goa_a_b", "create-goa")
    chat_store.persist_turn(
        "goa_a_b",
        "goa_a_b",
        retry_base,
        [HumanMessage(content="plan goa"), AIMessage(content="Done")],
        request_id="create-goa",
    )

    assert chat_store.transcript(None) == []
    assert [row["text"] for row in chat_store.transcript("goa_a_b")] == [
        "hello",
        "Hi",
        "plan goa",
        "Done",
    ]


def test_migrated_body_keeps_unmatched_prefix_around_shared_rows():
    shared = {"role": "assistant", "text": "shared"}
    current = {"messages": [shared, {"role": "user", "text": "destination"}]}
    source = {
        "messages": [
            {"role": "user", "text": "general prefix"},
            shared,
            {"role": "assistant", "text": "general suffix"},
        ]
    }

    merged = chat_store._merge_migrated_body(current, source)

    assert merged is not None
    assert [row["text"] for row in merged["messages"]] == [
        "general prefix",
        "shared",
        "destination",
        "general suffix",
    ]


def test_first_trip_raises_when_source_delete_conflicts_are_exhausted(monkeypatch):
    versioned = storage_cosmos.VersionedDocument(
        body={"messages": [{"role": "user", "text": "plan goa"}]},
        version='"changing"',
    )
    delete_calls = 0
    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "read_doc_versioned",
        lambda *_: versioned,
    )
    monkeypatch.setattr(chat_store, "save", lambda *_: None)
    monkeypatch.setattr(chat_store, "_append_rows", lambda *_, **_kwargs: None)

    def conflict(*_args):
        nonlocal delete_calls
        delete_calls += 1
        raise storage_cosmos.WriteConflictError("changed")

    monkeypatch.setattr(chat_store.storage_cosmos, "delete_doc_if_version", conflict)

    with pytest.raises(storage_cosmos.WriteConflictError):
        chat_store.persist_turn(
            None,
            "goa_a_b",
            [],
            [HumanMessage(content="plan goa"), AIMessage(content="sure!")],
        )

    assert delete_calls == chat_store._MAX_WRITE_ATTEMPTS


def test_persist_turn_switch_keeps_prev_and_seeds_new(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    # Mexico bucket already has prior turns.
    mexico = [
        HumanMessage(content="plan mexico, 2 adults"),
        AIMessage(content="Mexico draft ready"),
    ]
    chat_store.save("mexico_x_y", mexico)

    # The switch turn: full history is mexico + the new switch turn.
    turn = [
        HumanMessage(content="actually plan kashmir"),
        AIMessage(content="Switching to Kashmir!"),
    ]
    out = chat_store.persist_turn(
        "mexico_x_y",
        "kashmir_p_q",
        mexico,
        turn,
        carryover_text="Carrying over: 2 adults.",
    )
    assert out == "kashmir_p_q"

    # Mexico bucket untouched.
    assert _spoken(chat_store.transcript("mexico_x_y")) == [
        {"role": "user", "text": "plan mexico, 2 adults"},
        {"role": "assistant", "text": "Mexico draft ready"},
    ]
    # Kashmir bucket: carryover note + the switch turn only (no Mexico verbatim).
    kashmir = chat_store.transcript("kashmir_p_q")
    assert _spoken(kashmir) == [
        {"role": "assistant", "text": "Carrying over: 2 adults."},
        {"role": "user", "text": "actually plan kashmir"},
        {"role": "assistant", "text": "Switching to Kashmir!"},
    ]


def test_a_stored_turn_keeps_its_time_and_duration(monkeypatch, tmp_path):
    """Timing lived only in browser storage, so every turn but the newest lost
    its clock on reload and on any other device."""
    _use_temp_chats(monkeypatch, tmp_path)
    first = [HumanMessage(content="plan goa"), AIMessage(content="Here is Goa")]
    chat_store.persist_turn("goa_a_b", "goa_a_b", [], first, turn_seconds=26)
    chat_store.persist_turn(
        "goa_a_b",
        "goa_a_b",
        first,
        [HumanMessage(content="add a beach"), AIMessage(content="Added")],
        turn_seconds=8,
    )

    rows = chat_store.transcript("goa_a_b")
    assert [row["text"] for row in rows] == ["plan goa", "Here is Goa", "add a beach", "Added"]
    assert all(isinstance(row["ts"], int) for row in rows)
    # The duration belongs to the reply, not to the question that prompted it.
    assert [row.get("seconds") for row in rows] == [None, 26, None, 8]
    # The agent's context is still only what was said.
    assert [message.content for message in chat_store.load("goa_a_b")] == [
        "plan goa",
        "Here is Goa",
        "add a beach",
        "Added",
    ]


def test_timing_never_makes_one_turn_look_like_two(monkeypatch, tmp_path):
    """Merge and overlap detection compare rows, so display metadata must not
    take part in deciding whether a turn is already stored."""
    _use_temp_chats(monkeypatch, tmp_path)
    turn = [HumanMessage(content="plan goa"), AIMessage(content="Here is Goa")]
    chat_store.persist_turn("goa_a_b", "goa_a_b", [], turn, turn_seconds=26)

    chat_store.save("goa_a_b", turn)

    assert [row["text"] for row in chat_store.transcript("goa_a_b")] == [
        "plan goa",
        "Here is Goa",
    ]


def test_persist_turn_switch_carries_the_request_that_started_the_trip(monkeypatch, tmp_path):
    """The trip is created a turn after it is asked for, so without this the new
    chat opens on the kickoff answer and never shows the request itself."""
    _use_temp_chats(monkeypatch, tmp_path)
    paris = [
        HumanMessage(content="plan paris for 4 days"),
        AIMessage(content="Paris draft ready"),
        HumanMessage(content="Plan a trip to Rajasthan for 7 days"),
        AIMessage(content="A few quick details first"),
    ]
    chat_store.save("paris_x_y", paris)

    turn = [
        HumanMessage(content="2 adults, mid budget"),
        AIMessage(content="Rajasthan itinerary ready"),
    ]
    chat_store.persist_turn(
        "paris_x_y",
        "rajasthan_p_q",
        paris,
        turn,
        origin_prompt=chat_store.originating_request(paris, "Rajasthan"),
    )

    assert _spoken(chat_store.transcript("rajasthan_p_q")) == [
        {"role": "user", "text": "Plan a trip to Rajasthan for 7 days"},
        {"role": "user", "text": "2 adults, mid budget"},
        {"role": "assistant", "text": "Rajasthan itinerary ready"},
    ]


def test_originating_request_ignores_an_unrelated_previous_chat(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    history = [
        HumanMessage(content="plan paris for 4 days"),
        AIMessage(content="Paris draft ready"),
    ]
    assert chat_store.originating_request(history, "Rajasthan") == ""


def test_persist_turn_switch_to_existing_appends(monkeypatch, tmp_path):
    _use_temp_chats(monkeypatch, tmp_path)
    chat_store.save("kashmir_p_q", [HumanMessage(content="old"), AIMessage(content="prev")])
    base = [
        HumanMessage(content="ignored prior"),
        AIMessage(content="ignored prior reply"),
    ]
    turn = [
        HumanMessage(content="back to kashmir"),
        AIMessage(content="resumed"),
    ]
    out = chat_store.persist_turn("mexico_x_y", "kashmir_p_q", base, turn)
    assert out == "kashmir_p_q"
    assert _spoken(chat_store.transcript("kashmir_p_q")) == [
        {"role": "user", "text": "old"},
        {"role": "assistant", "text": "prev"},
        {"role": "user", "text": "back to kashmir"},
        {"role": "assistant", "text": "resumed"},
    ]


def test_module_imports_clean():
    importlib.reload(chat_carryover)
