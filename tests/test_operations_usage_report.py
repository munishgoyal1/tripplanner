from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from tripplanner import operations_usage_report as reports


@pytest.fixture
def local_report(monkeypatch, tmp_path):
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setattr(reports, "_ENTRIES", {})
    monkeypatch.setattr(
        reports,
        "get_settings",
        lambda: SimpleNamespace(
            cosmos_emulator=True,
            cosmos_endpoint="https://localhost:8081",
            cosmos_database="test",
        ),
    )
    return tmp_path


def _wait_finished():
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with reports._LOCK:
            if not any(entry.get("running") for entry in reports._ENTRIES.values()):
                return
        time.sleep(0.01)
    pytest.fail("report worker did not finish")


def test_first_report_does_not_block_or_invent_zero_totals(local_report, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def build(**kwargs):
        calls.append(kwargs)
        entered.set()
        assert release.wait(3)
        return {
            "totals": {"calls": 123},
            "by_trip": [{"trip_id": "goa", "interaction_kind": "new_trip"}],
        }

    monkeypatch.setattr(reports, "summary", build)
    try:
        start = time.monotonic()
        report, status = reports.get_report(days=30, trip_names={"goa": "Goa"})
        assert time.monotonic() - start < 0.25
        assert report is None
        assert status["state"] == "pending"
        assert entered.wait(1)
        for _ in range(5):
            reports.get_report(days=30, trip_names={"goa": "Other name"})
        assert len(calls) == 1
    finally:
        release.set()
        _wait_finished()
    report, status = reports.get_report(days=30, trip_names={"goa": "Goa"})
    assert status["state"] == "ready"
    assert report["totals"]["calls"] == 123
    assert report["by_trip"][0]["trip_name"] == "Goa"
    assert "trip_names" not in calls[0]
    assert calls[0]["strict"] is True


def test_restart_serves_saved_report_and_expiry_never_waits(local_report, monkeypatch):
    path = reports._path({"days": 30})
    reports._save(path, {"totals": {"calls": 123}}, time.time() - 120)
    entered, release = threading.Event(), threading.Event()

    def build(**kwargs):
        entered.set()
        assert release.wait(3)
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(reports, "summary", build)
    try:
        start = time.monotonic()
        report, status = reports.get_report(days=30)
        assert time.monotonic() - start < 0.25
        assert report["totals"]["calls"] == 123
        assert status["state"] == "refreshing"
        assert status["generated_at"] is not None
        assert entered.wait(1)
    finally:
        release.set()
        _wait_finished()
    report, status = reports.get_report(days=30)
    assert report["totals"]["calls"] == 123
    assert status["state"] == "error"
    assert reports._read_saved(path)["report"]["totals"]["calls"] == 123


def test_saved_reports_are_isolated_by_database_and_range(local_report, monkeypatch):
    path = reports._path({"days": 30})
    assert reports._path({"days": 7}) != path
    monkeypatch.setattr(
        reports,
        "get_settings",
        lambda: SimpleNamespace(
            cosmos_emulator=True,
            cosmos_endpoint="https://localhost:8081",
            cosmos_database="other",
        ),
    )
    assert reports._path({"days": 30}) != path


def test_corrupt_saved_report_is_not_used(local_report):
    path = reports._path({"days": 30})
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    assert reports._read_saved(path)["report"] is None


def test_base_overview_survives_restart_and_stale_refresh(local_report, monkeypatch):
    identity = {"user_id": "owner", "days": 30}
    path = reports._path({"section": "overview-base", **identity})
    reports._save(path, {"business": {"trips": 6}}, time.time() - 120)
    entered, release = threading.Event(), threading.Event()

    def build():
        entered.set()
        assert release.wait(3)
        return {"business": {"trips": 7}}

    try:
        start = time.monotonic()
        result = reports.get_base(build, **identity)
        assert time.monotonic() - start < 0.25
        assert result["business"]["trips"] == 6
        assert result["overview_status"]["state"] == "refreshing"
        assert entered.wait(1)
    finally:
        release.set()
        _wait_finished()
    reports._ENTRIES.clear()
    result = reports.get_base(lambda: pytest.fail("restart must not query history"), **identity)
    assert result["business"]["trips"] == 7
    assert result["overview_status"]["state"] == "ready"


def test_compact_dashboard_keeps_global_totals_and_visible_trip_drilldowns():
    trip = {"interaction_kind": "new_trip", "calls": 3}
    background = {"interaction_kind": "other", "calls": 100}
    report = {"totals": {"calls": 103}, "by_provider_total": [{"calls": 103}]}
    for field in ("by_trip", "by_provider", "by_operation", "by_interaction"):
        report[field] = [trip, background]
    compact = reports._compact_usage(report)
    assert compact["totals"]["calls"] == 103
    assert compact["by_provider_total"] == [{"calls": 103}]
    assert compact["by_operation"] == [trip]
    assert report["by_operation"] == [trip, background]


def test_hosted_report_is_ready_with_a_real_timestamp(monkeypatch):
    monkeypatch.setattr(reports, "get_settings", lambda: SimpleNamespace(cosmos_emulator=False))
    monkeypatch.setattr(reports, "summary", lambda **kwargs: {"totals": {"calls": 1}})
    report, status = reports.get_report(days=30)
    assert report["totals"]["calls"] == 1
    assert status["state"] == "ready"
    assert status["generated_at"] is not None
