from __future__ import annotations

from tripplanner.validation.harness import HarnessEvidence, build_report
from tripplanner.validation.harness.evidence import HarnessEvent


def test_report_separates_measurement_estimate_and_billing() -> None:
    evidence = HarnessEvidence(
        "run-1",
        "scenario-1",
        "local",
        events=[
            HarnessEvent(
                "llm_call",
                {
                    "model": "gpt-4.1-mini",
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 100_000,
                    "cached_tokens": 250_000,
                    "action_id": "one",
                    "ms": 200,
                },
            ),
            HarnessEvent(
                "outbound_http",
                {
                    "provider": "google",
                    "operation": "text_search",
                    "sku_class": "pro",
                    "status": "ok",
                    "endpoint": "places.googleapis.com",
                    "action_id": "one",
                    "ms": 50,
                },
            ),
            HarnessEvent("cache_access", {"result": "miss", "action_id": "one"}),
            HarnessEvent("cache_access", {"result": "memory_hit", "action_id": "two"}),
        ],
    )

    report = build_report(evidence, git_sha="abc123")

    assert report["version"] == 2
    assert report["run"]["git_sha"] == "abc123"
    assert report["model"] == {
        "source": "runtime_llm_events",
        "rounds": 1,
        "successful_rounds": 1,
        "errors": 0,
        "throttled_rounds": 0,
        "throttle_rate": 0.0,
        "retry_delay_ms": 0,
        "prompt_tokens": 1_000_000,
        "completion_tokens": 100_000,
    }
    assert report["cost"]["measured"]["prompt_tokens"] == 1_000_000
    assert report["cost"]["estimated"]["authoritative"] is False
    assert report["cost"]["billing_reconciliation"]["status"] == "not_available"
    assert report["cache"]["hit_rate"] == 0.5
    assert report["amplification"]["requests_per_action"] == 0.5
    assert report["quality"]["subjective_evaluation_costed_separately"] is True
