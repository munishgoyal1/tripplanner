from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path

import pytest

from tripplanner.evals import suite
from tripplanner.evals.contracts import REAL, REVISION, CorpusRecord
from tripplanner.evals.findings import Finding
from tripplanner.harness import audit, audit_report, corpus, incremental, lifecycle
from tripplanner.harness.results import ResultStore, fingerprint


def record(**changes):
    base = CorpusRecord(
        id="test:1",
        case_id="family-trip",
        provenance=REAL,
        source="test",
        plan={"destination": "Paris", "day_wise_itinerary": [{"day": 1, "stops": []}]},
        places={"museum|paris": {"lat": 48.8, "lng": 2.3}},
        request="A relaxed family trip",
    )
    return dataclasses.replace(base, **changes)


@pytest.fixture
def engine(monkeypatch, tmp_path):
    calls = []
    version = {"value": "implementation-1"}
    monkeypatch.setattr(incremental, "implementation_fingerprint", lambda: version["value"])
    monkeypatch.setattr(incremental, "code_identity", lambda _: ("c" * 40, False))

    def evaluate(name, case, ratings):
        calls.append((name, case.artifact_id))
        findings = [Finding("I9", "broken route", "Broken route", case.id, case.provenance)]
        return ("fail", findings, "") if case.plan.get("broken", True) else ("pass", [], "")

    monkeypatch.setattr(suite, "evaluate", evaluate)

    def run(case=None, **kwargs):
        return audit.audit(
            tmp_path,
            records=[case or record()],
            state_root=tmp_path / "state",
            baseline=kwargs.pop("baseline", {}),
            evaluators=kwargs.pop("evaluators", ("plan",)),
            quality_ratings=kwargs.pop("quality_ratings", {}),
            **kwargs,
        )

    return run, calls, version


def test_repeat_reuses_failure_without_hiding_it_or_renotifying(engine):
    run, calls, _ = engine
    first, second = run(), run()
    assert len(calls) == 1
    assert first.findings == second.findings
    assert first.new and not second.new
    assert second.evaluation["executed"] == 0
    assert second.evaluation["reused"] == 1
    assert second.evaluation["occurrences"][0]["status"] == "known"


@pytest.mark.parametrize(
    "change",
    [
        {"plan": {"destination": "Rome"}},
        {"request": "An active family trip"},
        {"preferences": {"pace": "slow"}},
        {"places": {"museum|paris": {"lat": 49, "lng": 2}}},
        {"final_reply": "Updated itinerary"},
        {"steps": ({"phase": "planning", "output": "revised"},)},
        {"generation": {"generated_by_commit": "new-producer"}},
    ],
)
def test_all_evaluation_context_changes_invalidate(engine, change):
    run, calls, _ = engine
    run()
    updated = run(record(**change))
    assert len(calls) == 2
    assert updated.evaluation["reused"] == 0


def test_ratings_invalidate_only_human_evaluator(engine):
    run, calls, _ = engine
    run(evaluators=("plan", "human"))
    changed = run(
        evaluators=("plan", "human"),
        quality_ratings={
            "ratings": {
                "test:1": {"hard_gates": {"scenario_preference_fidelity": {"outcome": "fail"}}}
            },
        },
    )
    assert [name for name, _ in calls] == ["plan", "human", "human"]
    assert changed.evaluation["reused"] == 1


def test_configuration_implementation_and_force_each_invalidate(engine):
    run, calls, version = engine
    first = run()
    run(configuration={"plan": {"rubric": "v2"}})
    version["value"] = "implementation-2"
    run()
    forced = run(force=True)
    assert len(calls) == 4
    assert forced.evaluation["results"][0]["id"] != first.evaluation["results"][0]["id"]


def test_corrupt_cache_is_recomputed_and_immutable_receipts_survive(engine, tmp_path):
    run, calls, _ = engine
    first = run().evaluation["results"][0]
    path = ResultStore(tmp_path / "state").path(first["id"])
    original = path.read_text()
    second = run(force=True).evaluation["results"][0]
    assert path.read_text() == original
    ResultStore(tmp_path / "state").path(second["id"]).write_text('{"broken":true}')
    recovered = run()
    assert len(calls) == 3
    assert recovered.findings


def test_errors_are_never_reused_and_report_cannot_claim_complete(engine, monkeypatch):
    run, _, _ = engine

    def fail(*_):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(suite, "evaluate", fail)
    first, second = run(), run()
    assert first.evaluation["errors"] == second.evaluation["errors"] == 1
    assert second.evaluation["executed"] == 1
    report = audit_report.build_report(second, {}, audit_report.build_report(first, {}))
    assert report["evidence"]["deterministic_rules"] == "partial"
    assert report["comparison"]["status"] == "not_comparable"
    assert report["retired"] == []


