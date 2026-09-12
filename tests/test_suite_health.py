from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "dev" / "suite_health.py"
SPEC = importlib.util.spec_from_file_location("suite_health", MODULE_PATH)
assert SPEC and SPEC.loader
suite_health = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = suite_health
SPEC.loader.exec_module(suite_health)

Failure = suite_health.Failure
SuiteResult = suite_health.SuiteResult

# Recorded verbatim from a real gate run (logs/last-run/full-2way-sync.log), with
# the node ids un-wrapped. Every id below exists in tests/.
CLEAN_SUMMARY = """\
===================== short test summary info =====================
FAILED tests/test_parallel_tools.py::test_tool_node_runs_parallel_tool_calls_concurrently - \
AssertionError: ToolNode ran serially (took 0.94s)
FAILED tests/test_places_cache.py::test_prefetch_cache_hits_do_not_serialize_on_logging - \
AssertionError: assert 0.5060616999980994 < ((0.05 * 8) / 2)
FAILED tests/test_trip_rebalance.py::test_it_reduces_travel_by_grouping_the_day - \
AssertionError: assert False
7 failed, 2073 passed, 2 skipped, 1 warning in 1222.56s (0:20:22)
"""

# The same block as it was ACTUALLY recorded: Start-Transcript renders at the
# host console width, hard-wrapping node ids mid-word at ~66 columns.
WRAPPED_SUMMARY = """\
===================== short test summary info =====================
FAILED tests/test_parallel_tools.py::test_tool_node_runs_parallel_to
ol_calls_concurrently - AssertionError: ToolNode ran serially (took
0.94s)
FAILED tests/test_trip_rebalance.py::test_it_reduces_travel_by_group
ing_the_day - AssertionError: assert False
7 failed, 2073 passed, 2 skipped, 1 warning in 1222.56s (0:20:22)
"""


def junit(cases: list[tuple[str, str, bool]], **suite_attrs: str) -> str:
    tests = len(cases)
    failures = sum(1 for _, _, failed in cases if failed)
    body = "".join(
        f'<testcase file="{source}" name="{name}">'
        + ("<failure>boom</failure>" if failed else "")
        + "</testcase>"
        for source, name, failed in cases
    )
    attrs = {"tests": str(tests), "failures": str(failures), "errors": "0", "skipped": "0"}
    attrs.update(suite_attrs)
    rendered = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    return f'<?xml version="1.0"?><testsuite {rendered}>{body}</testsuite>'


THREE_FAILURES = [
    ("tests/test_parallel_tools.py", "test_tool_node_runs_parallel_tool_calls_concurrently", True),
    ("tests/test_places_cache.py", "test_prefetch_cache_hits_do_not_serialize_on_logging", True),
    ("tests/test_trip_rebalance.py", "test_it_reduces_travel_by_grouping_the_day", True),
    ("tests/test_graph_policy.py", "test_something_that_passes", False),
]


# ---------------------------------------------------------------------------
# pytest parsing
# ---------------------------------------------------------------------------


def test_it_reads_verbatim_node_ids_from_a_clean_summary() -> None:
    failures = suite_health.parse_pytest_summary(CLEAN_SUMMARY)

    assert [failure.id for failure in failures] == [
        "tests/test_parallel_tools.py::test_tool_node_runs_parallel_tool_calls_concurrently",
        "tests/test_places_cache.py::test_prefetch_cache_hits_do_not_serialize_on_logging",
        "tests/test_trip_rebalance.py::test_it_reduces_travel_by_grouping_the_day",
    ]
    assert failures[2].message == "AssertionError: assert False"


def test_it_refuses_console_wrapped_output_instead_of_truncating_a_node_id() -> None:
    # The failure mode this guards against is silent: "..._runs_parallel_to" is a
    # perfectly plausible node id that would never match its baseline entry, so
    # the same failure would be filed as NEW on every single run.
    with pytest.raises(suite_health.TruncatedOutputError) as caught:
        suite_health.parse_pytest_summary(WRAPPED_SUMMARY)

    assert "COLUMNS=400" in str(caught.value)


