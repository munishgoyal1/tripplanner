"""Behaviour of the INR spend ceiling and the per-trip cost ledger."""

from __future__ import annotations

import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from tripplanner import cost_ledger, cost_model


@pytest.fixture(autouse=True)
def ledger_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    monkeypatch.setenv("COST_CEILING_ENFORCED", "1")
    monkeypatch.setenv("COST_CEILING_DENY_ON_LEDGER_ERROR", "0")
    monkeypatch.setattr(cost_ledger.storage_cosmos, "is_enabled", lambda: False)
    cost_model.reset_cache_for_tests()
    yield
    cost_model.reset_cache_for_tests()


NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def google_call(cost_usd: float | None, *, operation: str = "text_search") -> dict:
    return {
        "provider": "google",
        "operation": operation,
        "sku_class": "pro",
        "billable": True,
        "units": 1,
        "estimated_cost_usd": cost_usd,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


def llm_call(cost_usd: float, *, prompt: int = 1000, completion: int = 200) -> dict:
    return {
        "provider": "azure_openai",
        "operation": "chat_completion",
        "sku_class": "gpt-5.4-mini",
        "billable": True,
        "units": 1,
        "estimated_cost_usd": cost_usd,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
    }


def attribution(interaction_id: str, *, trip_id: str = "trip-1", kind: str = "new_trip") -> dict:
    return {
        "interaction_id": interaction_id,
        "trip_id": trip_id,
        "interaction_kind": kind,
        "environment": "local",
    }


def test_usd_records_are_converted_to_inr_exactly_once():
    """A USD provider estimate must land in the ledger multiplied by the FX rate.

    If USD ever reached a ceiling uncoverted the effective budget would be ~88x
    what the owner set, so this asserts the rate rather than merely "non-zero".
    """
    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cost_ledger.settle(attribution("i1"), [google_call(1.0)], now=NOW)

    spent = cost_ledger.snapshot(now=NOW)["windows"]["daily"]["spent_inr"]
    assert spent == pytest.approx(88.0)


def test_settle_advances_every_window():
    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cost_ledger.settle(attribution("i1"), [google_call(0.5)], now=NOW)

    windows = cost_ledger.snapshot(now=NOW)["windows"]
    for window in ("daily", "weekly", "monthly"):
        assert windows[window]["spent_inr"] == pytest.approx(44.0)


def test_ceiling_breach_refuses_the_turn(monkeypatch):
    monkeypatch.setenv("COST_CEILING_INR_DAILY", "100")

    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cost_ledger.settle(attribution("i1"), [google_call(1.0)], now=NOW)

    with pytest.raises(cost_ledger.CostCeilingError) as excinfo:
        cost_ledger.reserve("new_trip", interaction_id="i2", now=NOW)
    assert excinfo.value.window == "daily"
    assert excinfo.value.ceiling_inr == 100.0
    assert excinfo.value.resets_at.startswith("2026-09-12")


def test_concurrent_reservations_are_counted_before_any_settles(monkeypatch):
    """The property that makes the ceiling actually stop.

    Without reserve-then-reconcile every concurrent turn reads the same "spent
    so far" of zero and all of them pass a check none would pass individually.
    """
    monkeypatch.setenv("COST_CEILING_INR_DAILY", "150")

    assert cost_ledger.reserve("new_trip", interaction_id="a", now=NOW) is not None
    assert cost_ledger.reserve("new_trip", interaction_id="b", now=NOW) is not None
    # Two seeded holds of INR 60 leave 30 -- not enough for a third.
    with pytest.raises(cost_ledger.CostCeilingError):
        cost_ledger.reserve("new_trip", interaction_id="c", now=NOW)


def test_releasing_a_hold_returns_headroom(monkeypatch):
    monkeypatch.setenv("COST_CEILING_INR_DAILY", "150")

    cost_ledger.reserve("new_trip", interaction_id="a", now=NOW)
    cost_ledger.reserve("new_trip", interaction_id="b", now=NOW)
    cost_ledger.release("b", now=NOW)

    assert cost_ledger.reserve("new_trip", interaction_id="c", now=NOW) is not None


def test_retry_of_same_interaction_replaces_its_own_hold(monkeypatch):
    monkeypatch.setenv("COST_CEILING_INR_DAILY", "130")

    cost_ledger.reserve("new_trip", interaction_id="same", now=NOW)
    # A retried request must not stack a second hold on top of its own.
    cost_ledger.reserve("new_trip", interaction_id="same", now=NOW)
    assert cost_ledger.snapshot(now=NOW)["pending_inr"] == pytest.approx(60.0)


def test_unknown_cost_calls_are_never_free():
    """A billable call with no price estimate must not contribute zero."""
    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cost_ledger.settle(attribution("i1"), [google_call(None), google_call(None)], now=NOW)

    spent = cost_ledger.snapshot(now=NOW)["windows"]["daily"]["spent_inr"]
    seed = cost_model.reservation_settings()["seedUnknownInr"]["new_trip"]
    assert spent == pytest.approx(seed)


def test_settling_twice_for_one_interaction_charges_once():
    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cost_ledger.settle(attribution("i1"), [google_call(0.5)], now=NOW)
    cost_ledger.settle(attribution("i1"), [google_call(0.5)], now=NOW)

    assert cost_ledger.snapshot(now=NOW)["windows"]["daily"]["spent_inr"] == pytest.approx(44.0)


def test_observe_mode_records_without_refusing(monkeypatch):
    monkeypatch.setenv("COST_CEILING_INR_DAILY", "10")
    monkeypatch.setenv("COST_CEILING_ENFORCED", "0")

    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cost_ledger.settle(attribution("i1"), [google_call(1.0)], now=NOW)

    # Over the ceiling, but admission still returns rather than raising.
    assert cost_ledger.reserve("new_trip", interaction_id="i2", now=NOW) is None
    snapshot = cost_ledger.snapshot(now=NOW)
    assert snapshot["enforced"] is False
    assert snapshot["windows"]["daily"]["spent_inr"] == pytest.approx(88.0)


def test_trip_document_breaks_down_providers_llm_and_turns():
    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cost_ledger.settle(
        attribution("i1"),
        [
            google_call(0.032, operation="text_search"),
            google_call(0.007, operation="photo_media"),
            google_call(0.007, operation="photo_media"),
            llm_call(0.10, prompt=5000, completion=700),
        ],
        now=NOW,
    )
    cost_ledger.reserve("trip_update", interaction_id="i2", now=NOW)
    cost_ledger.settle(
        attribution("i2", kind="trip_update"),
        [google_call(0.007, operation="photo_media")],
        now=NOW,
    )

    trips = cost_ledger.recent_trips(20, {"trip-1": "Goa"})
    assert len(trips) == 1
    trip = trips[0]
    assert trip["destination"] == "Goa"
    assert trip["turns"] == {"new_trip": 1, "trip_update": 1}
    assert trip["llm"]["calls"] == 1
    assert trip["llm"]["prompt_tokens"] == 5000
    assert trip["providers"]["google"]["calls"] == 4
    assert trip["providers"]["google"]["by_operation"] == {"text_search": 1, "photo_media": 3}
    assert trip["totals"]["cost_inr"] == pytest.approx((0.032 + 0.007 * 3 + 0.10) * 88.0)
    assert "INR" in trip["summary"] and "2 turns" in trip["summary"]


def test_aggregate_reports_cumulative_and_average():
    for index, cost in enumerate([0.1, 0.2, 0.3]):
        interaction = f"i{index}"
        cost_ledger.reserve("new_trip", interaction_id=interaction, now=NOW)
        cost_ledger.settle(
            attribution(interaction, trip_id=f"trip-{index}"), [google_call(cost)], now=NOW
        )

    result = cost_ledger.aggregate()
    assert result["currency"] == "INR"
    assert result["trips"] == 3
    assert result["cumulative_inr"] == pytest.approx(0.6 * 88.0)
    assert result["average_per_trip_inr"] == pytest.approx(0.2 * 88.0)


def test_anomalous_trip_is_flagged_against_the_rolling_median():
    for index in range(6):
        interaction = f"normal{index}"
        cost_ledger.reserve("new_trip", interaction_id=interaction, now=NOW)
        cost_ledger.settle(
            attribution(interaction, trip_id=f"trip-{index}"), [google_call(0.5)], now=NOW
        )

    cost_ledger.reserve("new_trip", interaction_id="runaway", now=NOW)
    cost_ledger.settle(
        attribution("runaway", trip_id="trip-runaway"), [google_call(5.0)], now=NOW
    )

    flagged = [
        trip for trip in cost_ledger.recent_trips(20) if (trip.get("anomaly") or {}).get("flagged")
    ]
    assert [trip["trip_id"] for trip in flagged] == ["trip-runaway"]
    assert flagged[0]["anomaly"]["ratio_to_median"] == pytest.approx(10.0)


def test_non_planning_work_counts_against_the_ceiling_but_not_the_estimates():
    """A destination guide spends real money, so it must charge the ceiling.

    It must not shape what a planning turn is predicted to cost, though --
    usage_scope wraps guides, corpus runs and CLI work as well as chat.
    """
    cost_ledger.settle(
        attribution("guide-1", trip_id="", kind="destination_guide"),
        [google_call(0.25)],
        now=NOW,
    )

    assert cost_ledger.snapshot(now=NOW)["windows"]["daily"]["spent_inr"] == pytest.approx(22.0)
    # Seed value unchanged: the guide contributed no sample.
    assert cost_ledger.estimate_reserve_inr(
        "trip_update", cost_ledger._read_windows_body()
    ) == pytest.approx(20.0)


def test_cache_hits_add_savings_not_spend():
    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cost_ledger.settle(
        attribution("i1"),
        [
            {
                "provider": "google",
                "operation": "text_search",
                "event_type": "cache_hit",
                "billable": False,
                "units": 4,
                "estimated_savings_usd": 0.128,
                "estimated_cost_usd": None,
            }
        ],
        now=NOW,
    )

    assert cost_ledger.snapshot(now=NOW)["windows"]["daily"]["spent_inr"] == pytest.approx(0.0)
    trip = cost_ledger.recent_trips(1)[0]
    assert trip["totals"]["cache_hits"] == 4
    assert trip["totals"]["savings_inr"] == pytest.approx(0.128 * 88.0)


# --- Cosmos contention -------------------------------------------------------


class FakeCosmos:
    """Documents keyed by (container, partition, id) with versions, like Cosmos.

    ``write_delay`` holds each conditional write open long enough for concurrent
    turns to interleave, which is when read-modify-write loses without a version
    check and conflicts without batching.
    """

    def __init__(self, write_delay: float = 0.0) -> None:
        self.docs: dict[tuple[str, str, str], tuple[dict, int]] = {}
        self.lock = threading.Lock()
        self.write_delay = write_delay
        self.reads: list[tuple[str, str, str]] = []
        self.writes: list[tuple[str, str, str]] = []
        self.conflicts = 0

    def install(self, monkeypatch) -> None:
        storage = cost_ledger.storage_cosmos
        monkeypatch.setattr(storage, "is_enabled", lambda: True)
        for name in (
            "read_doc",
            "read_doc_versioned",
            "create_doc_if_absent",
            "replace_doc_if_version",
            "upsert_doc",
            "delete_doc",
            "operations_query",
        ):
            monkeypatch.setattr(storage, name, getattr(self, name))

    def read_doc(self, container, partition, doc_id):
        with self.lock:
            self.reads.append((container, partition, doc_id))
            found = self.docs.get((container, partition, doc_id))
            return copy.deepcopy(found[0]) if found else None

    def read_doc_versioned(self, container, partition, doc_id):
        with self.lock:
            self.reads.append((container, partition, doc_id))
            found = self.docs.get((container, partition, doc_id))
            if not found:
                return None
            return cost_ledger.storage_cosmos.VersionedDocument(
                body=copy.deepcopy(found[0]), version=str(found[1])
            )

    def create_doc_if_absent(self, container, partition, doc_id, body):
        time.sleep(self.write_delay)
        with self.lock:
            key = (container, partition, doc_id)
            if key in self.docs:
                self.conflicts += 1
                raise cost_ledger.storage_cosmos.WriteConflictError("created")
            self.writes.append(key)
            self.docs[key] = (copy.deepcopy(body), 1)

    def replace_doc_if_version(self, container, partition, doc_id, body, version):
        time.sleep(self.write_delay)
        with self.lock:
            key = (container, partition, doc_id)
            current = self.docs.get(key)
            if current is None or str(current[1]) != version:
                self.conflicts += 1
                raise cost_ledger.storage_cosmos.WriteConflictError("changed")
            self.writes.append(key)
            self.docs[key] = (copy.deepcopy(body), current[1] + 1)

    def upsert_doc(self, container, partition, doc_id, body):
        with self.lock:
            key = (container, partition, doc_id)
            self.writes.append(key)
            previous = self.docs.get(key)
            self.docs[key] = (copy.deepcopy(body), (previous[1] + 1) if previous else 1)

    def delete_doc(self, container, partition, doc_id):
        with self.lock:
            self.docs.pop((container, partition, doc_id), None)

    def operations_query(self, container, query, parameters):
        values = {parameter["name"]: parameter["value"] for parameter in parameters}
        with self.lock:
            return [
                {**copy.deepcopy(body), "id": doc_id, "user_id": partition}
                for (stored, partition, doc_id), (body, _version) in self.docs.items()
                if stored == container
                and doc_id.startswith(values["@prefix"])
                and partition == values["@env"]
            ]


def _concurrently(count: int, action) -> list:
    barrier = threading.Barrier(count)

    def run(index: int):
        barrier.wait()
        try:
            return action(index)
        except Exception as exc:  # noqa: BLE001 - the outcome is what is asserted
            return exc

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(run, range(count)))


