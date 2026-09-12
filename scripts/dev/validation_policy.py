"""Read which validation gates the lane scripts should run.

The gates are declared as ``VALIDATION_GATE_<NAME>`` entries in
``config/environments/local.env``, beside every other checked-in non-secret
knob, so there is one configuration file to look in rather than a dedicated one
for this. ``scripts/dev/lib/validation-policy.ps1`` reads the same keys for the
PowerShell lane scripts; this module serves the multiagent coordinator. One
file, one decision, three call sites that cannot drift apart.

Because the declarations are environment-variable names, a real environment
variable overrides the file for free -- which is how the per-run overrides work.

Nothing here deletes a gate. A suspended gate's command still lives at its call
site behind :func:`gate_enabled`, so restoring it is a config edit rather than a
code change.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "environments" / "local.env"
FULL_SUITES_ENV = "TRIPPLANNER_FULL_SUITES"
GATES = ("lint", "typecheck", "build", "pytest", "vitest")
SUSPENDED = "suspended"

_cache: dict[str, str] | None = None
_cache_loaded = False


def gate_variable(gate: str) -> str:
    """The environment-variable name a gate is declared under."""
    return f"VALIDATION_GATE_{gate.upper()}"


def load_policy(path: Path | None = None) -> dict[str, str]:
    """Return the ``VALIDATION_GATE_*`` declarations found in the env file.

    An unreadable or absent file yields an empty mapping, which every consumer
    treats as "run every gate". A policy we cannot read must never be the reason
    a gate silently stops protecting the tree.

    Deliberately a small hand-rolled parser rather than python-dotenv: this runs
    from ``scripts/dev`` where the application's dependencies are not guaranteed
    to be importable, and the only syntax it needs is ``KEY=value`` with ``#``
    comments.
    """
    global _cache, _cache_loaded
    cache_result = path is None
    if cache_result:
        if _cache_loaded:
            return dict(_cache or {})
        path = POLICY_PATH

    found: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key.startswith("VALIDATION_GATE_"):
            continue
        # Trim an inline comment and surrounding quotes.
        value = value.split("#", 1)[0].strip().strip("\"'").lower()
        found[key] = value

    if cache_result:
        _cache = found
        _cache_loaded = True
    return dict(found)


def gate_enabled(gate: str, *, path: Path | None = None) -> bool:
    """True when ``gate`` should run in this invocation.

    Resolution order, matching ``Test-GateEnabled`` in the PowerShell reader:

    1. ``TRIPPLANNER_FULL_SUITES=1`` forces every gate on.
    2. A ``VALIDATION_GATE_<NAME>`` environment variable, if one is set.
    3. The same key in ``config/environments/local.env``.
    4. Anything else -- unknown gate, missing file, unrecognised value -- means
       run.

    Only the exact word ``suspended`` skips a gate. A typo therefore runs the
    check rather than silently disabling it.
    """
    if os.environ.get(FULL_SUITES_ENV) == "1":
        return True

    variable = gate_variable(gate)
    override = os.environ.get(variable)
    if override is not None:
        return override.strip().lower() != SUSPENDED

    return load_policy(path).get(variable, "").strip() != SUSPENDED


def suspension_note(gate: str, *, path: Path | None = None) -> str:
    """One line recording that ``gate`` did not run, for a validation summary.

    Deliberately free of the substrings ``frontend/`` and ``packages/``:
    ``multiagent.integrate`` decides whether to run the web suite by searching an
    assignment's previous validation text for exactly those, and that same field
    is overwritten with this summary. Saying "web suite" keeps the two apart.
    """
    return (
        f"{gate}: SUSPENDED by config/environments/local.env "
        f"({gate_variable(gate)}) - not run, not passing. "
        "Health: scripts/dev/suite-health.ps1"
    )