def test_lifecycle_preserves_artifacts_and_excludes_historical_by_default(engine, tmp_path):
    run, calls, _ = engine
    original = record()
    path = tmp_path / "corpus/evaluation-lifecycle.json"
    lifecycle.set_state(path, original.artifact_id, "historical", "Old planner output")
    excluded = run(selection="active")
    assert not calls and excluded.evaluation["excluded"]
    inspected = run(selection="historical")
    assert inspected.findings and not inspected.new
    lifecycle.set_state(path, original.artifact_id, "regression", "Protect the route fix")
    assert run(selection="regression").evaluation["reused"] == 1
    assert original.plan["destination"] == "Paris"


def test_revision_defaults_historical_and_unknown_producer_stays_unknown():
    case = record(provenance=REVISION)
    selected, excluded = lifecycle.select([case], {"artifacts": {}}, "active")
    assert not selected and excluded[0]["state"] == "historical"
    assert case.generation == {}


def test_corrupt_lifecycle_cannot_silently_exclude_inputs(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text('{"version":1,"artifacts":{"bad":{"state":"gone"}}}')
    with pytest.raises(ValueError):
        lifecycle.load_manifest(path)


def test_deduplication_preserves_distinct_request_context():
    cases = [record(), record(request="A fast trip")]
    assert len(corpus.deduplicate(cases)) == 2


def test_explicit_input_and_generated_manifest_retain_context(tmp_path):
    path = tmp_path / "manual.json"
    path.write_text(
        json.dumps(
            {
                "case_id": "manual",
                "plan": {"destination": "Paris"},
                "request": "Relax",
                "preferences": {"pace": "slow"},
                "steps": [{"output": "proposal"}],
            }
        )
    )
    loaded = corpus.from_json(path)
    assert loaded.case_identity == "manual" and loaded.request == "Relax"
    assert loaded.steps == ({"output": "proposal"},) and loaded.generation == {}
    trips = tmp_path / "trips"
    trips.mkdir()
    (trips / "paris.json").write_text('{"destination":"Paris"}')
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "produced": [
                    {
                        "slug": "paris",
                        "request": "Paris please",
                        "generated_by_commit": "abc",
                    }
                ]
            }
        )
    )
    generated = corpus.from_generated_finals(trips)[0]
    assert generated.request == "Paris please"
    assert generated.generation["generated_by_commit"] == "abc"


def test_verified_regeneration_does_not_reopen_old_failure_but_detects_recurrence(engine, tmp_path):
    run, _, _ = engine
    failed = run().evaluation["results"][0]
    passing_case = record(
        plan={"destination": "Paris", "broken": False},
        generation={"generated_by_commit": "c" * 40},
    )
    passed = run(passing_case).evaluation["results"][0]
    lifecycle.verify_fix(
        tmp_path / "state",
        "I9|broken route",
        failed["id"],
        passed["id"],
        "regenerated",
        "c" * 40,
        "#example",
    )
    historical = run()
    assert not historical.new
    assert historical.evaluation["occurrences"][0]["status"] == "historical"
    fresh = record(generation={"generated_by_commit": "d" * 40})
    baseline = {"accepted": {"I9|broken route": {}}}
    recurrence = run(fresh, baseline=baseline)
    assert recurrence.new
    assert recurrence.evaluation["occurrences"][0]["status"] == "recurring"
    assert not run(fresh, baseline=baseline).new


def test_replay_verification_requires_same_artifact_and_changed_implementation(
    engine, tmp_path, monkeypatch
):
    run, _, version = engine
    failed = run().evaluation["results"][0]
    monkeypatch.setattr(suite, "evaluate", lambda *_: ("pass", [], ""))
    same_code = run(force=True).evaluation["results"][0]
    with pytest.raises(ValueError, match="changed evaluator"):
        lifecycle.verify_fix(
            tmp_path / "state", "I9|broken route", failed["id"], same_code["id"], "replay", "c" * 40
        )
    version["value"] = "implementation-2"
    passed = run().evaluation["results"][0]
    proof = lifecycle.verify_fix(
        tmp_path / "state", "I9|broken route", failed["id"], passed["id"], "replay", "c" * 40
    )
    assert proof["before_artifact"] == proof["after_artifact"]
    changed_evidence = run(record(places={"new": {"lat": 1, "lng": 2}})).evaluation["results"][0]
    with pytest.raises(ValueError, match="unchanged evidence"):
        lifecycle.verify_fix(
            tmp_path / "state",
            "I9|broken route",
            failed["id"],
            changed_evidence["id"],
            "replay",
            "c" * 40,
        )


