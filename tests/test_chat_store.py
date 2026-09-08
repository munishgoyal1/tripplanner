"""Tests for the per-trip chat transcript store (web/chat_store.py)."""

from __future__ import annotations

import copy
import os
import shutil
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tripplanner import storage_cosmos
from tripplanner.user_context import get_user_id, set_user_id
from tripplanner.web import chat_store

# Parallel sandboxes run this suite at the same time against one home
# directory, so a shared name means one run's teardown deletes another
# run's fixture mid-test. The pid keeps them disjoint.
_TEST_CHATS = Path.home() / f".tripplanner_chat_test-{os.getpid()}" / "chats"


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


def _spoken(rows: list[dict]) -> list[dict]:
    """What was said, without the display timing stored beside it."""
    return [{"role": row["role"], "text": row["text"]} for row in rows]


def test_transcript_shape() -> None:
    chat_store.save("goa_2026-01-10_2026-01-15", _convo())
    rows = chat_store.transcript("goa_2026-01-10_2026-01-15")
    assert _spoken(rows) == [
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


def test_save_extends_shared_history() -> None:
    chat_store.save("t", [HumanMessage(content="first")])
    chat_store.save("t", [HumanMessage(content="first"), AIMessage(content="second")])
    rows = chat_store.transcript("t")
    assert [r["text"] for r in rows] == ["first", "second"]


def test_stale_snapshot_cannot_truncate_newer_history() -> None:
    complete = [
        HumanMessage(content="first"),
        AIMessage(content="second"),
        HumanMessage(content="third"),
        AIMessage(content="fourth"),
    ]
    chat_store.save("t", complete)
    chat_store.save("t", complete[:2])

    assert [row["text"] for row in chat_store.transcript("t")] == [
        "first",
        "second",
        "third",
        "fourth",
    ]


def test_divergent_snapshots_preserve_both_suffixes_and_exact_replay_is_idempotent() -> None:
    base = [HumanMessage(content="first"), AIMessage(content="second")]
    branch_a = base + [HumanMessage(content="A"), AIMessage(content="A reply")]
    branch_b = base + [HumanMessage(content="B"), AIMessage(content="B reply")]

    chat_store.save("t", branch_a)
    chat_store.save("t", branch_b)
    chat_store.save("t", branch_b)

    assert [row["text"] for row in chat_store.transcript("t")] == [
        "first",
        "second",
        "A",
        "A reply",
        "B",
        "B reply",
    ]


def test_repeated_identical_turns_with_different_bases_are_preserved() -> None:
    first = [HumanMessage(content="again"), AIMessage(content="ok")]
    second = first + [HumanMessage(content="again"), AIMessage(content="ok")]

    chat_store.save("t", first)
    chat_store.save("t", second)

    assert [row["text"] for row in chat_store.transcript("t")] == [
        "again",
        "ok",
        "again",
        "ok",
    ]


def test_request_id_is_idempotent_when_retry_loads_a_new_base() -> None:
    turn = [HumanMessage(content="again"), AIMessage(content="ok")]
    chat_store.persist_turn("t", "t", [], turn, request_id="request-123")
    changed_base = chat_store.load("t")

    chat_store.persist_turn(
        "t",
        "t",
        changed_base,
        turn,
        request_id="request-123",
    )

    assert [row["text"] for row in chat_store.transcript("t")] == ["again", "ok"]


def test_completed_retry_replaces_interrupted_attempt() -> None:
    interrupted = [
        HumanMessage(content="plan goa"),
        AIMessage(content="(interrupted)"),
    ]
    completed = [HumanMessage(content="plan goa"), AIMessage(content="Goa is ready")]

    chat_store.persist_turn(
        "t",
        "t",
        [],
        interrupted,
        request_id="request-123",
        completed=False,
    )
    retry_base = chat_store.load_for_request("t", "request-123")
    chat_store.persist_turn(
        "t",
        "t",
        retry_base,
        completed,
        request_id="request-123",
    )

    assert retry_base == []
    assert [row["text"] for row in chat_store.transcript("t")] == [
        "plan goa",
        "Goa is ready",
    ]
    assert chat_store.completed_operation("t", "request-123") == {
        "reply": "Goa is ready",
        "agent": "trip",
        "trip_id": "t",
        "message": "plan goa",
    }


def test_completed_request_ledger_survives_first_trip_migration() -> None:
    first_turn = [HumanMessage(content="hello"), AIMessage(content="Hi")]
    chat_store.persist_turn(
        None,
        None,
        [],
        first_turn,
        request_id="pre-trip-request",
    )
    base = chat_store.load(None)

    chat_store.persist_turn(
        None,
        "goa-trip",
        base,
        [HumanMessage(content="plan goa"), AIMessage(content="Done")],
        request_id="create-trip-request",
    )

    assert chat_store.completed_operation("goa-trip", "pre-trip-request") == {
        "reply": "Hi",
        "agent": "trip",
        "trip_id": "goa-trip",
        "message": "hello",
    }
    assert chat_store.transcript(None) == []


def test_completed_request_replays_after_active_trip_switch() -> None:
    chat_store.persist_turn(
        "goa-trip",
        "goa-trip",
        [],
        [HumanMessage(content="plan goa"), AIMessage(content="Goa is ready")],
        request_id="switch-safe-request",
    )
    chat_store.save(
        "paris-trip",
        [HumanMessage(content="plan paris"), AIMessage(content="Paris is ready")],
    )

    assert chat_store.completed_request("switch-safe-request") == {
        "reply": "Goa is ready",
        "agent": "trip",
        "trip_id": "goa-trip",
        "message": "plan goa",
    }


def test_completed_request_is_isolated_by_principal(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_store,
        "_resolve_dir",
        lambda: _TEST_CHATS / get_user_id(),
    )
    try:
        set_user_id("alice")
        chat_store.persist_turn(
            "goa-trip",
            "goa-trip",
            [],
            [HumanMessage(content="plan goa"), AIMessage(content="Goa is ready")],
            request_id="shared-request-id",
        )

        set_user_id("bob")
        assert chat_store.completed_request("shared-request-id") is None

        set_user_id("alice")
        assert chat_store.completed_request("shared-request-id") is not None
    finally:
        set_user_id("local")


def test_adopt_state_merges_all_chat_metadata_without_replacing_account_chat(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        chat_store,
        "_resolve_dir",
        lambda: _TEST_CHATS / get_user_id(),
    )
    try:
        set_user_id("guest")
        chat_store.persist_turn(
            None,
            None,
            [],
            [HumanMessage(content="hello"), AIMessage(content="Hi")],
            request_id="guest-general",
        )
        chat_store.persist_turn(
            "goa-trip",
            "goa-trip",
            [],
            [HumanMessage(content="plan goa"), AIMessage(content="Goa is ready")],
            request_id="guest-completed",
        )
        chat_store.persist_turn(
            "goa-trip",
            "goa-trip",
            chat_store.load("goa-trip"),
            [HumanMessage(content="change hotel"), AIMessage(content="(interrupted)")],
            request_id="guest-interrupted",
            completed=False,
        )
        state = chat_store.export_state(["goa-trip"])

        set_user_id("account")
        chat_store.save(
            "goa-trip",
            [HumanMessage(content="account turn"), AIMessage(content="Account reply")],
        )
        assert chat_store.adopt_state(state) is True

        assert [row["text"] for row in chat_store.transcript(None)] == ["hello", "Hi"]
        assert [row["text"] for row in chat_store.transcript("goa-trip")] == [
            "account turn",
            "Account reply",
            "plan goa",
            "Goa is ready",
            "change hotel",
            "(interrupted)",
        ]
        assert chat_store.load_for_request("goa-trip", "guest-interrupted") == [
            HumanMessage(content="account turn"),
            AIMessage(content="Account reply"),
            HumanMessage(content="plan goa"),
            AIMessage(content="Goa is ready"),
        ]
        assert chat_store.completed_request("guest-completed") == {
            "reply": "Goa is ready",
            "agent": "trip",
            "trip_id": "goa-trip",
            "message": "plan goa",
        }
    finally:
        set_user_id("local")


def test_clearing_trip_removes_its_completed_requests() -> None:
    chat_store.persist_turn(
        "goa-trip",
        "goa-trip",
        [],
        [HumanMessage(content="plan goa"), AIMessage(content="Goa is ready")],
        request_id="deleted-trip-request",
    )

    chat_store.clear("goa-trip")

    assert chat_store.completed_request("deleted-trip-request") is None


def test_document_mutation_replays_intent_after_cosmos_conflict(monkeypatch) -> None:
    base = [{"role": "user", "text": "first"}]
    concurrent = {"role": "assistant", "text": "concurrent"}
    incoming = {"role": "user", "text": "second"}
    state = {"body": {"messages": base}, "version": 1}
    observed_bodies: list[dict] = []

    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "read_doc_versioned",
        lambda *_args: storage_cosmos.VersionedDocument(
            copy.deepcopy(state["body"]), str(state["version"])
        ),
    )

    def replace(_container, _user, _doc_id, body, _version):
        if len(observed_bodies) == 1:
            state["body"] = {"messages": base + [concurrent]}
            state["version"] = 2
            raise storage_cosmos.WriteConflictError("changed")
        state["body"] = copy.deepcopy(body)

    monkeypatch.setattr(chat_store.storage_cosmos, "replace_doc_if_version", replace)

    def append_incoming(body):
        observed_bodies.append(copy.deepcopy(body))
        return {**body, "messages": list(body.get("messages") or []) + [incoming]}

    chat_store._mutate_document("chat_t", append_incoming)

    assert observed_bodies == [
        {"messages": base},
        {"messages": base + [concurrent]},
    ]
    assert state["body"] == {"messages": base + [concurrent, incoming]}


