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
        amounts = [name for name in ceilings if name.endswith(("DAILY", "WEEKLY", "MONTHLY"))]
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