def test_concurrent_reservations_admit_exactly_what_the_ceiling_allows(monkeypatch):
    """Group commit must keep the invariant: no turn is checked against state
    that ignores a concurrent turn. Twelve turns race for room for five."""
    monkeypatch.setenv("COST_CEILING_INR_DAILY", "300")  # five INR 60 seeded holds
    cosmos = FakeCosmos(write_delay=0.01)
    cosmos.install(monkeypatch)

    outcomes = _concurrently(
        12, lambda index: cost_ledger.reserve("new_trip", interaction_id=f"turn-{index}", now=NOW)
    )

    admitted = [outcome for outcome in outcomes if isinstance(outcome, cost_ledger.Reservation)]
    denied = [outcome for outcome in outcomes if isinstance(outcome, cost_ledger.CostCeilingError)]
    assert len(admitted) == 5
    assert len(denied) == 7
    assert cost_ledger.snapshot(now=NOW)["pending_inr"] == pytest.approx(300.0)
    # Collisions inside one process are batched away rather than retried.
    assert cosmos.conflicts == 0
    assert len(cosmos.writes) < len(admitted)


def test_concurrent_settlements_lose_no_spend_and_raise_no_ledger_error(monkeypatch):
    """Under COST_CEILING_DENY_ON_LEDGER_ERROR=1, five exhausted retries denied a turn."""
    monkeypatch.setenv("COST_CEILING_DENY_ON_LEDGER_ERROR", "1")
    cosmos = FakeCosmos(write_delay=0.005)
    cosmos.install(monkeypatch)
    turns = 16
    for index in range(turns):
        cost_ledger.reserve("trip_update", interaction_id=f"turn-{index}", now=NOW)

    _concurrently(
        turns,
        lambda index: cost_ledger.settle(
            attribution(f"turn-{index}", trip_id=f"trip-{index}", kind="trip_update"),
            [google_call(0.25)],
            now=NOW,
        ),
    )

    snapshot = cost_ledger.snapshot(now=NOW)
    assert snapshot["windows"]["daily"]["spent_inr"] == pytest.approx(turns * 0.25 * 88.0)
    assert snapshot["pending_inr"] == pytest.approx(0.0)
    assert cosmos.conflicts == 0


