"""Small in-process admission limits for expensive chat turns."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterable
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request

_WINDOW_SECONDS = 60.0


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


@dataclass(frozen=True)
class ChatPermit:
    user_id: str


@dataclass(frozen=True)
class ReplayAccessPermit:
    user_id: str


class ChatAdmission:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._user_requests: dict[str, deque[float]] = defaultdict(deque)
        self._ip_requests: dict[str, deque[float]] = defaultdict(deque)
        self._active_users: dict[str, int] = defaultdict(int)
        self._replay_access: dict[str, int] = defaultdict(int)
        self._workspace_exclusive: set[str] = set()
        self._active_total = 0

    @staticmethod
    def _record(history: deque[float], now: float, limit: int) -> bool:
        while history and now - history[0] >= _WINDOW_SECONDS:
            history.popleft()
        if len(history) >= limit:
            return False
        history.append(now)
        return True

    async def acquire(self, user_id: str, ip_address: str) -> ChatPermit:
        async with self._lock:
            if user_id in self._workspace_exclusive:
                raise HTTPException(
                    status_code=409,
                    detail="A workspace update is in progress. Please retry shortly.",
                    headers={"Retry-After": "2"},
                )
            now = time.monotonic()
            user_limit = _positive_int("CHAT_USER_REQUESTS_PER_MINUTE", 10)
            ip_limit = _positive_int("CHAT_IP_REQUESTS_PER_MINUTE", 30)
            if not self._record(self._user_requests[user_id], now, user_limit):
                raise HTTPException(
                    status_code=429,
                    detail="Too many chat requests. Please wait and retry.",
                    headers={"Retry-After": "60"},
                )
            if not self._record(self._ip_requests[ip_address], now, ip_limit):
                raise HTTPException(
                    status_code=429,
                    detail="Too many chat requests from this network.",
                    headers={"Retry-After": "60"},
                )

            per_user = _positive_int("CHAT_MAX_CONCURRENT_PER_USER", 1)
            global_limit = _positive_int("CHAT_MAX_CONCURRENT_GLOBAL", 4)
            if self._active_users[user_id] >= per_user or self._active_total >= global_limit:
                raise HTTPException(
                    status_code=429,
                    detail="A chat request is already in progress. Please wait.",
                    headers={"Retry-After": "2"},
                )
            self._active_users[user_id] += 1
            self._active_total += 1
            return ChatPermit(user_id=user_id)

    async def release(self, permit: ChatPermit) -> None:
        async with self._lock:
            active = self._active_users.get(permit.user_id, 0)
            if active <= 1:
                self._active_users.pop(permit.user_id, None)
            else:
                self._active_users[permit.user_id] = active - 1
            self._active_total = max(0, self._active_total - 1)

    async def reset(self) -> None:
        async with self._lock:
            self._user_requests.clear()
            self._ip_requests.clear()
            self._active_users.clear()
            self._replay_access.clear()
            self._workspace_exclusive.clear()
            self._active_total = 0

    async def acquire_replay_access(self, user_id: str) -> ReplayAccessPermit:
        async with self._lock:
            if user_id in self._workspace_exclusive:
                raise HTTPException(
                    status_code=409,
                    detail="A workspace update is in progress. Please retry shortly.",
                    headers={"Retry-After": "2"},
                )
            self._replay_access[user_id] += 1
            return ReplayAccessPermit(user_id=user_id)

    async def release_replay_access(self, permit: ReplayAccessPermit) -> None:
        async with self._lock:
            active = self._replay_access.get(permit.user_id, 0)
            if active <= 1:
                self._replay_access.pop(permit.user_id, None)
            else:
                self._replay_access[permit.user_id] = active - 1

    async def acquire_workspace_exclusive(self, user_ids: Iterable[str]) -> tuple[str, ...]:
        principals = tuple(sorted(set(user_ids)))
        async with self._lock:
            if any(
                self._active_users.get(user_id, 0)
                or self._replay_access.get(user_id, 0)
                or user_id in self._workspace_exclusive
                for user_id in principals
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Wait for the active Assistant request to finish, then retry.",
                    headers={"Retry-After": "2"},
                )
            self._workspace_exclusive.update(principals)
        return principals

    async def release_workspace_exclusive(self, user_ids: tuple[str, ...]) -> None:
        async with self._lock:
            for user_id in user_ids:
                self._workspace_exclusive.discard(user_id)


chat_admission = ChatAdmission()


class ReplayLookupAdmission:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._user_requests: dict[str, deque[float]] = defaultdict(deque)
        self._ip_requests: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, user_id: str, ip_address: str) -> None:
        async with self._lock:
            now = time.monotonic()
            user_limit = _positive_int("CHAT_REPLAY_LOOKUPS_PER_MINUTE", 60)
            ip_limit = _positive_int("CHAT_REPLAY_LOOKUPS_PER_IP_PER_MINUTE", 180)
            if not ChatAdmission._record(self._user_requests[user_id], now, user_limit):
                raise HTTPException(
                    status_code=429,
                    detail="Too many chat retry checks. Please wait and retry.",
                    headers={"Retry-After": "60"},
                )
            if not ChatAdmission._record(self._ip_requests[ip_address], now, ip_limit):
                raise HTTPException(
                    status_code=429,
                    detail="Too many chat retry checks from this network.",
                    headers={"Retry-After": "60"},
                )

    async def reset(self) -> None:
        async with self._lock:
            self._user_requests.clear()
            self._ip_requests.clear()


replay_lookup_admission = ReplayLookupAdmission()


async def acquire_chat(request: Request, user_id: str) -> ChatPermit:
    return await chat_admission.acquire(user_id, client_ip(request))


async def check_replay_lookup(request: Request, user_id: str) -> None:
    await replay_lookup_admission.check(user_id, client_ip(request))


async def acquire_replay_access(user_id: str) -> ReplayAccessPermit:
    return await chat_admission.acquire_replay_access(user_id)


async def release_replay_access(permit: ReplayAccessPermit) -> None:
    await chat_admission.release_replay_access(permit)


async def acquire_workspace_exclusive(*user_ids: str) -> tuple[str, ...]:
    return await chat_admission.acquire_workspace_exclusive(user_ids)


async def release_workspace_exclusive(user_ids: tuple[str, ...]) -> None:
    await chat_admission.release_workspace_exclusive(user_ids)


async def release_chat(permit: ChatPermit) -> None:
    await chat_admission.release(permit)