def test_missing_or_dirty_producer_cannot_verify_a_fix(engine, tmp_path):
    run, _, _ = engine
    failed = run().evaluation["results"][0]
    passed = run(record(plan={"destination": "Paris", "broken": False})).evaluation["results"][0]
    with pytest.raises(ValueError, match="produced by"):
        lifecycle.verify_fix(
            tmp_path / "state",
            "I9|broken route",
            failed["id"],
            passed["id"],
            "regenerated",
            "c" * 40,
        )
    with pytest.raises(ValueError, match="clean declared"):
        lifecycle.verify_fix(
            tmp_path / "state",
            "I9|broken route",
            failed["id"],
            passed["id"],
            "regenerated",
            "wrong",
        )


def test_real_evaluators_reuse_the_same_findings_and_show_missing_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(incremental, "implementation_fingerprint", lambda: "real-fixture")
    case = record(places={})
    legacy = audit.audit(tmp_path, records=[case], baseline={})
    first = audit.audit(tmp_path, records=[case], baseline={}, state_root=tmp_path / "state")
    second = audit.audit(tmp_path, records=[case], baseline={}, state_root=tmp_path / "state")
    assert first.findings == legacy.findings == second.findings
    assert second.evaluation["executed"] == 0 and second.evaluation["reused"] == 4
    assert second.evaluation["insufficient_evidence"] == 4


def test_cli_explicit_input_never_collects_other_sources(tmp_path, monkeypatch, capsys):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "audit_cli_test", root / "scripts/dev/trip_audit.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli, "REPORT_ROOT", tmp_path)
    monkeypatch.setattr(incremental, "implementation_fingerprint", lambda: "cli-fixture")

    def forbidden(*args, **kwargs):
        pytest.fail("Explicit input must not discover an emulator or private debug store")

    monkeypatch.setattr(audit, "collect", forbidden)
    path = tmp_path / "trip.json"
    path.write_text('{"destination":"Paris"}')
    args = ["--input", str(path), "--state-root", str(tmp_path / "state"), "--json"]
    assert cli.main(args) == 1
    capsys.readouterr()
    assert cli.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["evaluation"]["reused"] == 4
    assert all(not item["new"] for item in output["groups"])
    assert (tmp_path / "audit/latest.json").exists()


def test_receipt_checksum_rejects_tampered_pass(engine, tmp_path):
    run, _, _ = engine
    result = run().evaluation["results"][0]
    store = ResultStore(tmp_path / "state")
    payload = json.loads(store.path(result["id"]).read_text())
    payload["result"]["status"] = "pass"
    store.path(result["id"]).write_text(json.dumps(payload))
    assert store.read(result["id"]) is None
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_implementation_identity_tracks_code_and_settings_not_docs(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from tripplanner import config
    from tripplanner.harness import results

    module = tmp_path / "src/tripplanner/harness/results.py"
    module.parent.mkdir(parents=True)
    module.write_text("VERSION = 1\n")
    settings = {"pace": "relaxed"}
    monkeypatch.setattr(results, "__file__", str(module))
    monkeypatch.setattr(results, "distributions", lambda: [])
    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: SimpleNamespace(model_dump=lambda **_: settings),
    )
    first = results.implementation_fingerprint()
    (tmp_path / "README.md").write_text("Documentation only")
    assert results.implementation_fingerprint() == first
    module.write_text("VERSION = 2\n")
    second = results.implementation_fingerprint()
    assert second != first
    settings["pace"] = "fast"
    assert results.implementation_fingerprint() != second


def test_full_audit_after_exclusion_never_claims_the_missing_failure_resolved(engine, tmp_path):
    run, _, _ = engine
    first = audit_report.build_report(run(), {})
    lifecycle.set_state(
        tmp_path / "corpus/evaluation-lifecycle.json",
        record().artifact_id,
        "superseded",
        "New output exists",
        "a" * 64,
    )
    second = audit_report.build_report(run(selection="active"), {}, first)
    assert second["comparison"]["status"] == "not_comparable"
    assert second["comparison"]["resolved_groups"] == []
    assert second["retired"] == []


def test_selected_family_does_not_execute_other_evaluators(engine):
    run, calls, _ = engine
    result = run(evaluators=("render",))
    assert [name for name, _ in calls] == ["render"]
    assert result.evaluation["evaluators"] == ["render"]
    report = audit_report.build_report(result, {})
    assert all(item["evaluated"] == 0 for item in report["rules"] if item["code"] == "I9")


def test_unrelated_place_facts_do_not_claim_geographic_coverage():
    case = record(
        plan={
            "destination": "Paris",
            "day_wise_itinerary": [
                {"day": 1, "city": "Paris", "stops": [{"name": "Unknown park"}]}
            ],
        }
    )
    assert not suite.has_place_coverage(case)