def test_a_write_from_another_process_is_reread_not_overwritten(monkeypatch):
    """The version check still guards against writers outside this process."""
    cosmos = FakeCosmos()
    cosmos.install(monkeypatch)
    cost_ledger.reserve("new_trip", interaction_id="first", now=NOW)
    replace = cosmos.replace_doc_if_version
    interfered = {"done": False}

    def replace_after_another_process_reserves(container, partition, doc_id, body, version):
        if not interfered["done"]:
            interfered["done"] = True
            current, stored_version = cosmos.docs[(container, partition, doc_id)]
            other = cost_ledger._with_reservation(
                current, category="new_trip", reservation_id="other-process", now=NOW
            )[0]
            cosmos.docs[(container, partition, doc_id)] = (other, stored_version + 1)
        return replace(container, partition, doc_id, body, version)

    monkeypatch.setattr(
        cost_ledger.storage_cosmos, "replace_doc_if_version", replace_after_another_process_reserves
    )
    monkeypatch.setattr(cost_ledger.time, "sleep", lambda _seconds: None)

    cost_ledger.reserve("new_trip", interaction_id="second", now=NOW)

    assert cosmos.conflicts == 1
    assert cost_ledger.snapshot(now=NOW)["pending_inr"] == pytest.approx(180.0)


