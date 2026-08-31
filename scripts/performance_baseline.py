from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

DEFAULT_SAMPLES = 30
DEFAULT_WARMUPS = 3
DEFAULT_P95_LIMIT_MS = 750.0
BENCHMARK_USER = "performance-baseline"


@dataclass(frozen=True)
class Scenario:
    name: str
    method: str
    path: str
    payload: dict[str, Any] | None = None


SCENARIOS = (
    Scenario("trip_view", "GET", "/trip/view"),
    Scenario("trip_map", "GET", "/trip/map"),
    Scenario("trip_itinerary", "GET", "/trip/itinerary"),
    Scenario(
        "stop_booked",
        "POST",
        "/trip/stop/booked",
        {"day": 1, "name": "Museum", "booked": True},
    ),
    Scenario(
        "chat_json",
        "POST",
        "/chat",
        {"message": "Plan a benchmark trip", "proposal_only": True},
    ),
    Scenario(
        "chat_sse",
        "POST",
        "/chat/stream",
        {"message": "Plan a benchmark trip", "proposal_only": True},
    ),
)


class PerformanceRegressionError(RuntimeError):
    pass


def percentile(values: list[float], percentage: float) -> float:
    if not values:
        raise ValueError("At least one measurement is required.")
    ordered = sorted(values)
    rank = max(1, (len(ordered) * percentage + 99) // 100)
    return ordered[min(int(rank), len(ordered)) - 1]


def _invoke(client: TestClient, scenario: Scenario) -> tuple[int, float]:
    started = time.perf_counter_ns()
    response = client.request(
        scenario.method,
        scenario.path,
        params={"user_id": BENCHMARK_USER} if scenario.method == "GET" else None,
        json={**(scenario.payload or {}), "user_id": BENCHMARK_USER}
        if scenario.method != "GET"
        else None,
    )
    duration_ms = (time.perf_counter_ns() - started) / 1_000_000
    return response.status_code, duration_ms


def measure_scenario(
    client: TestClient,
    scenario: Scenario,
    *,
    samples: int,
    warmups: int,
) -> dict[str, Any]:
    if samples < 1 or warmups < 0:
        raise ValueError("Samples must be positive and warmups cannot be negative.")
    for _ in range(warmups):
        status, _ = _invoke(client, scenario)
        if status >= 400:
            raise PerformanceRegressionError(
                f"{scenario.name} warmup returned HTTP {status}."
            )

    durations: list[float] = []
    errors = 0
    for _ in range(samples):
        status, duration_ms = _invoke(client, scenario)
        durations.append(duration_ms)
        errors += int(status >= 400)

    return {
        "samples": samples,
        "errors": errors,
        "error_rate": round(errors / samples, 4),
        "min_ms": round(min(durations), 3),
        "mean_ms": round(statistics.fmean(durations), 3),
        "p50_ms": round(percentile(durations, 50), 3),
        "p95_ms": round(percentile(durations, 95), 3),
        "max_ms": round(max(durations), 3),
    }


def run_baseline(
    client: TestClient,
    *,
    samples: int = DEFAULT_SAMPLES,
    warmups: int = DEFAULT_WARMUPS,
    p95_limit_ms: float = DEFAULT_P95_LIMIT_MS,
) -> dict[str, Any]:
    started = time.time()
    results = {
        scenario.name: measure_scenario(
            client, scenario, samples=samples, warmups=warmups
        )
        for scenario in SCENARIOS
    }
    failures = [
        name
        for name, result in results.items()
        if result["errors"] or result["p95_ms"] > p95_limit_ms
    ]
    report = {
        "status": "passed" if not failures else "failed",
        "measurement": "in_process_fastapi_contract",
        "samples_per_scenario": samples,
        "warmups_per_scenario": warmups,
        "p95_limit_ms": p95_limit_ms,
        "duration_seconds": round(time.time() - started, 3),
        "scenarios": results,
        "failed_scenarios": failures,
    }
    if failures:
        raise PerformanceRegressionError(
            f"Performance baseline failed for: {', '.join(failures)}"
        )
    return report


def run_hermetic_baseline(
    *,
    samples: int = DEFAULT_SAMPLES,
    warmups: int = DEFAULT_WARMUPS,
    p95_limit_ms: float = DEFAULT_P95_LIMIT_MS,
) -> dict[str, Any]:
    import asyncio

    from langchain_core.messages import AIMessage, AIMessageChunk

    from tripplanner import api, storage_cosmos, usage
    from tripplanner.graph import app_graph
    from tripplanner.request_limits import chat_admission

    view = {"overview": {"destination": "Benchmark City"}, "items": []}
    map_view = {"center": {"lat": 0.0, "lng": 0.0}, "pins": [], "days": []}
    itinerary = {"days": [], "stats": {"days": 0, "stops": 0}}
    benchmark_reply = "Benchmark itinerary ready."

    def fake_invoke(state: dict[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "messages": [*state["messages"], AIMessage(content=benchmark_reply)],
            "current_agent": "trip",
        }

    async def fake_stream(*_args: Any, **_kwargs: Any):
        for text in ("Benchmark itinerary ", "ready."):
            yield {
                "event": "on_chat_model_stream",
                "name": "benchmark-model",
                "run_id": "benchmark-run",
                "data": {"chunk": AIMessageChunk(content=text)},
            }

    async def reserve_conversation(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def acquire_permit(*_args: Any, **_kwargs: Any) -> object:
        return object()

    async def release_permit(*_args: Any, **_kwargs: Any) -> None:
        return None

    def save_chat(*_args: Any, **_kwargs: Any) -> str:
        return "benchmark-trip"

    with TemporaryDirectory(prefix="tripplanner-performance-") as home:
        previous_home = os.environ.get("tripplanner_HOME")
        os.environ["tripplanner_HOME"] = home
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(storage_cosmos, "is_enabled", lambda: False))
                stack.enter_context(
                    patch("tripplanner.web.trip_operations.build_view", return_value=view)
                )
                stack.enter_context(
                    patch("tripplanner.web.trip_operations.build_map", return_value=map_view)
                )
                stack.enter_context(
                    patch(
                        "tripplanner.web.trip_operations.build_itinerary",
                        return_value=itinerary,
                    )
                )
                stack.enter_context(
                    patch(
                        "tripplanner.web.trip_operations.set_stop_booked",
                        return_value={"ok": True, "itinerary": itinerary},
                    )
                )
                stack.enter_context(patch.object(app_graph, "invoke", fake_invoke))
                stack.enter_context(patch.object(app_graph, "astream_events", fake_stream))
                stack.enter_context(patch.object(api, "_completed_chat_request", lambda _: None))
                stack.enter_context(
                    patch.object(api, "_load_chat_request", lambda _: (None, [], None))
                )
                stack.enter_context(patch.object(api, "_save_chat", save_chat))
                stack.enter_context(
                    patch.object(api, "_reserve_conversation", reserve_conversation)
                )
                stack.enter_context(patch.object(api, "acquire_chat", acquire_permit))
                stack.enter_context(patch.object(api, "release_chat", release_permit))
                stack.enter_context(patch.object(api, "acquire_replay_access", acquire_permit))
                stack.enter_context(patch.object(api, "release_replay_access", release_permit))
                stack.enter_context(patch.object(api, "check_replay_lookup", release_permit))
                stack.enter_context(patch.object(usage, "is_over_cap", lambda _: (False, {})))
                usage_before = usage.get_usage(BENCHMARK_USER)
                asyncio.run(chat_admission.reset())
                try:
                    with TestClient(api.app) as client:
                        report = run_baseline(
                            client,
                            samples=samples,
                            warmups=warmups,
                            p95_limit_ms=p95_limit_ms,
                        )
                        json_payload = client.post(
                            "/chat",
                            json={
                                "user_id": BENCHMARK_USER,
                                "message": "Plan a benchmark trip",
                                "proposal_only": True,
                            },
                        ).json()
                        stream_text = client.post(
                            "/chat/stream",
                            json={
                                "user_id": BENCHMARK_USER,
                                "message": "Plan a benchmark trip",
                                "proposal_only": True,
                            },
                        ).text
                finally:
                    asyncio.run(chat_admission.reset())
                usage_after = usage.get_usage(BENCHMARK_USER)
        finally:
            if previous_home is None:
                os.environ.pop("tripplanner_HOME", None)
            else:
                os.environ["tripplanner_HOME"] = previous_home

    cost_delta = round(
        float(usage_after.get("cost_usd", 0.0))
        - float(usage_before.get("cost_usd", 0.0)),
        6,
    )
    call_delta = int(usage_after.get("calls", 0)) - int(usage_before.get("calls", 0))
    report["llm_usage"] = {"calls": call_delta, "cost_usd": cost_delta}
    done_payload = next(
        json.loads(line.removeprefix("data: "))
        for block in stream_text.split("\n\n")
        if block.startswith("event: done\n")
        for line in block.splitlines()
        if line.startswith("data: ")
    )
    parity_fields = ("reply", "agent", "trip_id")
    report["chat_transport_parity"] = {
        "matched": all(json_payload.get(key) == done_payload.get(key) for key in parity_fields),
        "fields": list(parity_fields),
    }
    if not report["chat_transport_parity"]["matched"]:
        raise PerformanceRegressionError("JSON and SSE chat terminal payloads diverged.")
    if call_delta or cost_delta:
        raise PerformanceRegressionError("Hermetic baseline incurred LLM usage.")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the hermetic tripplanner API performance and cost baseline."
    )
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--p95-limit-ms", type=float, default=DEFAULT_P95_LIMIT_MS)
    parser.add_argument("--report-path", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_hermetic_baseline(
        samples=args.samples,
        warmups=args.warmups,
        p95_limit_ms=args.p95_limit_ms,
    )
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report_path:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
