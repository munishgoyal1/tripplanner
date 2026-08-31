"""Pure evaluators that turn correlated harness evidence into report sections."""

from __future__ import annotations

from collections import Counter
from typing import Any

from tripplanner.validation.harness.evidence import HarnessEvent, HarnessEvidence
from tripplanner.validation.harness.pricing import (
    CATALOG_VERSION,
    GOOGLE_PLACES_USD_PER_REQUEST,
    azure_openai_rate,
)


def _events(evidence: HarnessEvidence, kind: str) -> list[HarnessEvent]:
    return [event for event in evidence.events if event.kind == kind]


def evaluate_cost(evidence: HarnessEvidence) -> dict[str, Any]:
    llm_calls = _events(evidence, "llm_call")
    google_calls = [
        event
        for event in _events(evidence, "outbound_http")
        if event.fields.get("provider") == "google"
    ]
    prompt_tokens = sum(int(event.fields.get("prompt_tokens") or 0) for event in llm_calls)
    completion_tokens = sum(int(event.fields.get("completion_tokens") or 0) for event in llm_calls)
    cached_tokens = sum(int(event.fields.get("cached_tokens") or 0) for event in llm_calls)

    azure_estimate = 0.0
    for event in llm_calls:
        fields = event.fields
        rate = azure_openai_rate(str(fields.get("model") or ""))
        prompt = int(fields.get("prompt_tokens") or 0)
        cached = min(prompt, int(fields.get("cached_tokens") or 0))
        uncached = prompt - cached
        cached_rate = rate.cached_input_per_million_usd or rate.input_per_million_usd
        azure_estimate += (
            uncached * rate.input_per_million_usd
            + cached * cached_rate
            + int(fields.get("completion_tokens") or 0) * rate.output_per_million_usd
        ) / 1_000_000

    google_counts = Counter(
        f"{event.fields.get('operation')}:{event.fields.get('sku_class')}"
        for event in google_calls
        if event.fields.get("status") == "ok"
    )
    google_estimate = sum(
        count * GOOGLE_PLACES_USD_PER_REQUEST.get(sku, 0.0)
        for sku, count in google_counts.items()
    )
    return {
        "measured": {
            "source": "runtime_provider_events",
            "llm_calls": len(llm_calls),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_prompt_tokens": cached_tokens,
            "google_requests": dict(sorted(google_counts.items())),
        },
        "estimated": {
            "source": "versioned_planning_catalog",
            "catalog_version": CATALOG_VERSION,
            "azure_openai_usd": round(azure_estimate, 6),
            "google_maps_platform_usd": round(google_estimate, 6),
            "total_usd": round(azure_estimate + google_estimate, 6),
            "authoritative": False,
        },
    }


def evaluate_cache(evidence: HarnessEvidence) -> dict[str, Any]:
    outcomes = Counter(
        str(event.fields.get("result") or "unknown")
        for event in _events(evidence, "cache_access")
    )
    hits = sum(outcomes[name] for name in ("memory_hit", "durable_hit", "coalesced_hit"))
    misses = outcomes["miss"] + outcomes["refresh"]
    attempts = hits + misses
    return {
        "source": "runtime_cache_events",
        "outcomes": dict(sorted(outcomes.items())),
        "hit_rate": round(hits / attempts, 4) if attempts else None,
    }


def evaluate_amplification(evidence: HarnessEvidence) -> dict[str, Any]:
    outbound = _events(evidence, "outbound_http")
    endpoints = Counter(str(event.fields.get("endpoint")) for event in outbound)
    action_ids = {
        str(event.fields["action_id"])
        for event in evidence.events
        if event.fields.get("action_id")
    }
    return {
        "source": "correlated_runtime_events",
        "outbound_requests": len(outbound),
        "actions": len(action_ids),
        "requests_per_action": round(len(outbound) / len(action_ids), 4) if action_ids else None,
        "by_endpoint": dict(sorted(endpoints.items())),
    }


def evaluate_performance(evidence: HarnessEvidence) -> dict[str, Any]:
    timed = [
        event for event in evidence.events if isinstance(event.fields.get("ms"), (int, float))
    ]
    durations = [float(event.fields["ms"]) for event in timed]
    durations.sort()
    by_kind: dict[str, dict[str, float | int]] = {}
    by_operation: dict[str, dict[str, float | int]] = {}
    for event in timed:
        duration = float(event.fields["ms"])
        kind = event.kind
        operation = f"{kind}:{event.fields.get('operation') or 'unspecified'}"
        for buckets, key in ((by_kind, kind), (by_operation, operation)):
            bucket = buckets.setdefault(key, {"count": 0, "sum_ms": 0.0})
            bucket["count"] = int(bucket["count"]) + 1
            bucket["sum_ms"] = round(float(bucket["sum_ms"]) + duration, 2)
    scenario_events = _events(evidence, "scenario_operation")
    scenario_ms = (
        float(scenario_events[-1].fields["ms"])
        if scenario_events and isinstance(scenario_events[-1].fields.get("ms"), (int, float))
        else None
    )
    return {
        "source": "runtime_event_durations",
        "timed_events": len(durations),
        "scenario_wall_ms": scenario_ms,
        "sum_event_ms": round(sum(durations), 2),
        "p95_ms": durations[max(0, int(len(durations) * 0.95) - 1)] if durations else None,
        "by_kind": dict(sorted(by_kind.items())),
        "by_operation": dict(sorted(by_operation.items())),
    }
