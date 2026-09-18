"""The derived guardrails stay in line with the INR ceilings, and units never mix.

Two separate concerns live here:

* **Derivation** -- ``infra/billing-guardrails.json`` quota rows are computed
  from ``config/cost-model.json`` plus the ceilings in the environment profiles.
  Asserting they match means the cloud net cannot drift from the budget it
  protects, and retuning the budget cannot silently leave the quotas behind.
* **Unit discipline** -- every ceiling is INR; provider catalogs are USD. A USD
  figure reaching a ceiling uncoverted would raise the real budget by the FX
  rate (~88x), so the boundary is asserted rather than trusted to review.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tripplanner import cost_model, limits_config

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ("local", "canary", "prod")


def _derive_module():
    spec = importlib.util.spec_from_file_location(
        "derive_limits", ROOT / "scripts" / "derive_limits.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _profile(environment: str) -> str:
    return (ROOT / "config" / "environments" / f"{environment}.env").read_text(encoding="utf-8")


def _setting(environment: str, name: str) -> str:
    match = re.search(rf"^{name}=(.*)$", _profile(environment), re.MULTILINE)
    assert match, f"{name} missing from {environment}.env"
    return match.group(1).strip()


# --- Derivation --------------------------------------------------------------


def test_checked_in_quotas_match_the_derivation():
    """``derive_limits.py --check`` is the contract; this runs it."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "derive_limits.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, (
        "Derived limits are stale. Run scripts/derive_limits.py.\n" + result.stdout
    )


def test_local_burst_tuning_preserves_other_environments_and_daily_limits():
    derive = _derive_module()
    model = derive.load_cost_model()
    baseline = derive.derived_quota_rows(model)
    key = "places.googleapis.com/GetPhotoMediaRequestPerMinutePerProject"
    model["quotaSizing"]["burstPerMinuteFloor"][key]["local"] += 10
    updated = derive.derived_quota_rows(model)
    row = tuple(key.split("/"))
    assert updated[row]["local"] == baseline[row]["local"] + 10
    updated[row]["local"] = baseline[row]["local"]
    assert updated == baseline


def test_free_pool_shares_do_not_oversubscribe_the_account():
    """Google's free allowances are pooled across all projects, not per project.

    Shares summing above 1.0 would quota three environments for allowances the
    billing account cannot collectively deliver, and the overflow bills at full
    rate -- the condition behind the 2026-08-27 incident's cost.
    """
    model = cost_model.load()
    total = sum(float(model["freePoolShare"][env]) for env in ENVIRONMENTS)
    assert total <= 1.0, f"free pool shares sum to {total}"


def test_quotas_sit_above_what_the_daily_budget_can_buy():
    """The INR ceiling must refuse before a quota rejects.

    A quota that binds first would throttle a legitimately complex trip for
    reasons unrelated to money -- the failure mode the call-counting limits had.
    Its job is to stop a compromised key, so it sits above the budget.
    """
    derive = _derive_module()
    model = cost_model.load()
    guardrails = json.loads((ROOT / "infra" / "billing-guardrails.json").read_text("utf-8"))
    by_key = {(row["service"], row["quotaId"]): row for row in guardrails["gcp"]["quotas"]}

    for (service, quota_id), sku in derive.QUOTA_SKU.items():
        unit_usd = derive.GOOGLE_PLACES_USD_PER_REQUEST[sku]
        for environment in ENVIRONMENTS:
            budget_inr = derive.daily_ceiling_inr(environment) * float(
                model["quotaSizing"]["googleShareOfDailyCeiling"]
            )
            affordable = int(budget_inr / (unit_usd * cost_model.inr_per_usd()))
            assert by_key[(service, quota_id)][environment] >= affordable, (
                f"{service}/{quota_id} [{environment}] rejects before the budget does"
            )


# --- Unit discipline ---------------------------------------------------------


def test_every_spend_ceiling_names_its_currency():
    """A ceiling whose name omits the unit is one paste away from an 88x budget."""
    for environment in ENVIRONMENTS:
        ceilings = [
            line.partition("=")[0]
            for line in _profile(environment).splitlines()
            if line.startswith("COST_CEILING_") and "=" in line
        ]
        amounts = [
            name
            for name in ceilings
            if name.endswith(("HOURLY", "DAILY", "WEEKLY", "MONTHLY"))
        ]
        assert amounts, f"no spend ceilings found in {environment}.env"
        for name in amounts:
            assert "_INR_" in name, f"{name} does not state its currency"


def test_usd_to_inr_applies_the_configured_rate():
    assert cost_model.usd_to_inr(1.0) == pytest.approx(cost_model.inr_per_usd())
    assert cost_model.usd_to_inr(None) == 0.0
    assert cost_model.usd_to_inr("nonsense") == 0.0