def test_migration_merge_replays_against_cosmos_conflict_winner(monkeypatch) -> None:
    destination = {"role": "assistant", "text": "account reply"}
    concurrent = {"role": "user", "text": "concurrent destination turn"}
    source = {"messages": [{"role": "user", "text": "guest turn"}]}
    state = {"body": {"messages": [destination]}, "version": 1}
    replace_calls = 0

    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "read_doc_versioned",
        lambda *_args: storage_cosmos.VersionedDocument(
            copy.deepcopy(state["body"]), str(state["version"])
        ),
    )

    def replace(_container, _user, _doc_id, body, _version):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 1:
            state["body"] = {"messages": [destination, concurrent]}
            state["version"] = 2
            raise storage_cosmos.WriteConflictError("changed")
        state["body"] = copy.deepcopy(body)

    monkeypatch.setattr(chat_store.storage_cosmos, "replace_doc_if_version", replace)

    chat_store._merge_migrated_document(
        "goa-trip",
        source,
        associate_operations=False,
    )

    assert replace_calls == 2
    assert state["body"]["messages"] == [destination, concurrent, *source["messages"]]


def test_cosmos_replace_conflict_rereads_and_preserves_both_suffixes(monkeypatch) -> None:
    base = [
        {"role": "user", "text": "first"},
        {"role": "assistant", "text": "second"},
    ]
    concurrent = [
        {"role": "user", "text": "A"},
        {"role": "assistant", "text": "A reply"},
    ]
    incoming = [
        HumanMessage(content="first"),
        AIMessage(content="second"),
        HumanMessage(content="B"),
        AIMessage(content="B reply"),
    ]
    state = {"body": {"messages": base}, "version": 1}
    replace_calls = 0

    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "read_doc",
        lambda *_args: copy.deepcopy(state["body"]),
    )
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "read_doc_versioned",
        lambda *_args: storage_cosmos.VersionedDocument(
            copy.deepcopy(state["body"]), str(state["version"])
        ),
    )

    def replace(_container, _user, _doc_id, body, _version):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 1:
            state["body"] = {"messages": base + concurrent}
            state["version"] = 2
            raise storage_cosmos.WriteConflictError("changed")
        state["body"] = copy.deepcopy(body)
        state["version"] += 1

    monkeypatch.setattr(chat_store.storage_cosmos, "replace_doc_if_version", replace)

    chat_store.save("t", incoming)

    assert replace_calls == 2
    assert [row["text"] for row in state["body"]["messages"]] == [
        "first",
        "second",
        "A",
        "A reply",
        "B",
        "B reply",
    ]


