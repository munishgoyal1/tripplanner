"""Dependency direction and compatibility contracts for the harness/eval split."""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "tripplanner"


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("validation.runner", "harness.audit"),
        ("validation.corpus", "harness.corpus"),
        ("validation.generate", "harness.generation.generate"),
        ("validation.emulator", "harness.sources.emulator"),
        ("validation.checks", "evals.deterministic.checks"),
        ("validation.quality", "evals.human"),
        ("validation.harness.evidence", "harness.evidence"),
        ("validation.harness.pricing", "pricing"),
    ],
)
def test_legacy_imports_share_module_state(legacy, canonical, monkeypatch) -> None:
    old = importlib.import_module(f"tripplanner.{legacy}")
    new = importlib.import_module(f"tripplanner.{canonical}")
    assert old is new
    sentinel = object()
    monkeypatch.setattr(old, "_compatibility_probe", sentinel, raising=False)
    assert new._compatibility_probe is sentinel


def test_legacy_and_shared_context_restore_the_same_nested_scope() -> None:
    from tripplanner.observability.context import current_context, run_scope
    from tripplanner.validation.harness.context import harness_scope

    assert current_context() is None
    with run_scope("outer", run_id="outer-run") as outer:
        with pytest.raises(RuntimeError), harness_scope("inner", run_id="inner-run"):
            assert current_context().run_id == "inner-run"
            raise RuntimeError("failed execution")
        assert current_context() is outer
    assert current_context() is None


def test_evaluators_and_runtime_telemetry_do_not_depend_on_harness() -> None:
    files = [
        *SOURCE.joinpath("evals").rglob("*.py"),
        *SOURCE.joinpath("observability").rglob("*.py"),
        *(SOURCE / name for name in (
            "pricing.py", "provider_usage.py", "usage.py", "usage_attribution.py",
        )),
    ]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
                imports.extend(f"{node.module}.{alias.name}" for alias in node.names)
            assert not any(
                name == prefix or name.startswith(prefix + ".")
                for name in imports
                for prefix in ("tripplanner.harness", "tripplanner.validation")
            ), path


def test_runtime_telemetry_does_not_load_evaluation_packages() -> None:
    script = """
import sys
from tripplanner.observability import app_event
from tripplanner import provider_usage, usage
app_event('boundary_probe', status='ok')
for prefix in ('tripplanner.harness', 'tripplanner.evals', 'tripplanner.validation'):
    assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_plan_eval_module_cli_still_lists_scenarios() -> None:
    from tripplanner.evals import SCENARIOS

    result = subprocess.run(
        [sys.executable, "-m", "tripplanner.evals", "--list"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [f"{case.id}\t{case.name}" for case in SCENARIOS]


def test_registry_keeps_historical_report_identity() -> None:
    from tripplanner.evals.registry import registry

    owners = {rule.evaluated_in for rule in registry()}
    # These serialized identities contribute to historical report fingerprints.
    assert "tripplanner.validation.render" in owners
    assert "tripplanner.validation.mutations" in owners
    assert "tripplanner.validation.quality" in owners
    for owner in owners:
        importlib.import_module(owner)
