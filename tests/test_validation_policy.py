from __future__ import annotations

import importlib.util
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

LOCAL_ENV = ROOT / "config" / "environments" / "local.env"
POWERSHELL_READER = ROOT / "scripts" / "dev" / "lib" / "validation-policy.ps1"


def write_env(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "local.env"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_ambient_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    # The overrides are environment variables so they reach nested script calls,
    # which also means a developer's own shell could otherwise silently decide
    # the result of every assertion below.
    monkeypatch.delenv(validation_policy.FULL_SUITES_ENV, raising=False)
    for gate in validation_policy.GATES:
        monkeypatch.delenv(validation_policy.gate_variable(gate), raising=False)


def test_a_suspended_gate_does_not_run(tmp_path: Path) -> None:
    path = write_env(tmp_path, "VALIDATION_GATE_PYTEST=suspended\n")

    assert validation_policy.gate_enabled("pytest", path=path) is False


def test_a_required_gate_runs(tmp_path: Path) -> None:
    path = write_env(tmp_path, "VALIDATION_GATE_PYTEST=required\n")

    assert validation_policy.gate_enabled("pytest", path=path) is True


def test_gates_are_independent_so_one_can_return_before_the_other(tmp_path: Path) -> None:
    path = write_env(
        tmp_path, "VALIDATION_GATE_PYTEST=suspended\nVALIDATION_GATE_VITEST=required\n"
    )

    assert validation_policy.gate_enabled("pytest", path=path) is False
    assert validation_policy.gate_enabled("vitest", path=path) is True


def test_unrelated_env_keys_are_ignored(tmp_path: Path) -> None:
    # The gates live in the application's own runtime profile, so the parser has
    # to walk past a few hundred lines of unrelated configuration.
    path = write_env(
        tmp_path,
        "# === Azure OpenAI ===\n"
        "ENABLE_AZURE_OPENAI=1\n"
        "AZURE_OPENAI_DEPLOYMENT=gpt-5.4-mini\n"
        "\n"
        "VALIDATION_GATE_PYTEST=suspended\n"
        "COST_CEILING_INR_DAILY=1000\n",
    )

    assert validation_policy.gate_enabled("pytest", path=path) is False
    assert validation_policy.load_policy(path) == {"VALIDATION_GATE_PYTEST": "suspended"}


def test_comments_and_inline_comments_and_quotes_are_stripped(tmp_path: Path) -> None:
    path = write_env(
        tmp_path,
        "# VALIDATION_GATE_PYTEST=required   <- commented out, must not count\n"
        'VALIDATION_GATE_PYTEST="suspended"  # paid once on master instead\n',
    )

    assert validation_policy.gate_enabled("pytest", path=path) is False


def test_a_missing_env_file_runs_every_gate(tmp_path: Path) -> None:
    # Fail closed. A policy we cannot read must never be the reason a gate
    # silently stops protecting the tree.
    assert validation_policy.gate_enabled("pytest", path=tmp_path / "absent.env") is True


def test_an_undeclared_gate_runs(tmp_path: Path) -> None:
    path = write_env(tmp_path, "VALIDATION_GATE_PYTEST=suspended\n")

    assert validation_policy.gate_enabled("vitest", path=path) is True


def test_only_the_exact_word_suspended_skips_a_gate(tmp_path: Path) -> None:
    # A typo must run the check, not quietly disable it.
    for value in ("suspend", "Suspended!", "off", "0", "false", ""):
        path = write_env(tmp_path, f"VALIDATION_GATE_PYTEST={value}\n")
        assert validation_policy.gate_enabled("pytest", path=path) is True, value


def test_the_word_is_case_insensitive(tmp_path: Path) -> None:
    path = write_env(tmp_path, "VALIDATION_GATE_PYTEST=SUSPENDED\n")

    assert validation_policy.gate_enabled("pytest", path=path) is False


def test_full_suites_re_enables_every_suspended_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_env(
        tmp_path, "VALIDATION_GATE_PYTEST=suspended\nVALIDATION_GATE_VITEST=suspended\n"
    )
    monkeypatch.setenv(validation_policy.FULL_SUITES_ENV, "1")

    assert validation_policy.gate_enabled("pytest", path=path) is True
    assert validation_policy.gate_enabled("vitest", path=path) is True


def test_a_real_environment_variable_beats_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # This is the whole reason the gates are declared as env-var names: a one-off
    # override needs no file edit.
    path = write_env(tmp_path, "VALIDATION_GATE_PYTEST=suspended\n")
    monkeypatch.setenv("VALIDATION_GATE_PYTEST", "required")

    assert validation_policy.gate_enabled("pytest", path=path) is True


def test_an_environment_variable_can_also_suspend_a_required_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_env(tmp_path, "VALIDATION_GATE_LINT=required\n")
    monkeypatch.setenv("VALIDATION_GATE_LINT", "suspended")

    assert validation_policy.gate_enabled("lint", path=path) is False


def test_the_suspension_note_never_collides_with_the_frontend_substring_test() -> None:
    # multiagent.integrate decides whether to run the web suite by searching an
    # assignment's previous validation text for "frontend/" or "packages/", and
    # overwrites that same field with this summary. A note containing either
    # substring would silently re-enable the web suite on re-integration.
    note = validation_policy.suspension_note("vitest")

    assert "frontend/" not in note
    assert "packages/" not in note
    assert "SUSPENDED" in note
    assert "VALIDATION_GATE_VITEST" in note


def test_the_checked_in_profile_declares_every_gate_the_scripts_read() -> None:
    declared = validation_policy.load_policy(LOCAL_ENV)

    expected = {validation_policy.gate_variable(gate) for gate in validation_policy.GATES}
    assert set(declared) == expected
    for variable, value in declared.items():
        assert value in {"required", "suspended"}, f"{variable}={value}"


def test_the_suite_health_script_and_baseline_the_notices_point_at_exist() -> None:
    # Every suspension banner names these two paths. A banner pointing at a file
    # that does not exist is worse than no banner.
    assert (ROOT / "scripts" / "dev" / "suite-health.ps1").exists()
    assert (ROOT / "scripts" / "dev" / "test-health-baseline.json").exists()


def test_both_readers_agree_on_the_contract() -> None:
    # The PowerShell and Python readers are separate implementations of one
    # contract; these spellings are the only things they must share exactly.
    powershell = POWERSHELL_READER.read_text(encoding="utf-8")

    assert validation_policy.FULL_SUITES_ENV == "TRIPPLANNER_FULL_SUITES"
    assert "TRIPPLANNER_FULL_SUITES" in powershell
    assert "VALIDATION_GATE_" in powershell
    assert "config/environments/local.env" in powershell
    assert "suspended" in powershell
