"""The validation harness, tested without an emulator or a provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tripplanner.validation import corpus, findings, runner
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
    result = runner.audit(tmp_path, records=[_record()], baseline={"accepted": {}})

    assert result.corpus_size == 1
    assert result.provenance_mix == {corpus.REAL: 1}
    assert any(item.rule == "I9" for item in result.new)