def test_ceiling_accessors_return_the_profile_values_unconverted():
    """The accessor must hand back the INR the operator wrote, not a conversion.

    If a ceiling were ever run through usd_to_inr on the way out, the effective
    budget would silently become 88x what the profile says.
    """
    for window, name in (
        ("hourly", "COST_CEILING_INR_HOURLY"),
        ("daily", "COST_CEILING_INR_DAILY"),
        ("weekly", "COST_CEILING_INR_WEEKLY"),
        ("monthly", "COST_CEILING_INR_MONTHLY"),
    ):
        assert limits_config.cost_ceiling_inr(window) == float(_setting("local", name))


def test_malformed_ceiling_falls_back_to_the_default_not_to_unlimited(monkeypatch):
    """A deployment typo must not disable the budget.

    The retired conversation ceilings read a blank value as zero and zero as
    "disabled", so an unset variable in a deploy script silently removed the
    only cost control that reached production.
    """
    for bad in ("", "   ", "not-a-number", "0", "-5"):
        monkeypatch.setenv("COST_CEILING_INR_DAILY", bad)
        assert limits_config.cost_ceiling_inr_daily() == 1000.0


def test_abuse_limits_are_generous_enough_for_real_use():
    """These bound request rate, not spend, and must not obstruct genuine use.

    Concurrency of 1 previously made a second browser tab fail with a 429 that
    read as a bug.
    """
    assert limits_config.chat_max_concurrent_per_user() >= 5
    assert limits_config.chat_max_concurrent_global() >= 12
    assert limits_config.chat_user_requests_per_minute() >= 30


def test_no_per_trip_call_budget_remains_in_config():
    """The agent may make whatever calls a quality itinerary needs."""
    for retired in (
        "google_places_max_text_searches_per_trip",
        "google_places_max_review_details_per_trip",
        "google_places_max_photos_per_trip",
        "max_tool_phases_per_turn",
        "max_transport_comparisons_per_turn",
        "monthly_llm_cost_cap_usd",
        "conversation_limit",
    ):
        assert not hasattr(limits_config, retired), f"{retired} is still configurable"


# --- Cosmos derivation ---------------------------------------------------------


def test_every_window_the_ledger_enforces_has_a_ceiling_and_a_reset():
    """A window in COST_CEILING_WINDOWS with no key or reset silently never rolls.

    ``_rolled_windows`` keys each window's bucket; a window the key function does
    not handle falls through to the monthly key, so an hourly burst would
    accumulate against the month and never reset.
    """
    from datetime import UTC, datetime

    from tripplanner import cost_ledger

    now = datetime(2026, 9, 13, 14, 30, tzinfo=UTC)
    keys = {
        window: cost_ledger._window_key(window, now)
        for window in limits_config.COST_CEILING_WINDOWS
    }
    assert len(set(keys.values())) == len(keys), f"two windows share one key: {keys}"
    for window in limits_config.COST_CEILING_WINDOWS:
        assert limits_config.cost_ceiling_inr(window) > 0
        assert cost_ledger._resets_at(window, now) > now.isoformat().replace("+00:00", "Z")


def test_hourly_ceiling_is_a_burst_of_the_daily_one():
    """Hourly must bind tighter than daily but still buy a few trips.

    Equal to daily would make it decorative; too small would refuse the two or
    three back-to-back trips the owner builds in one sitting.
    """
    model = cost_model.load()
    p95_trip_inr = float(model["cosmosSizing"]["p95TripCostInr"])
    for environment in ENVIRONMENTS:
        hourly = float(_setting(environment, "COST_CEILING_INR_HOURLY"))
        daily = float(_setting(environment, "COST_CEILING_INR_DAILY"))
        assert hourly < daily, f"{environment}: hourly ceiling does not bind"
        assert hourly / p95_trip_inr >= 3, (
            f"{environment}: hourly ceiling buys fewer than three worst-case trips"
        )


def test_cosmos_burst_demand_covers_a_peak_burst_of_trips():
    """The recorded burst demand must cover what the ceilings actually admit.

    Three concurrent builds fanned across places_cache._MAX_WORKERS threads demand
    several hundred RU/s. Where the free-tier cap is lower, that gap is recorded
    rather than silently hidden.
    """
    derive = _derive_module()
    model = derive.load_cost_model()
    guardrails = json.loads((ROOT / "infra" / "billing-guardrails.json").read_text("utf-8"))

    for environment in ENVIRONMENTS:
        row = guardrails["azure"]["cosmos"][environment]
        peak = derive.peak_concurrent_trips(environment, model)
        burst_demand = (
            peak
            * derive.ru_per_trip(model)
            / float(model["cosmosSizing"]["tripBuildSeconds"])
            * float(model["cosmosSizing"]["burstFactor"])
        )
        assert int(row["burstDemandRuPerSecond"]) >= burst_demand
        assert int(row["ruPerSecond"]) >= int(model["cosmosSizing"]["minimumRuPerSecond"])


