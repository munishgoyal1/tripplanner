"""Derive every real-time guardrail from the INR ceilings the owner sets.

The owner sets three numbers per environment in ``config/environments/*.env``:
``COST_CEILING_INR_{DAILY,WEEKLY,MONTHLY}``. Everything mechanical below that --
the GCP quota preferences that hard-reject calls in real time -- is computed
here from those ceilings plus ``config/cost-model.json``, so the cloud net can
never drift away from the budget it is supposed to protect.

    python scripts/derive_limits.py --check    # CI: fail if files are stale
    python scripts/derive_limits.py            # rewrite the derived values

Two sizing rules, deliberately different:

* **Daily quotas are cost-derived.** A single SKU may not consume more than
  ``googleShareOfDailyCeiling`` of the daily INR ceiling, times ``dailyHeadroom``.
  For a SKU with a free monthly allowance the environment's reserved slice of
  that pooled allowance is the binding number instead, since calls inside the
  pool cost nothing and capping below it would throttle quality for no saving.
* **Per-minute quotas are NOT cost-derived.** They exist so ``places_cache._pace``
  can self-pace under the same ceiling Google enforces without tripping the
  provider circuit breaker. Sizing them for cost is what produced the documented
  40-60 second stalls, so they come from ``burstPerMinuteFloor``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COST_MODEL_PATH = ROOT / "config" / "cost-model.json"
GUARDRAILS_PATH = ROOT / "infra" / "billing-guardrails.json"
ENVIRONMENTS = ("local", "canary", "prod")

sys.path.insert(0, str(ROOT / "src"))
from tripplanner.validation.harness.pricing import (  # noqa: E402
    GOOGLE_PLACES_USD_PER_REQUEST,
)

#: Quota id -> the priced SKU it consumes. Quotas with no entry bound an API
#: surface the application does not call; they stay pinned at their configured
#: value so a leaked key cannot spend through an unused operation.
QUOTA_SKU = {
    ("places.googleapis.com", "SearchTextRequestPerDayPerProject"): "text_search:pro",
    ("places.googleapis.com", "GetPlaceRequestPerDayPerProject"): (
        "place_details:enterprise_atmosphere"
    ),
    ("places.googleapis.com", "GetPhotoMediaRequestPerDayPerProject"): "photo_media:photo_media",
}


def load_cost_model() -> dict[str, Any]:
    return json.loads(COST_MODEL_PATH.read_text(encoding="utf-8"))


def daily_ceiling_inr(environment: str) -> float:
    """Read COST_CEILING_INR_DAILY straight from the profile the app reads."""
    profile = (ROOT / "config" / "environments" / f"{environment}.env").read_text(
        encoding="utf-8"
    )
    match = re.search(r"^COST_CEILING_INR_DAILY=(.+)$", profile, re.MULTILINE)
    if not match:
        raise SystemExit(f"COST_CEILING_INR_DAILY missing from {environment}.env")
    return float(match.group(1).strip())


def derive_daily_quota(environment: str, sku: str, model: dict[str, Any]) -> int:
    """Calls per day this environment may make of one SKU.

    Free allowance first, then what the budget can buy beyond it. The quota must
    never be the thing that binds before the INR ceiling does -- that is what
    call-counting limits used to do, throttling a complex trip for reasons
    unrelated to money. Its job is to stop a compromised key or a runaway loop,
    so it sits above the budget and lets the ledger refuse first.
    """
    unit_usd = GOOGLE_PLACES_USD_PER_REQUEST.get(sku)
    if not unit_usd:
        raise SystemExit(f"No price for {sku}; cannot derive a daily quota from a budget.")

    sizing = model["quotaSizing"]
    inr_per_usd = float(model["fx"]["inrPerUsd"])
    budget_inr = (
        daily_ceiling_inr(environment)
        * float(sizing["googleShareOfDailyCeiling"])
        * float(sizing["dailyHeadroom"])
    )
    paid_calls = int(budget_inr / (unit_usd * inr_per_usd))

    # This environment's daily slice of the account-wide free monthly allowance.
    # Calls inside it cost nothing, so they are headroom the budget never sees.
    free_pool = int(model["freePoolsPerMonth"].get(sku, 0) or 0)
    share = float(model["freePoolShare"][environment])
    free_calls = int(free_pool * share / 30.0)

    return max(1, free_calls + paid_calls)


def derived_quota_rows(model: dict[str, Any]) -> dict[tuple[str, str], dict[str, int]]:
    floors = model["quotaSizing"]["burstPerMinuteFloor"]
    derived: dict[tuple[str, str], dict[str, int]] = {}
    for (service, quota_id), sku in QUOTA_SKU.items():
        derived[(service, quota_id)] = {
            environment: derive_daily_quota(environment, sku, model)
            for environment in ENVIRONMENTS
        }
    for key, floor in floors.items():
        service, _, quota_id = key.partition("/")
        derived[(service, quota_id)] = {environment: int(floor) for environment in ENVIRONMENTS}
    return derived


def monthly_ceiling_inr(environment: str) -> float:
    profile = (ROOT / "config" / "environments" / f"{environment}.env").read_text(
        encoding="utf-8"
    )
    match = re.search(r"^COST_CEILING_INR_MONTHLY=(.+)$", profile, re.MULTILINE)
    if not match:
        raise SystemExit(f"COST_CEILING_INR_MONTHLY missing from {environment}.env")
    return float(match.group(1).strip())


def derive_cloud_budgets(guardrails: dict[str, Any], model: dict[str, Any]) -> list[str]:
    """Align the notify-only cloud budgets with the INR ceiling they shadow.

    The ceiling covers Azure and Google together, so each cloud's per-environment
    budget is its share of the monthly ceiling. Keeping them in step matters
    because a budget alert that fires far after the ceiling has already refused
    work tells the owner nothing, and one that fires far before cries wolf.
    """
    share = float(model["quotaSizing"]["googleShareOfDailyCeiling"])
    changes: list[str] = []
    for cloud, cloud_share in (("gcp", share), ("azure", 1.0 - share)):
        total = 0
        for environment in guardrails[cloud]["environments"]:
            name = environment["name"]
            monthly = int(monthly_ceiling_inr(name) * cloud_share)
            daily = int(daily_ceiling_inr(name) * cloud_share)
            if environment.get("budget") != monthly:
                changes.append(
                    f"{cloud} budget [{name}]: {environment.get('budget')} -> {monthly}"
                )
                environment["budget"] = monthly
            if environment.get("dailyBudget") != daily:
                changes.append(
                    f"{cloud} dailyBudget [{name}]: {environment.get('dailyBudget')} -> {daily}"
                )
                environment["dailyBudget"] = daily
            total += monthly
        # The account-wide alert is only meaningful if it equals what the
        # environments can collectively spend.
        global_budget = guardrails[cloud]["globalBudget"]
        if global_budget.get("amount") != total:
            changes.append(
                f"{cloud} globalBudget: {global_budget.get('amount')} -> {total}"
            )
            guardrails[cloud]["globalBudget"]["amount"] = total
    return changes


def apply(write: bool) -> int:
    model = load_cost_model()
    guardrails = json.loads(GUARDRAILS_PATH.read_text(encoding="utf-8"))
    derived = derived_quota_rows(model)

    stale: list[str] = []
    for quota in guardrails["gcp"]["quotas"]:
        key = (quota.get("service"), quota.get("quotaId"))
        if key not in derived:
            continue
        for environment, value in derived[key].items():
            if int(quota.get(environment, -1)) != value:
                stale.append(
                    f"{key[0]}/{key[1]} [{environment}]: {quota.get(environment)} -> {value}"
                )
                quota[environment] = value

    stale.extend(derive_cloud_budgets(guardrails, model))

    if not stale:
        print("All derived limits are in line with the INR ceilings.")
        return 0

    if not write:
        print("Derived limits are STALE. Run scripts/derive_limits.py to update:")
        for line in stale:
            print(f"  {line}")
        return 1

    GUARDRAILS_PATH.write_text(
        json.dumps(guardrails, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Updated {len(stale)} derived limits in {GUARDRAILS_PATH.name}:")
    for line in stale:
        print(f"  {line}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if any derived limit is stale, without writing",
    )
    args = parser.parse_args()
    return apply(write=not args.check)


if __name__ == "__main__":
    raise SystemExit(main())
