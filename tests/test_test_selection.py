from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "dev" / "test_selection.py"
SPEC = importlib.util.spec_from_file_location("test_selection", MODULE_PATH)
assert SPEC and SPEC.loader
test_selection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = test_selection
SPEC.loader.exec_module(test_selection)


@pytest.mark.parametrize(
    "source_path",
    [
        "src/tripplanner/web/trip_view.py",
        "src/tripplanner/web/map_view.py",
        "src/tripplanner/web/day_journey.py",
    ],
)
def test_source_module_selects_direct_and_cross_boundary_tests(source_path: str) -> None:
    selected = test_selection.select_tests([source_path])

    split_modules = {
        "tests/test_trip_view_summary_weather_budget.py",
        "tests/test_trip_view_itinerary_rendering.py",
        "tests/test_trip_view_map_focus.py",
        "tests/test_trip_view_journeys_transfers.py",
        "tests/test_trip_view_places_gallery.py",
        "tests/test_trip_view_verification_freshness.py",
    }
    assert split_modules <= selected.backend
    assert "tests/test_trip_view_api.py" in selected.backend
    assert "frontend/src/components/MapPanel.test.ts" in selected.frontend
    assert selected.frontend_typecheck
    assert not selected.backend_all


def test_colocated_frontend_test_is_selected_without_running_every_frontend_test() -> None:
    selected = test_selection.select_tests(["frontend/src/components/ChatPanel.tsx"])

    assert selected.frontend == {"frontend/src/components/ChatPanel.test.tsx"}
    assert selected.frontend_typecheck
    assert not selected.frontend_all


def test_changed_test_file_runs_itself() -> None:
    selected = test_selection.select_tests(["tests/test_graph_policy.py"])

    assert selected.backend == {"tests/test_graph_policy.py"}
    assert not selected.backend_all


def test_changed_support_module_runs_its_dependent_tests_not_the_helper() -> None:
    selected = test_selection.select_tests(["tests/support/trip_view.py"])

    assert "tests/test_trip_view_map_focus.py" in selected.backend
    assert "tests/support/trip_view.py" not in selected.backend
    assert not selected.backend_all


def test_changed_global_fixture_falls_back_to_complete_backend_suite() -> None:
    selected = test_selection.select_tests(["tests/conftest.py"])

    assert selected.backend_all
    assert selected.backend == set()


def test_working_tree_selection_includes_untracked_files(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output = "src/tripplanner/api.py\n" if command[1] == "diff" else "tests/test_new.py\n"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(test_selection.subprocess, "run", run)

    assert test_selection._changed_paths("origin/master", None) == [
        "src/tripplanner/api.py",
        "tests/test_new.py",
    ]
    assert calls[1] == ["git", "ls-files", "--others", "--exclude-standard"]


def test_unknown_executable_path_falls_back_to_complete_backend_suite() -> None:
    selected = test_selection.select_tests(["src/new_package/unmapped.py"])

    assert selected.backend_all
    assert selected.backend == set()
    assert "complete backend fallback" in selected.reasons[0]


def test_documentation_only_change_does_not_invent_runtime_validation() -> None:
    selected = test_selection.select_tests(["docs/development/dev.md"])

    assert test_selection.validation_commands(selected) == ()


def test_behavior_id_resolves_existing_executable_proofs() -> None:
    selected = test_selection.select_tests([], behavior_ids=["EB-PLAN-001"])

    proof = (
        "tests/test_parallel_tools.py::"
        "test_hotel_fallback_uses_successful_result_from_parallel_batch"
    )
    assert proof in selected.backend
    assert "frontend/src/App.test.tsx" in selected.frontend


def test_behavior_id_resolves_a_test_method_to_its_pytest_class_node() -> None:
    selected = test_selection.select_tests([], behavior_ids=["EB-PLAN-002"])

    assert (
        "tests/test_trip_persistence.py::TestPreferenceTools::"
        "test_create_trip_persists_planning_recommendation"
    ) in selected.backend


def test_behavior_proof_name_must_exist() -> None:
    with pytest.raises(ValueError, match="is missing"):
        test_selection._pytest_target("tests/test_test_selection.py", "test_absent")


def test_unknown_behavior_id_fails_loudly() -> None:
    with pytest.raises(ValueError, match="Unknown expected-behavior ID"):
        test_selection.select_tests([], behavior_ids=["EB-NOT-REAL"])


def test_shared_client_requires_web_and_mobile_validation() -> None:
    selected = test_selection.select_tests(["packages/tripplanner-client/src/events.ts"])

    assert selected.frontend_all
    assert selected.frontend_typecheck
    assert selected.mobile


def test_every_policy_test_target_exists() -> None:
    policy = test_selection.json.loads(test_selection.DEFAULT_POLICY.read_text(encoding="utf-8"))

    missing = [
        target
        for rule in policy["rules"]
        for target in (*rule.get("backend", ()), *rule.get("frontend", ()))
        if not (ROOT / target).is_file()
    ]
    assert missing == []


def test_every_behavior_test_link_points_to_an_existing_file() -> None:
    text = test_selection.EXPECTED_BEHAVIORS.read_text(encoding="utf-8")
    missing = [
        path
        for _label, path in test_selection.TEST_LINK.findall(text)
        if not (ROOT / path).is_file()
    ]
    assert missing == []


def test_every_named_behavior_proof_resolves_to_an_executable_node() -> None:
    text = test_selection.EXPECTED_BEHAVIORS.read_text(encoding="utf-8")

    for behavior_id in test_selection.BEHAVIOR_HEADING.findall(text):
        test_selection.behavior_tests(behavior_id)