def test_a_document_that_never_settles_is_reported_unavailable(monkeypatch):
    cosmos = FakeCosmos()
    cosmos.install(monkeypatch)
    monkeypatch.setenv("COST_CEILING_DENY_ON_LEDGER_ERROR", "1")
    cost_ledger.reserve("new_trip", interaction_id="first", now=NOW)

    def always_conflict(*_args):
        raise cost_ledger.storage_cosmos.WriteConflictError("changed")

    monkeypatch.setattr(cost_ledger.storage_cosmos, "replace_doc_if_version", always_conflict)
    monkeypatch.setattr(cost_ledger.time, "sleep", lambda _seconds: None)

    with pytest.raises(cost_ledger.LedgerUnavailableError):
        cost_ledger.reserve("new_trip", interaction_id="second", now=NOW)


def test_settlement_idempotency_survives_the_switch_to_markers():
    """Ids stored in full before digests were introduced must still stop a double charge."""
    body = cost_ledger._empty_windows()
    body["settled_interactions"] = ["legacy-full-interaction-id"]

    replay = cost_ledger._with_settlement(
        body,
        reservation_id="legacy-full-interaction-id",
        interaction_id="legacy-full-interaction-id",
        category="new_trip",
        is_trip=True,
        now=NOW,
        records=[google_call(1.0)],
    )
    fresh = cost_ledger._with_settlement(
        body,
        reservation_id="new-id",
        interaction_id="new-id",
        category="new_trip",
        is_trip=True,
        now=NOW,
        records=[google_call(1.0)],
    )

    assert replay is None
    assert fresh is not None
    assert fresh[0]["settled_interactions"][-1] == cost_ledger._settled_marker("new-id")
    assert "new-id" not in fresh[0]["settled_interactions"]


def test_settle_reads_the_window_document_once(monkeypatch):
    """The anomaly check reuses the settled document instead of reading it back."""
    cosmos = FakeCosmos()
    cosmos.install(monkeypatch)
    cost_ledger.reserve("new_trip", interaction_id="i1", now=NOW)
    cosmos.reads.clear()

    cost_ledger.settle(attribution("i1"), [google_call(1.0)], now=NOW)

    environment = cost_ledger._environment()
    assert ("trip_costs", environment, "trip_trip-1") in cosmos.docs
    window_reads = [read for read in cosmos.reads if read[2] == "_windows_v1"]
    assert len(window_reads) == 1
    assert cost_ledger.recent_trips(5)[0]["totals"]["cost_inr"] == pytest.approx(88.0)
