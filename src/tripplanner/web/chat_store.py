"""Per-trip chat transcript persistence (frontend-agnostic).

The visible conversation + itinerary summary must survive a browser refresh and
follow saved-trip switches (Mumbai chat vs. Vietnam chat). We persist the clean
Human/AI text turns — the same list the API keeps as the agent's LLM context —
so a reload yields valid context and an identical transcript.

Two backends, auto-selected (mirrors ``trip_planner``):
- **Cosmos DB** ``users`` container, doc id ``chat_<trip_id>`` (hosted mode)
- **Local JSON** ``~/.tripplanner/chats/<trip_id>.json`` otherwise (per-user
  subdir for non-``local`` identities)

A conversation that happens before any trip exists lives in the ``_general``
bucket; once a trip is created it is migrated into that trip's bucket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from tripplanner import storage_cosmos
from tripplanner.user_context import get_user_id

_CHATS_DIR = Path.home() / ".tripplanner" / "chats"
_COSMOS_USERS_CONTAINER = "users"
_GENERAL = "_general"
_MAX_TURNS = 80  # keep the persisted transcript bounded


def _doc_id(trip_id: str | None) -> str:
    return f"chat_{trip_id or _GENERAL}"


def _resolve_dir() -> Path:
    uid = get_user_id()
    if uid == "local":
        return _CHATS_DIR
    return Path.home() / ".tripplanner" / "users" / uid / "chats"


def _serialize(messages: list[BaseMessage]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for m in messages:
        mtype = getattr(m, "type", "")
        role = "user" if mtype == "human" else "assistant" if mtype == "ai" else None
        if role is None:
            continue
        text = m.content if isinstance(m.content, str) else str(m.content)
        if not text.strip():
            continue
        rows.append({"role": role, "text": text})
    return rows[-_MAX_TURNS:]


def _deserialize(rows: list[dict[str, Any]]) -> list[BaseMessage]:
    msgs: list[BaseMessage] = []
    for r in rows:
        text = str(r.get("text") or "")
        if not text.strip():
            continue
        if r.get("role") == "user":
            msgs.append(HumanMessage(content=text))
        else:
            msgs.append(AIMessage(content=text))
    return msgs


def _read_rows(trip_id: str | None) -> list[dict[str, Any]]:
    if storage_cosmos.is_enabled():
        doc = storage_cosmos.read_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _doc_id(trip_id)
        )
        return list((doc or {}).get("messages") or [])
    path = _resolve_dir() / f"{_doc_id(trip_id)}.json"
    if path.exists():
        try:
            return list(json.loads(path.read_text(encoding="utf-8")).get("messages") or [])
        except (json.JSONDecodeError, OSError):
            return []
    return []


def load(trip_id: str | None) -> list[BaseMessage]:
    """LangChain message history for a trip's conversation (for the agent)."""
    return _deserialize(_read_rows(trip_id))


def transcript(trip_id: str | None) -> list[dict[str, str]]:
    """The display transcript ([{role, text}]) for the SPA to re-render."""
    return [
        {"role": str(r.get("role") or "assistant"), "text": str(r.get("text") or "")}
        for r in _read_rows(trip_id)
        if str(r.get("text") or "").strip()
    ]


def save(trip_id: str | None, messages: list[BaseMessage]) -> None:
    rows = _serialize(messages)
    body = {"messages": rows}
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _doc_id(trip_id), body
        )
        return
    d = _resolve_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{_doc_id(trip_id)}.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clear(trip_id: str | None) -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _doc_id(trip_id)
        )
        return
    (_resolve_dir() / f"{_doc_id(trip_id)}.json").unlink(missing_ok=True)


def clear_all() -> int:
    """Delete every persisted chat transcript for the current user."""
    if storage_cosmos.is_enabled():
        return storage_cosmos.delete_docs(
            _COSMOS_USERS_CONTAINER,
            get_user_id(),
            id_prefix="chat_",
        )

    deleted = 0
    d = _resolve_dir()
    if not d.exists():
        return 0
    for path in d.glob("chat_*.json"):
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
    return deleted

