"""The validation harness, tested without an emulator or a provider."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tripplanner.validation import corpus, findings, mutations, render, runner
from tripplanner.validation.checks import check_record, plan_names
from tripplanner.validation.emulator import assert_sandbox_database

_PLACES = {
    "kempegowda international airport|paris": {"lat": 13.1986, "lng": 77.7066},
    "hotel lutetia|paris": {"lat": 48.8515, "lng": 2.3266},
}


def _plan(**extra: Any) -> dict[str, Any]:
    return {
        "trip_id": "paris_2026-09-06",
        "origin": "Bangalore",
        "destination": "Paris",
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Kempegowda International Airport", "kind": "transport",
                     "time": "05:00"},
                    {"name": "Hotel Lutetia", "kind": "hotel", "time": "23:59"},
                ],
            }
        ],
        **extra,
    }


def _record(**extra: Any) -> corpus.CorpusRecord:
    return corpus.CorpusRecord(
        id="test:1", provenance=corpus.REAL, source="test", plan=_plan(**extra), places=_PLACES
    )


# ---- corpus ---------------------------------------------------------------


def test_a_trip_seen_from_two_sources_is_counted_once() -> None:
    same = [_record(), _record()]
    assert len(corpus.deduplicate(same)) == 1


def test_provenance_is_tallied_for_the_report() -> None:
    records = [
        _record(),
        corpus.CorpusRecord(id="b", provenance=corpus.GOLDEN, source="s", plan=_plan()),
    ]
    assert corpus.counts_by_provenance(records) == {corpus.REAL: 1, corpus.GOLDEN: 1}


def test_debug_store_records_contribute_their_intermediate_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan is usually right when finished and wrong somewhere in the middle."""
    users = tmp_path / "users" / "owner"
    users.mkdir(parents=True)
    (users / "0001__paris.json").write_text(
        json.dumps(
            {
                "archive_no": 1,
                "trip_id": "paris",
                "revisions": [
                    {"plan": _plan(status="draft")},
                    {"plan": _plan(status="final")},
                ],
                "bundle": {"places": _PLACES},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRIPPLANNER_DEBUG_STORE_DIR", str(tmp_path))

    every = corpus.from_debug_store(tmp_path / "users")
    assert [item.provenance for item in every] == [corpus.REVISION, corpus.REAL]
    assert len(corpus.from_debug_store(tmp_path / "users", revisions=False)) == 1


# ---- isolation ------------------------------------------------------------


@pytest.mark.parametrize("name", ["tripplanner-prod", "tripplanner-canary", "tripplanner-local"])
def test_the_audit_cannot_read_a_database_that_is_not_a_sandbox(name: str) -> None:
    with pytest.raises(ValueError):
        assert_sandbox_database(name)


# ---- checks ---------------------------------------------------------------


def test_a_stay_in_another_city_is_reported_without_a_provider() -> None:
    """AC-05 in miniature: the known Paris shape, found from stored facts alone."""
    reported = check_record(_record())

    assert any(finding.rule == "I9" for finding in reported)


def test_a_gap_that_only_repeats_a_violation_is_not_reported_twice() -> None:
    reported = check_record(_record())
    messages = {finding.message for finding in reported if finding.rule == "gap"}

    assert not any("Itinerary is not coherent" in message for message in messages)


def test_plan_names_gathers_every_proper_noun_the_symptom_must_lose() -> None:
    names = plan_names(_plan())

    assert "Paris" in names
    assert "Hotel Lutetia" in names


# ---- findings -------------------------------------------------------------


def test_the_same_shape_from_different_trips_is_one_group() -> None:
    names = ["Mandu Fort", "Rajwada Palace"]
    first = findings.Finding(
        "I9", findings.symptom_of("Mandu Fort is far from X on Day 3.", names),
        "m", "trip-a", corpus.REAL,
    )
    second = findings.Finding(
        "I9", findings.symptom_of("Rajwada Palace is far from X on Day 7.", names),
        "m", "trip-b", corpus.REAL,
    )

    grouped = findings.group([first, second])
    assert len(grouped) == 1
    assert grouped[0].count == 2


def test_only_findings_absent_from_the_baseline_are_new() -> None:
    finding = findings.Finding("I9", "shape", "message", "trip", corpus.REAL)
    grouped = findings.group([finding])

    assert findings.new_groups(grouped, {"accepted": {}}) == grouped
    assert findings.new_groups(grouped, findings.accept(grouped, {"accepted": {}})) == []


def test_accepting_twice_keeps_the_original_acceptance_date() -> None:
    grouped = findings.group([findings.Finding("I9", "shape", "message", "t", corpus.REAL)])
    first = findings.accept(grouped, {"accepted": {}})
    first["accepted"]["I9|shape"]["accepted_on"] = "2020-01-01"

    again = findings.accept(grouped, first)
    assert again["accepted"]["I9|shape"]["accepted_on"] == "2020-01-01"


def test_an_accepted_finding_that_stopped_occurring_is_offered_for_pruning() -> None:
    baseline = {"accepted": {"I9|gone": {}, "I4|still-here": {}}}
    grouped = findings.group([findings.Finding("I4", "still-here", "m", "t", corpus.REAL)])

    assert findings.stale_keys(grouped, baseline) == ["I9|gone"]


def test_a_saved_baseline_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "audit-baseline.json"
    grouped = findings.group([findings.Finding("I9", "shape", "message", "t", corpus.REAL)])
    findings.save_baseline(path, findings.accept(grouped, {"accepted": {}}))

    assert findings.new_groups(grouped, findings.load_baseline(path)) == []


# ---- runner ---------------------------------------------------------------


def test_the_audit_reports_the_corpus_it_actually_read(tmp_path: Path) -> None:
    result = runner.audit(
        tmp_path, records=[_record()], baseline={"accepted": {}}, render=False, mutate=False
    )

    assert result.corpus_size == 1
    assert result.provenance_mix == {corpus.REAL: 1}
    assert any(item.rule == "I9" for item in result.new)


# ---- render ---------------------------------------------------------------


def test_a_leg_drawn_as_ground_travel_across_a_continent_is_reported() -> None:
    """The reported defect: a taxi from Bengaluru to a Paris hotel."""
    return_day = _plan()
    return_day["day_wise_itinerary"] = [
        {
            "day": 1,
            "stops": [
                {"name": "Charles de Gaulle Airport", "kind": "transport", "time": "09:55"},
                {"name": "Kempegowda International Airport", "kind": "transport",
                 "time": "23:20"},
                {"name": "Hotel Lutetia", "kind": "hotel", "time": "23:59"},
            ],
        }
    ]
    record = corpus.CorpusRecord(
        id="return-day",
        provenance=corpus.REAL,
        source="test",
        plan=return_day,
        places={**_PLACES, "charles de gaulle airport|paris": {"lat": 49.0097, "lng": 2.5479}},
    )

    reported = render.check_render(record)

    assert any(finding.rule == render.RULE_GROUND_LEG for finding in reported)
    assert any(finding.rule == render.RULE_LEG_DURATION for finding in reported)


def test_render_checks_stay_silent_without_the_facts_to_measure_with() -> None:
    blind = corpus.CorpusRecord(id="x", provenance=corpus.REAL, source="s", plan=_plan())

    assert render.check_render(blind) == []


def test_a_stop_missing_from_the_stored_facts_is_not_called_unmapped() -> None:
    """The audit's own blind spot must not be reported as the product's defect."""
    view = {"unmapped_stops": [{"name": "Somewhere Uncached", "day": 1, "reason": "no_location"}]}

    assert render._unmapped_findings(_record(), view, []) == []


def test_a_place_the_provider_swapped_for_another_is_reported() -> None:
    view = {"unmapped_stops": [{"name": "Seine River Cruise", "day": 2, "reason": "no_match"}]}

    reported = render._unmapped_findings(_record(), view, [])
    assert [finding.rule for finding in reported] == [render.RULE_UNMAPPED]


# ---- metamorphic ----------------------------------------------------------


def test_every_mutation_is_offered_in_a_fixed_order() -> None:
    plan = _plan()

    assert [item.name for item in mutations.mutations_of(plan)] == [
        item.name for item in mutations.mutations_of(plan)
    ]


def test_a_mutation_never_edits_the_plan_it_was_given() -> None:
    plan = _plan()
    before = json.dumps(plan, sort_keys=True)

    mutations.mutations_of(plan)
    assert json.dumps(plan, sort_keys=True) == before


def test_blanking_an_origin_that_is_already_missing_is_not_a_mutation() -> None:
    assert mutations.blank_origin(_plan(origin="")) is None


def test_an_edit_that_changes_nothing_must_change_no_finding() -> None:
    record = _record()
    for mutation in mutations.mutations_of(record.plan):
        if mutation.kind != mutations.NEUTRAL:
            continue
        mutated = dataclasses.replace(record, plan=mutation.plan)
        assert {f.key for f in check_record(mutated)} == {f.key for f in check_record(record)}


def test_a_guard_that_stops_running_is_caught_by_the_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-07: silence the origin guards and losing the origin goes unnoticed.

    Two rules cover a missing origin today, so both have to go before the hole
    opens -- which is itself the evidence that the coverage is real.
    """
    from tripplanner.tools import trip_guard, trip_validation

    record = _record()
    assert not [
        finding
        for finding in mutations.check_metamorphic(record)
        if finding.rule == mutations.RULE_UNNOTICED
    ]

    monkeypatch.setattr(trip_guard, "_coverage_violations", lambda plan: [])
    monkeypatch.setattr(trip_validation, "_round_trip_transport_warnings", lambda plan: [])

    blinded = mutations.check_metamorphic(record)
    assert [f.rule for f in blinded if "blank-origin" in f.message] == [
        mutations.RULE_UNNOTICED
    ]