def test_provisioned_cosmos_throughput_is_never_billed():
    """Owner policy: canary and prod together stay inside the account's free 1000 RU/s.

    Burst sizing once derived 700 RU/s for each database -- 1400 in an account whose
    free tier covers 1000, so every deploy would have billed 400 RU/s around the clock
    for bursts a retried 429 absorbs.
    """
    derive = _derive_module()
    model = derive.load_cost_model()
    guardrails = json.loads((ROOT / "infra" / "billing-guardrails.json").read_text("utf-8"))
    data_bicep = (ROOT / "infra" / "data.bicep").read_text("utf-8")
    caps = derive.free_tier_caps(model)

    provisioned_in_account = {
        environment
        for environment in ENVIRONMENTS
        if f"cosmosConfig.{environment}.ruPerSecond" in data_bicep
    }
    assert provisioned_in_account == set(caps), "every database in the account needs a cap"
    total = sum(int(guardrails["azure"]["cosmos"][name]["ruPerSecond"]) for name in caps)
    assert total <= int(model["cosmosSizing"]["freeTierRuPerSecond"])
    for name, cap in caps.items():
        assert int(guardrails["azure"]["cosmos"][name]["ruPerSecond"]) <= cap


def test_derivation_refuses_caps_that_would_bill():
    derive = _derive_module()
    model = derive.load_cost_model()
    model["cosmosSizing"]["freeTierAllocationRuPerSecond"]["prod"] = 700

    with pytest.raises(SystemExit, match="over the 1000 RU/s free tier"):
        derive.check_free_tier_budget(model)


def test_peak_concurrency_is_bounded_by_both_controls():
    """Cost and abuse controls both cap it; neither may be ignored."""
    derive = _derive_module()
    model = derive.load_cost_model()
    for environment in ENVIRONMENTS:
        peak = derive.peak_concurrent_trips(environment, model)
        assert peak <= derive.max_concurrent_global(environment)
        assert peak <= derive.hourly_ceiling_inr(environment) / float(
            model["cosmosSizing"]["p95TripCostInr"]
        )
        assert peak >= 1


def test_cosmos_throughput_tracks_the_hourly_ceiling():
    """Raising the burst ceiling must raise the demand the database is sized from.

    A guardrail that stays put when the budget moves is the drift this whole
    derivation exists to prevent. Provisioning itself stops at the free-tier cap.
    """
    derive = _derive_module()
    model = derive.load_cost_model()
    baseline = derive.cosmos_burst_demand_ru_per_second("prod", model)
    model["cosmosSizing"]["p95TripCostInr"] = (
        float(model["cosmosSizing"]["p95TripCostInr"]) / 4
    )
    assert derive.cosmos_burst_demand_ru_per_second("prod", model) > baseline
    assert derive.derive_cosmos_ru_per_second("prod", model) == derive.free_tier_caps(model)["prod"]


def test_cosmos_throttling_alert_does_not_page_at_severity_one():
    """A retried 429 is not an outage.

    Cosmos throttling has its own thresholded rule; it reached severity 1 only
    through failureAlert's catch-all ERROR match, which paged every five minutes
    for a condition that is only meaningful in aggregate.
    """
    guardrails = json.loads((ROOT / "infra" / "billing-guardrails.json").read_text("utf-8"))
    alerts = guardrails["azureInfraHealthAlerts"]
    assert alerts["cosmosThrottlingAlert"]["severity"] >= 3
    assert alerts["cosmosThrottlingAlert"]["threshold"] >= 20

    query = (ROOT / "infra" / "queries" / "application-failures.kql").read_text("utf-8")
    assert "429" in query and "storage_operation" in query, (
        "the severity-1 failure query no longer excludes Cosmos throttling"
    )


def test_derived_cosmos_values_are_not_hand_edited():
    """The checked-in rows must equal what the derivation computes."""
    derive = _derive_module()
    model = derive.load_cost_model()
    guardrails = json.loads((ROOT / "infra" / "billing-guardrails.json").read_text("utf-8"))
    for environment in ENVIRONMENTS:
        assert guardrails["azure"]["cosmos"][environment]["ruPerSecond"] == (
            derive.derive_cosmos_ru_per_second(environment, model)
        )
    assert guardrails["azureInfraHealthAlerts"]["cosmosThrottlingAlert"]["threshold"] == (
        derive.derive_cosmos_throttle_threshold(model)
    )


def test_bicep_reads_cosmos_throughput_from_the_derived_file():
    """A literal RU/s in Bicep would drift from the budget the moment it moved."""
    data_bicep = (ROOT / "infra" / "data.bicep").read_text("utf-8")
    assert "billing-guardrails.json" in data_bicep
    assert "ruPerSecond" in data_bicep
    module = (ROOT / "infra" / "modules" / "cosmos-data.bicep").read_text("utf-8")
    assert "databaseThroughput int = 400" not in module