def test_junit_supplies_totals_and_the_failing_file_and_name(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(junit(THREE_FAILURES, time="1222.56", skipped="2"), encoding="utf-8")

    failed, totals = suite_health.parse_pytest_junit(path)

    assert ("tests/test_trip_rebalance.py", "test_it_reduces_travel_by_grouping_the_day") in failed
    assert totals["failed"] == 3
    assert totals["duration_seconds"] == 1222.56


def test_reconcile_accepts_two_records_that_agree(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(junit(THREE_FAILURES), encoding="utf-8")
    junit_failures, _ = suite_health.parse_pytest_junit(path)

    reconciled = suite_health.reconcile_pytest(
        suite_health.parse_pytest_summary(CLEAN_SUMMARY), junit_failures
    )

    assert len(reconciled) == 3


def test_reconcile_refuses_when_the_two_records_disagree_on_count(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(junit(THREE_FAILURES[:2] + [THREE_FAILURES[3]]), encoding="utf-8")
    junit_failures, _ = suite_health.parse_pytest_junit(path)

    with pytest.raises(suite_health.TruncatedOutputError):
        suite_health.reconcile_pytest(
            suite_health.parse_pytest_summary(CLEAN_SUMMARY), junit_failures
        )


def test_reconcile_refuses_a_node_id_junit_never_saw(tmp_path: Path) -> None:
    swapped = list(THREE_FAILURES)
    swapped[2] = ("tests/test_trip_rebalance.py", "test_a_completely_different_name", True)
    path = tmp_path / "junit.xml"
    path.write_text(junit(swapped), encoding="utf-8")
    junit_failures, _ = suite_health.parse_pytest_junit(path)

    with pytest.raises(suite_health.TruncatedOutputError):
        suite_health.reconcile_pytest(
            suite_health.parse_pytest_summary(CLEAN_SUMMARY), junit_failures
        )


# ---------------------------------------------------------------------------
# vitest parsing
# ---------------------------------------------------------------------------


def test_vitest_failures_are_keyed_by_repo_relative_path(tmp_path: Path) -> None:
    payload = {
        "testResults": [
            {
                "name": str(ROOT / "frontend" / "src" / "App.test.tsx"),
                "assertionResults": [
                    {"fullName": "App renders", "status": "passed"},
                    {
                        "fullName": "App shows the refreshed itinerary",
                        "status": "failed",
                        "failureMessages": ["AssertionError: expected 1 to be 2\n  at foo"],
                    },
                    {"fullName": "App skipped one", "status": "skipped"},
                ],
            }
        ]
    }
    path = tmp_path / "vitest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    failures, totals = suite_health.parse_vitest_json(path, ROOT)

    assert failures[0].id == "frontend/src/App.test.tsx::App shows the refreshed itinerary"
    assert failures[0].message == "AssertionError: expected 1 to be 2"
    assert totals == {"tests": 3, "passed": 1, "failed": 1, "skipped": 1}


# ---------------------------------------------------------------------------
# classification -- the part that keeps the debt honest
# ---------------------------------------------------------------------------


def baseline_with(*ids: str, first_seen: str = "2026-09-12") -> dict:
    return {
        "version": 1,
        "pytest": {
            "failures": [
                {"id": node, "first_seen": first_seen, "category": "real", "owner": "unassigned"}
                for node in ids
            ]
        },
    }


def test_a_failure_absent_from_the_baseline_is_new() -> None:
    result = SuiteResult("pytest", True, (Failure("tests/test_a.py::test_one"),), {})

    classified = suite_health.classify(result, baseline_with())

    assert [f.id for f in classified.new] == ["tests/test_a.py::test_one"]
    assert classified.known == ()


def test_a_failure_already_in_the_baseline_is_known_not_new() -> None:
    result = SuiteResult("pytest", True, (Failure("tests/test_a.py::test_one"),), {})

    classified = suite_health.classify(result, baseline_with("tests/test_a.py::test_one"))

    assert classified.new == ()
    assert [f.id for f in classified.known] == ["tests/test_a.py::test_one"]


def test_a_baseline_entry_that_now_passes_is_fixed() -> None:
    result = SuiteResult(
        "pytest", True, (), {"observed_ids": {"tests/test_a.py::test_one"}}
    )

    classified = suite_health.classify(result, baseline_with("tests/test_a.py::test_one"))

    assert classified.fixed == ("tests/test_a.py::test_one",)
    assert classified.missing == ()


def test_a_baseline_entry_that_did_not_run_at_all_is_missing_not_fixed() -> None:
    # Deleting or skipping a failing test is the cheapest way to make this system
    # lie. Folding it into "fixed" would reward exactly that.
    result = SuiteResult("pytest", True, (), {"observed_ids": {"tests/test_a.py::test_other"}})

    classified = suite_health.classify(result, baseline_with("tests/test_a.py::test_one"))

    assert classified.missing == ("tests/test_a.py::test_one",)
    assert classified.fixed == ()


def test_a_suite_that_could_not_run_never_reports_its_baseline_as_fixed() -> None:
    result = SuiteResult("pytest", False, error="collection error")

    classified = suite_health.classify(result, baseline_with("tests/test_a.py::test_one"))

    assert classified.fixed == ()
    assert classified.missing == ()
    assert classified.ran is False


# ---------------------------------------------------------------------------
# baseline merge
# ---------------------------------------------------------------------------


def test_updating_the_baseline_preserves_first_seen_owner_and_category() -> None:
    baseline = baseline_with("tests/test_a.py::test_one", first_seen="2026-01-05")
    baseline["pytest"]["failures"][0]["owner"] = "munish"
    baseline["pytest"]["failures"][0]["category"] = "flaky-under-load"
    baseline["pytest"]["failures"][0]["note"] = "search budget"
    result = SuiteResult("pytest", True, (Failure("tests/test_a.py::test_one", "boom"),), {})
    classified = suite_health.classify(result, baseline)

    merged = suite_health.merge_baseline(baseline, [classified], today="2026-09-12")

    entry = merged["pytest"]["failures"][0]
    assert entry["first_seen"] == "2026-01-05"  # ages visibly; never reset
    assert entry["owner"] == "munish"
    assert entry["category"] == "flaky-under-load"
    assert entry["note"] == "search budget"


def test_a_new_entry_is_stamped_with_today_and_marked_unreviewed() -> None:
    result = SuiteResult("pytest", True, (Failure("tests/test_a.py::test_one"),), {})
    classified = suite_health.classify(result, baseline_with())

    merged = suite_health.merge_baseline(baseline_with(), [classified], today="2026-09-12")

    entry = merged["pytest"]["failures"][0]
    assert entry["first_seen"] == "2026-09-12"
    assert entry["category"] == "unreviewed"


def test_a_fixed_entry_is_dropped_on_update() -> None:
    baseline = baseline_with("tests/test_a.py::test_one")
    result = SuiteResult("pytest", True, (), {"observed_ids": {"tests/test_a.py::test_one"}})
    classified = suite_health.classify(result, baseline)

    merged = suite_health.merge_baseline(baseline, [classified], today="2026-09-12")

    assert merged["pytest"]["failures"] == []


def test_a_suite_that_did_not_run_leaves_its_recorded_debt_untouched() -> None:
    baseline = baseline_with("tests/test_a.py::test_one")
    classified = suite_health.classify(SuiteResult("pytest", False, error="boom"), baseline)

    merged = suite_health.merge_baseline(baseline, [classified], today="2026-09-12")

    assert len(merged["pytest"]["failures"]) == 1


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def test_the_report_leads_with_the_only_red_signal() -> None:
    baseline = baseline_with("tests/test_a.py::test_known")
    result = SuiteResult(
        "pytest",
        True,
        (Failure("tests/test_a.py::test_known"), Failure("tests/test_b.py::test_fresh", "boom")),
        {"failed": 2},
    )
    classified = suite_health.classify(result, baseline)

    markdown = suite_health.render_markdown(
        [classified], baseline, today="2026-09-13", context={"ref": "master"}
    )

    assert "1 NEW FAILURE(S)" in markdown
    assert "tests/test_b.py::test_fresh" in markdown
    assert "1d old" in markdown  # known entries age visibly


def test_a_clean_run_against_a_nonempty_baseline_still_reads_as_green() -> None:
    baseline = baseline_with("tests/test_a.py::test_known")
    result = SuiteResult("pytest", True, (Failure("tests/test_a.py::test_known"),), {})
    classified = suite_health.classify(result, baseline)

    markdown = suite_health.render_markdown(
        [classified], baseline, today="2026-09-12", context={}
    )

    # Known debt alone must not turn the report red, or it goes permanently red
    # and people stop reading it.
    assert "NO NEW FAILURES" in markdown