def test_cosmos_create_conflict_rereads_and_merges_winning_document(monkeypatch) -> None:
    winner = [
        {"role": "user", "text": "A"},
        {"role": "assistant", "text": "A reply"},
    ]
    incoming = [HumanMessage(content="B"), AIMessage(content="B reply")]
    state: dict[str, object] = {"body": None, "version": 0}

    monkeypatch.setattr(chat_store.storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        chat_store.storage_cosmos,
        "read_doc",
        lambda *_args: copy.deepcopy(state["body"]),
    )

    def read_versioned(*_args):
        body = state["body"]
        if body is None:
            return None
        return storage_cosmos.VersionedDocument(
            copy.deepcopy(body), str(state["version"])
        )

    def create(*_args):
        state["body"] = {"messages": winner}
        state["version"] = 1
        raise storage_cosmos.WriteConflictError("created")

    def replace(_container, _user, _doc_id, body, _version):
        state["body"] = copy.deepcopy(body)
        state["version"] = int(state["version"]) + 1

    monkeypatch.setattr(chat_store.storage_cosmos, "read_doc_versioned", read_versioned)
    monkeypatch.setattr(chat_store.storage_cosmos, "create_doc_if_absent", create)
    monkeypatch.setattr(chat_store.storage_cosmos, "replace_doc_if_version", replace)

    chat_store.save("t", incoming)

    assert [row["text"] for row in state["body"]["messages"]] == [  # type: ignore[index]
        "A",
        "A reply",
        "B",
        "B reply",
    ]


def test_exact_turn_append_preserves_concurrent_suffix_at_retention_limit() -> None:
    base = [
        HumanMessage(content=f"user {index}")
        if index % 2 == 0
        else AIMessage(content=f"assistant {index}")
        for index in range(chat_store._MAX_TURNS)
    ]
    chat_store.save("t", base)
    chat_store.persist_turn(
        "t",
        "t",
        base,
        [HumanMessage(content="concurrent"), AIMessage(content="first reply")],
    )
    chat_store.persist_turn(
        "t",
        "t",
        base,
        [HumanMessage(content="stale writer"), AIMessage(content="second reply")],
    )

    texts = [row["text"] for row in chat_store.transcript("t")]
    assert len(texts) == chat_store._MAX_TURNS
    assert texts[-4:] == ["concurrent", "first reply", "stale writer", "second reply"]

