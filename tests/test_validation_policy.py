from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "dev" / "validation_policy.py"
SPEC = importlib.util.spec_from_file_location("validation_policy", MODULE_PATH)
assert SPEC and SPEC.loader
validation_policy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validation_policy
SPEC.loader.exec_module(validation_policy)

POLICY_PATH = ROOT / "scripts" / "dev" / "validation-policy.json"
POWERSHELL_READER = ROOT / "scripts" / "dev" / "lib" / "validation-policy.ps1"


def write_policy(tmp_path: Path, gates: dict[str, dict[str, str]]) -> Path:
    path = tmp_path / "validation-policy.json"
    path.write_text(json.dumps({"version": 1, "gates": gates}), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_ambient_override(monkeypatch: pytest.MonkeyPatch) -> None:
    # The override is an environment variable so it reaches nested script calls,
    # which also means a developer's own shell could otherwise silently decide
    # the result of every assertion below.
    monkeypatch.delenv(validation_policy.FULL_SUITES_ENV, raising=False)


def test_a_suspended_gate_does_not_run(tmp_path: Path) -> None:
    path = write_policy(tmp_path, {"pytest": {"state": "suspended"}})

    assert validation_policy.gate_enabled("pytest", path=path) is False


def test_a_required_gate_runs(tmp_path: Path) -> None:
    path = write_policy(tmp_path, {"pytest": {"state": "required"}})

    assert validation_policy.gate_enabled("pytest", path=path) is True


def test_gates_are_independent_so_one_can_return_before_the_other(tmp_path: Path) -> None:
    path = write_policy(
        tmp_path, {"pytest": {"state": "suspended"}, "vitest": {"state": "required"}}
    )

    assert validation_policy.gate_enabled("pytest", path=path) is False
    assert validation_policy.gate_enabled("vitest", path=path) is True


def test_a_missing_policy_file_runs_every_gate(tmp_path: Path) -> None:
    # Fail closed. A policy we cannot read must never be the reason a gate
    # silently stops protecting the tree.
    assert validation_policy.gate_enabled("pytest", path=tmp_path / "absent.json") is True


def test_a_malformed_policy_file_runs_every_gate(tmp_path: Path) -> None:
    path = tmp_path / "validation-policy.json"
    path.write_text("{ not json", encoding="utf-8")

    assert validation_policy.gate_enabled("pytest", path=path) is True


def test_an_unknown_gate_name_runs(tmp_path: Path) -> None:
    path = write_policy(tmp_path, {"pytest": {"state": "suspended"}})

    assert validation_policy.gate_enabled("mypy", path=path) is True


def test_the_environment_override_re_enables_a_suspended_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_policy(tmp_path, {"pytest": {"state": "suspended"}})
    monkeypatch.setenv(validation_policy.FULL_SUITES_ENV, "1")

    assert validation_policy.gate_enabled("pytest", path=path) is True


def test_only_the_exact_override_value_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_policy(tmp_path, {"pytest": {"state": "suspended"}})
    monkeypatch.setenv(validation_policy.FULL_SUITES_ENV, "0")

    assert validation_policy.gate_enabled("pytest", path=path) is False


def test_the_suspension_note_never_collides_with_the_frontend_substring_test(
    tmp_path: Path,
) -> None:
    # multiagent.integrate decides whether to run the web suite by searching an
    # assignment's previous validation text for "frontend/" or "packages/", and
    # overwrites that same field with this summary. A note containing either
    # substring would silently re-enable the web suite on re-integration.
    path = write_policy(tmp_path, {"vitest": {"state": "suspended", "since": "2026-09-12"}})

    note = validation_policy.suspension_note("vitest", path=path)

    assert "frontend/" not in note
    assert "packages/" not in note
    assert "SUSPENDED" in note


def test_the_checked_in_policy_is_valid_and_declares_every_gate_the_scripts_read() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["version"] == 1
    gates = policy["gates"]
    assert set(gates) >= {"lint", "typecheck", "build", "pytest", "vitest"}
    for name, entry in gates.items():
        assert entry["state"] in {"required", "suspended"}, name
        # A suspended gate must say when and why, and name where the debt is
        # tracked, or the suspension becomes folklore.
        if entry["state"] == "suspended":
            assert entry.get("since"), name
            assert entry.get("reason"), name
            assert entry.get("tracked_by"), name

    for referenced in (policy["health_check"], policy["baseline"], policy["doc"]):
        assert (ROOT / referenced).exists(), referenced


def test_both_readers_agree_on_the_override_variable_name() -> None:
    # The PowerShell and Python readers are separate implementations of one
    # contract; the environment variable is the only thing they must spell
    # identically for -FullSuites to reach multiagent.py.
    powershell = POWERSHELL_READER.read_text(encoding="utf-8")

    assert validation_policy.FULL_SUITES_ENV == "TRIPPLANNER_FULL_SUITES"
    assert "TRIPPLANNER_FULL_SUITES" in powershell
    assert "suspended" in powershell
