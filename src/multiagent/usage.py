"""Per-user monthly LLM cost cap.

Tracks prompt + completion tokens per `(user_id, YYYYMM)` and refuses new
turns once the user's running cost crosses ``MONTHLY_LLM_COST_CAP_USD`` (env,
default $20). Storage:

- Hosted (`storage_cosmos.is_enabled()`): doc id ``usage_<YYYYMM>`` in the
  ``users`` container, partition ``/user_id``.
- Local: ``~/.multiagent/usage/<user_id>_<YYYYMM>.json``.

Pricing comes from a small constants table keyed by the deployment name
prefix; unknown models fall back to a conservative gpt-4o-mini-ish rate so we
never report zero cost.

The module is intentionally side-effect-free at import time. ``record_usage``
is what actually persists; everything else just reads.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from multiagent.observability import app_event

# Per-1K-token USD rates (rough Azure list prices, mid-2026). Keys are
# *prefixes* of the deployment name lowered. First match wins; ordering matters
# for "gpt-4.1-mini" vs "gpt-4.1".
_RATES: list[tuple[str, float, float]] = [
    # prefix, prompt_per_1k, completion_per_1k
    ("gpt-5", 0.005, 0.015),
    ("gpt-4.1-mini", 0.00015, 0.0006),
    ("gpt-4.1", 0.003, 0.012),
    ("gpt-4o-mini", 0.00015, 0.0006),
    ("gpt-4o", 0.0025, 0.01),
    ("gpt-4", 0.03, 0.06),
    ("gpt-3.5", 0.0005, 0.0015),
]

_DEFAULT_RATE = (0.001, 0.003)  # if we don't know the model, assume cheap-ish

_CONTAINER = "users"
_LOCK = threading.Lock()


def _month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m")


def _doc_id(month: str) -> str:
    return f"usage_{month}"


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a single LLM call."""
    name = (model or "").lower()
    p_rate, c_rate = _DEFAULT_RATE
    for prefix, p, c in _RATES:
        if name.startswith(prefix):
            p_rate, c_rate = p, c
            break
    return (prompt_tokens / 1000.0) * p_rate + (completion_tokens / 1000.0) * c_rate


def get_cap_usd() -> float:
    """Read the monthly cap from env. Default 20.0; ``<= 0`` disables the cap."""
    raw = os.getenv("MONTHLY_LLM_COST_CAP_USD", "20")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 20.0


def _local_dir() -> Path:
    base = Path(os.getenv("MULTIAGENT_HOME", str(Path.home() / ".multiagent"))) / "usage"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _local_path(user_id: str, month: str) -> Path:
    safe = user_id.replace("/", "_").replace("\\", "_")
    return _local_dir() / f"{safe}_{month}.json"


def _local_load(user_id: str, month: str) -> dict[str, Any]:
    path = _local_path(user_id, month)
    if not path.exists():
        return {"user_id": user_id, "month": month, "prompt_tokens": 0,
                "completion_tokens": 0, "cost_usd": 0.0, "calls": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"user_id": user_id, "month": month, "prompt_tokens": 0,
                "completion_tokens": 0, "cost_usd": 0.0, "calls": 0}


def _local_save(user_id: str, month: str, doc: dict[str, Any]) -> None:
    path = _local_path(user_id, month)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _empty_doc(user_id: str, month: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "month": month,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "calls": 0,
    }


def get_usage(user_id: str, month: str | None = None) -> dict[str, Any]:
    """Return the running usage doc for ``(user_id, month)``.

    Always returns a dict (filled with zeros if no prior record). Never
    raises on storage errors -- those degrade to zeros so the agent can keep
    running.
    """
    month = month or _month_key()
    from multiagent import storage_cosmos

    if storage_cosmos.is_enabled():
        try:
            doc = storage_cosmos.read_doc(_CONTAINER, user_id, _doc_id(month))
            if doc:
                return doc
        except Exception:
            pass
    return _local_load(user_id, month)


def record_usage(
    user_id: str,
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, Any]:
    """Add tokens + computed cost to the running monthly bucket and persist."""
    month = _month_key()
    cost = cost_for(model, prompt_tokens, completion_tokens)
    with _LOCK:
        doc = get_usage(user_id, month) or _empty_doc(user_id, month)
        doc["user_id"] = user_id
        doc["month"] = month
        doc["prompt_tokens"] = int(doc.get("prompt_tokens", 0)) + int(prompt_tokens or 0)
        doc["completion_tokens"] = int(doc.get("completion_tokens", 0)) + int(completion_tokens or 0)
        doc["cost_usd"] = round(float(doc.get("cost_usd", 0.0)) + cost, 6)
        doc["calls"] = int(doc.get("calls", 0)) + 1
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()

        from multiagent import storage_cosmos

        if storage_cosmos.is_enabled():
            try:
                storage_cosmos.upsert_doc(_CONTAINER, user_id, _doc_id(month), doc)
            except Exception:
                # Fall back to local so we don't lose the accounting.
                _local_save(user_id, month, doc)
        else:
            _local_save(user_id, month, doc)

    app_event(
        "llm_usage",
        user_id=user_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=round(cost, 6),
        month_cost_usd=doc["cost_usd"],
    )
    return doc


def is_over_cap(user_id: str) -> tuple[bool, dict[str, Any]]:
    """Return ``(over, usage_doc)``. Cap of ``<= 0`` disables the check."""
    cap = get_cap_usd()
    usage = get_usage(user_id)
    if cap <= 0:
        return False, usage
    over = float(usage.get("cost_usd", 0.0)) >= cap
    return over, usage


def cap_message(usage: dict[str, Any]) -> str:
    """Polite refusal text shown when the user trips the cap."""
    cap = get_cap_usd()
    spent = float(usage.get("cost_usd", 0.0))
    month = usage.get("month", _month_key())
    return (
        f"You've reached this month's planning budget "
        f"(${spent:.2f} of ${cap:.2f} for {month}). "
        "New requests will resume next month — your saved trips and "
        "preferences are untouched."
    )


def clear_usage(user_id: str) -> int:
    """Delete all usage buckets for ``user_id`` and return delete count."""
    from multiagent import storage_cosmos

    deleted = 0
    if storage_cosmos.is_enabled():
        try:
            return storage_cosmos.delete_docs(_CONTAINER, user_id, id_prefix="usage_")
        except Exception:
            return 0

    safe = user_id.replace("/", "_").replace("\\", "_")
    for path in _local_dir().glob(f"{safe}_*.json"):
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
    return deleted
