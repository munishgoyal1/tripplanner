"""Canonical versioned persistence for active and saved trips."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from tripplanner import debug_store, storage_cosmos
from tripplanner.json_store import atomic_write_json
from tripplanner.trip_models import TripPatch, TripPlan, UpdateOutcome

_USERS_CONTAINER = "users"
_TRIPS_CONTAINER = "trips"
_ACTIVE_DOC_ID = "active_trip"
_MAX_CONFLICT_RETRIES = 3

_LOCKS_GUARD = RLock()
_LOCKS: dict[tuple[str, str], RLock] = {}


class TripConflictError(RuntimeError):
    """The canonical trip kept changing while a mutation was retried."""


@dataclass(frozen=True)
class TripPaths:
    active: Path
    history: Path


def _lock_for(user_id: str, trip_id: str) -> RLock:
    key = (user_id, trip_id)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, RLock())


class TripRepository:
    """Persist one canonical trip plus a lightweight active-trip pointer."""

    def __init__(self, user_id: str, paths: TripPaths) -> None:
        self.user_id = user_id
        self.paths = paths

    def load_active(self) -> dict[str, Any] | None:
        pointer = self._read_active()
        if not pointer:
            return None
        if not self._is_pointer(pointer):
            return pointer
        return self.load(str(pointer["trip_id"]))

    def load(self, trip_id: str) -> dict[str, Any] | None:
        if not trip_id:
            return None
        if storage_cosmos.is_enabled():
            return storage_cosmos.read_doc(_TRIPS_CONTAINER, self.user_id, trip_id)
        path = self.paths.history / f"{trip_id}.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def set_active(self, plan: dict[str, Any]) -> None:
        trip_id = str(plan.get("trip_id") or "")
        if not trip_id:
            raise ValueError("An active trip requires trip_id")
        self._write_active_pointer(trip_id, int(plan.get("revision") or 0))

    def save(self, plan: dict[str, Any], *, activate: bool = True) -> UpdateOutcome:
        trip_id = str(plan.get("trip_id") or "")
        if not trip_id:
            raise ValueError("A saved trip requires trip_id")

        incoming = deepcopy(plan)
        expected_revision = int(incoming.get("revision") or 0)

        def replace(current: dict[str, Any] | None) -> dict[str, Any]:
            current_revision = int((current or {}).get("revision") or 0)
            if current_revision != expected_revision:
                raise TripConflictError(
                    f"Trip {trip_id!r} changed from revision {expected_revision} "
                    f"to {current_revision}"
                )
            return deepcopy(incoming)

        return self.mutate(trip_id, replace, activate=activate)

    def mutate(
        self,
        trip_id: str,
        mutation: Callable[[dict[str, Any] | None], dict[str, Any]],
        *,
        activate: bool = True,
    ) -> UpdateOutcome:
        if not trip_id:
            raise ValueError("A trip mutation requires trip_id")
        if storage_cosmos.is_enabled():
            return self._mutate_cosmos(trip_id, mutation, activate=activate)
        return self._mutate_local(trip_id, mutation, activate=activate)

    def patch(
        self, trip_id: str, patch: TripPatch, *, activate: bool = True
    ) -> UpdateOutcome:
        changes = patch.changes()
        changes.pop("trip_id", None)
        return self.mutate(
            trip_id,
            lambda current: {**(current or {}), **deepcopy(changes)},
            activate=activate,
        )

    def delete_active(self) -> None:
        if storage_cosmos.is_enabled():
            storage_cosmos.delete_doc(_USERS_CONTAINER, self.user_id, _ACTIVE_DOC_ID)
            return
        self.paths.active.unlink(missing_ok=True)

    def _mutate_cosmos(
        self,
        trip_id: str,
        mutation: Callable[[dict[str, Any] | None], dict[str, Any]],
        *,
        activate: bool,
    ) -> UpdateOutcome:
        for _attempt in range(_MAX_CONFLICT_RETRIES):
            current = storage_cosmos.read_doc_versioned(
                _TRIPS_CONTAINER, self.user_id, trip_id
            )
            body = self._next_body(
                trip_id,
                current.body if current is not None else None,
                mutation,
            )
            try:
                if current is None:
                    storage_cosmos.create_doc_if_absent(
                        _TRIPS_CONTAINER, self.user_id, trip_id, body
                    )
                else:
                    storage_cosmos.replace_doc_if_version(
                        _TRIPS_CONTAINER,
                        self.user_id,
                        trip_id,
                        body,
                        current.version,
                    )
            except storage_cosmos.WriteConflictError:
                continue
            if activate:
                self._write_active_pointer(trip_id, int(body["revision"]))
            debug_store.record_trip(body, self.user_id)
            return self._outcome(body)
        raise TripConflictError(f"Trip {trip_id!r} kept changing")

    def _mutate_local(
        self,
        trip_id: str,
        mutation: Callable[[dict[str, Any] | None], dict[str, Any]],
        *,
        activate: bool,
    ) -> UpdateOutcome:
        with _lock_for(self.user_id, trip_id):
            body = self._next_body(trip_id, self.load(trip_id), mutation)
            self.paths.history.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.paths.history / f"{trip_id}.json", body, indent=2)
            if activate:
                self._write_active_pointer(trip_id, int(body["revision"]))
            debug_store.record_trip(body, self.user_id)
            return self._outcome(body)

    @staticmethod
    def _next_body(
        trip_id: str,
        current: dict[str, Any] | None,
        mutation: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]:
        candidate = deepcopy(mutation(deepcopy(current)))
        if not isinstance(candidate, dict):
            raise TypeError("Trip mutation must return a dictionary")
        candidate["trip_id"] = trip_id
        candidate["revision"] = int((current or {}).get("revision") or 0) + 1
        return TripPlan.model_validate(candidate).model_dump(
            mode="python", exclude_unset=True
        )

    def _read_active(self) -> dict[str, Any] | None:
        if storage_cosmos.is_enabled():
            return storage_cosmos.read_doc(
                _USERS_CONTAINER, self.user_id, _ACTIVE_DOC_ID
            )
        if not self.paths.active.exists():
            return None
        try:
            value = json.loads(self.paths.active.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _write_active_pointer(self, trip_id: str, revision: int) -> None:
        pointer = {"trip_id": trip_id, "revision": revision}
        if storage_cosmos.is_enabled():
            storage_cosmos.upsert_doc(
                _USERS_CONTAINER, self.user_id, _ACTIVE_DOC_ID, pointer
            )
            return
        atomic_write_json(self.paths.active, pointer, indent=2)

    @staticmethod
    def _is_pointer(value: dict[str, Any]) -> bool:
        return bool(value.get("trip_id")) and set(value) <= {"trip_id", "revision"}

    @staticmethod
    def _outcome(body: dict[str, Any]) -> UpdateOutcome:
        plan = TripPlan.model_validate(body)
        return UpdateOutcome(ok=True, plan=plan, revision=plan.revision)
