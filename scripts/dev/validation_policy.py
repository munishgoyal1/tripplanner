"""Read the shared validation-gate policy.

The PowerShell lane scripts read ``scripts/dev/validation-policy.json`` through
``scripts/dev/lib/validation-policy.ps1``; the multiagent coordinator reads the
same file through this module. One file, one decision, three call sites that
cannot drift apart.

Nothing here deletes a gate. A suspended gate's command still lives at its call
site behind :func:`gate_enabled`, so restoring it is a policy edit rather than a
code change.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

POLICY_PATH = Path(__file__).resolve().parent / "validation-policy.json"
FULL_SUITES_ENV = "TRIPPLANNER_FULL_SUITES"

_cache: dict[str, Any] | None = None
_cache_loaded = False


def load_policy(path: Path | None = None) -> dict[str, Any] | None:
    """Return the parsed policy, or ``None`` when it cannot be read.

    A ``None`` result is not an error the caller has to handle specially: every
    consumer treats it as "run every gate". A policy we cannot read must never be
    the reason a gate silently stops protecting the tree.
    """
    global _cache, _cache_loaded
    if path is None:
        if _cache_loaded:
            return _cache
        path = POLICY_PATH
        cache_result = True
    else:
        cache_result = False

    parsed: dict[str, Any] | None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        parsed = None
    if not isinstance(parsed, dict):
        parsed = None

    if cache_result:
        _cache = parsed
        _cache_loaded = True
    return parsed


def gate_enabled(gate: str, *, path: Path | None = None) -> bool:
    """True when ``gate`` should run in this invocation.

    Resolution order, matching ``Test-GateEnabled`` in the PowerShell reader:

    1. ``TRIPPLANNER_FULL_SUITES=1`` forces every gate on.
    2. The gate's ``state`` in the policy file; ``"suspended"`` means skip.
    3. Anything else -- unknown gate, missing file, malformed JSON -- means run.
    """
    if os.environ.get(FULL_SUITES_ENV) == "1":
        return True

    policy = load_policy(path)
    if not policy:
        return True

    gates = policy.get("gates")
    if not isinstance(gates, dict):
        return True
    entry = gates.get(gate)
    if not isinstance(entry, dict):
        return True
    return entry.get("state") != "suspended"


def suspension_note(gate: str, *, path: Path | None = None) -> str:
    """One line recording that ``gate`` did not run, for a validation summary.

    Deliberately free of the substrings ``frontend/`` and ``packages/``:
    ``multiagent.integrate`` decides whether to run the web suite by searching an
    assignment's previous validation text for exactly those, and that same field
    is overwritten with this summary. Saying "web suite" keeps the two apart.
    """
    policy = load_policy(path)
    entry: dict[str, Any] = {}
    if policy:
        gates = policy.get("gates")
        if isinstance(gates, dict) and isinstance(gates.get(gate), dict):
            entry = gates[gate]

    since = f" since {entry['since']}" if entry.get("since") else ""
    health = (policy or {}).get("health_check", "scripts/dev/suite-health.ps1")
    return (
        f"{gate}: SUSPENDED{since} by scripts/dev/validation-policy.json "
        f"- not run, not passing. Health: {health}"
    )
