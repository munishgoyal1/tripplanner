"""Per-request user identity context.

The trip agent's tools persist preferences and trip state per user. In CLI
and test mode there's one implicit user ("local"); in the hosted Chainlit
app each chat session sets its own ID before invoking the graph.

This module exposes a ContextVar so any tool can ask "who is the current
user?" without changing tool signatures.
"""

from __future__ import annotations

import contextvars

_DEFAULT_USER_ID = "local"

_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "multiagent_user_id", default=_DEFAULT_USER_ID
)


def get_user_id() -> str:
    """Return the user ID for the current execution context."""
    return _user_id.get()


def set_user_id(user_id: str) -> None:
    """Set the user ID for the current execution context."""
    _user_id.set(user_id or _DEFAULT_USER_ID)


def is_default_user() -> bool:
    """True if running under the default ("local") user — i.e. CLI or tests."""
    return _user_id.get() == _DEFAULT_USER_ID
