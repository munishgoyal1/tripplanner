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
* **Cosmos RU/s IS cost-derived, but from the hourly ceiling, not the daily
  one.** Provisioned throughput is a rate, and a daily total divided by 86400 is
  not a rate anything real runs at -- spend arrives in bursts. So Cosmos sizing
  starts at ``COST_CEILING_INR_HOURLY``, converts it to trips that may be in
  flight at once, caps that by ``CHAT_MAX_CONCURRENT_GLOBAL`` (the anti-abuse
  control), and prices the Cosmos work one trip does. See ``cosmosSizing`` in
  ``config/cost-model.json``.
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


def _profile_number(environment: str, name: str) -> float:
    """Read one setting straight from the profile the running app reads.

    Deliberately the .env file rather than ``limits_config``: the derivation
    must reflect what the environment is actually deployed with, not what the
    code defaults to when a profile forgets to set it.
    """
    profile = (ROOT / "config" / "environments" / f"{environment}.env").read_text(
        encoding="utf-8"
    )
    match = re.search(rf"^{name}=(.+)$", profile, re.MULTILINE)
    if not match:
        raise SystemExit(f"{name} missing from {environment}.env")
    return float(match.group(1).strip())


def daily_ceiling_inr(environment: str) -> float:
    """Read COST_CEILING_INR_DAILY straight from the profile the app reads."""
    return _profile_number(environment, "COST_CEILING_INR_DAILY")


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
        derived[(service, quota_id)] = {
            environment: int(floor[environment] if isinstance(floor, dict) else floor)
            for environment in ENVIRONMENTS
        }
    return derived


# --- Cosmos DB -----------------------------------------------------------------
# Everything below derives from two numbers the owner already sets: the hourly
# INR ceiling (config/environments/*.env) and CHAT_MAX_CONCURRENT_GLOBAL (the
# anti-abuse admission control in the same file). Nothing here is hand-tuned.


def hourly_ceiling_inr(environment: str) -> float:
    return _profile_number(environment, "COST_CEILING_INR_HOURLY")


def max_concurrent_global(environment: str) -> int:
    return int(_profile_number(environment, "CHAT_MAX_CONCURRENT_GLOBAL"))


def peak_concurrent_trips(environment: str, model: dict[str, Any]) -> int:
    """Trips that may legitimately be building at the same instant.

    Two independent ceilings already in config, whichever binds first:

    * **Money.** The hourly ceiling affords ``hourly / p95TripCostInr`` trips in
      an hour, and the worst case is all of them starting together.
    * **Abuse.** ``CHAT_MAX_CONCURRENT_GLOBAL`` admits no more than that many
      concurrent chat turns however cheap they are.

    At the shipped defaults money binds first (INR 400/hour buys 3 worst-case
    trips; the concurrency control admits 12), which is the intended
    relationship: the anti-abuse limit is a backstop against scripted traffic,
    not the thing that sizes infrastructure.
    """
    sizing = model["cosmosSizing"]
    affordable = int(hourly_ceiling_inr(environment) / float(sizing["p95TripCostInr"]))
    return max(1, min(affordable, max_concurrent_global(environment)))


def ru_per_trip(model: dict[str, Any]) -> float:
    """RU one new_trip build spends across every container it touches."""
    sizing = model["cosmosSizing"]
    read_rate = float(sizing["ruPerReadKb"])
    write_rate = float(sizing["ruPerWriteKb"])
    total = 0.0
    for container, profile in sizing["tripOpProfile"].items():
        if container.startswith("$"):
            continue
        doc_kb = float(profile["docKb"])
        # A point operation is never cheaper than its 1 KB floor, whatever the
        # document weighs -- pricing a 0.2 KB write at one fifth of a KB write
        # would understate every small-document container here.
        total += int(profile["reads"]) * max(read_rate, doc_kb * read_rate)
        total += int(profile["writes"]) * max(write_rate, doc_kb * write_rate)
    return total


def cosmos_burst_demand_ru_per_second(environment: str, model: dict[str, Any]) -> int:
    """RU/s a peak burst of trip builds would use, rounded up. Not what is provisioned.

    Average demand is ``concurrent trips x RU per trip / build seconds``.
    ``burstFactor`` lifts that to the instantaneous peak, because a build fans
    its Cosmos work across ``places_cache._MAX_WORKERS`` threads rather than
    spreading it evenly.
    """
    sizing = model["cosmosSizing"]
    average = (
        peak_concurrent_trips(environment, model)
        * ru_per_trip(model)
        / float(sizing["tripBuildSeconds"])
    )
    demand = average * float(sizing["burstFactor"]) * float(sizing["provisionHeadroom"])
    step = int(sizing["roundRuToMultipleOf"])
    return int(-(-demand // step) * step)


def free_tier_caps(model: dict[str, Any]) -> dict[str, int]:
    """Hard RU/s ceilings for the databases provisioned in the free-tier account."""
    allocation = model["cosmosSizing"]["freeTierAllocationRuPerSecond"]
    return {name: int(value) for name, value in allocation.items() if not name.startswith("$")}


def derive_cosmos_ru_per_second(environment: str, model: dict[str, Any]) -> int:
    """Provisioned RU/s for this environment's shared-throughput database.

    Burst demand sizes it, but a database in the free-tier account can never be
    provisioned above its ``freeTierAllocationRuPerSecond`` cap. RU/s above the
    account's free 1000 is billed every hour whether or not it is used, while a
    burst above the cap only costs a retried 429. So the owner's no-billing policy
    wins over burst sizing, and the throttling alert reports when that trade stops
    holding.
    """
    sizing = model["cosmosSizing"]
    floor = int(sizing["minimumRuPerSecond"])
    demand = max(floor, cosmos_burst_demand_ru_per_second(environment, model))
    cap = free_tier_caps(model).get(environment)
    return demand if cap is None else min(demand, cap)


def check_free_tier_budget(model: dict[str, Any]) -> None:
    """Refuse an allocation that would bill: the caps must fit the free grant."""
    sizing = model["cosmosSizing"]
    caps = free_tier_caps(model)
    budget = int(sizing["freeTierRuPerSecond"])
    floor = int(sizing["minimumRuPerSecond"])
    if sum(caps.values()) > budget:
        raise SystemExit(
            f"cosmosSizing.freeTierAllocationRuPerSecond sums to {sum(caps.values())} RU/s, "
            f"over the {budget} RU/s free tier: the overflow would be billed hourly"
        )
    below_floor = {name: cap for name, cap in caps.items() if cap < floor}
    if below_floor:
        raise SystemExit(f"free-tier caps below Azure's {floor} RU/s database floor: {below_floor}")


def derive_cosmos_throttle_threshold(model: dict[str, Any]) -> int:
    """429s in the alert window that mean the sizing above is genuinely wrong.

    A 429 is not an incident on its own -- the Cosmos SDK retries it and the
    caller never sees it. What matters is the *rate*: once more than
    ``toleratedThrottleRate`` of a peak burst's operations are being rejected,
    provisioned RU/s no longer matches what the ceilings admit.
    """
    sizing = model["cosmosSizing"]
    alert = sizing["throttleAlert"]
    ops_per_trip = sum(
        int(profile["reads"]) + int(profile["writes"])
        for container, profile in sizing["tripOpProfile"].items()
        if not container.startswith("$")
    )
    window_minutes = _alert_window_minutes()
    # Peak operations the window can legitimately contain, at the busiest
    # environment -- the alert is one ARM rule over one shared account.
    peak_trips_per_minute = max(
        peak_concurrent_trips(environment, model) for environment in ENVIRONMENTS
    ) * (60.0 / float(sizing["tripBuildSeconds"]))
    ops_in_window = ops_per_trip * peak_trips_per_minute * window_minutes
    tolerated = int(ops_in_window * float(alert["toleratedThrottleRate"]))
    return max(int(alert["minimumThreshold"]), tolerated)


def _alert_window_minutes() -> float:
    """Minutes in the Cosmos alert's evaluation window.

    Read from the guardrails file rather than the cost model: windowSize is a
    genuine ARM value that main.bicep deploys, so it has exactly one home and
    this derivation follows it instead of keeping a second copy.
    """
    guardrails = json.loads(GUARDRAILS_PATH.read_text(encoding="utf-8"))
    alert = (guardrails.get("azureInfraHealthAlerts") or {}).get("cosmosThrottlingAlert") or {}
    window = str(alert.get("windowSize") or "PT15M")
    match = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?$", window)
    if not match:
        return 15.0
    hours, minutes = match.groups()
    return int(hours or 0) * 60 + int(minutes or 0)


def derive_cosmos(guardrails: dict[str, Any], model: dict[str, Any]) -> list[str]:
    """Write the derived RU/s and 429 threshold into the guardrails file."""
    check_free_tier_budget(model)
    changes: list[str] = []
    cosmos = guardrails.setdefault("azure", {}).setdefault("cosmos", {})
    comment = (
        "DERIVED by scripts/derive_limits.py from cosmosSizing in "
        "config/cost-model.json plus COST_CEILING_INR_HOURLY and "
        "CHAT_MAX_CONCURRENT_GLOBAL in config/environments/*.env. Do not hand-edit. "
        "ruPerSecond is the shared database throughput infra/data.bicep provisions for "
        "canary and prod in the free-tier account: burst demand sizes it, but it never "
        "exceeds that database's freeTierCapRuPerSecond, and the caps together fit the "
        "account's free 1000 RU/s, so provisioned throughput is never billed. "
        "burstDemandRuPerSecond is what a peak burst would use; when it exceeds the "
        "cap, the excess is served as retried 429s. The local row is informational: "
        "no local database is provisioned from this file."
    )
    if cosmos.get("$comment") != comment:
        changes.append("cosmos $comment: regenerated")
        cosmos["$comment"] = comment
    caps = free_tier_caps(model)
    for environment in ENVIRONMENTS:
        row = cosmos.setdefault(environment, {})
        wanted = {
            "ruPerSecond": derive_cosmos_ru_per_second(environment, model),
            "burstDemandRuPerSecond": cosmos_burst_demand_ru_per_second(environment, model),
        }
        if environment in caps:
            wanted["freeTierCapRuPerSecond"] = caps[environment]
        for field, value in wanted.items():
            if row.get(field) != value:
                changes.append(f"cosmos {field} [{environment}]: {row.get(field)} -> {value}")
                row[field] = value
        for stale_field in set(row) - set(wanted):
            changes.append(f"cosmos {stale_field} [{environment}]: removed")
            del row[stale_field]

    threshold = derive_cosmos_throttle_threshold(model)
    alert = guardrails.setdefault("azureInfraHealthAlerts", {}).setdefault(
        "cosmosThrottlingAlert", {}
    )
    if alert.get("threshold") != threshold:
        changes.append(f"cosmosThrottlingAlert threshold: {alert.get('threshold')} -> {threshold}")
        alert["threshold"] = threshold
    # The description is rendered into the alert email, so a stale one misreports
    # the condition that fired. It carries the number, so it is derived too.
    window = int(_alert_window_minutes())
    description = (
        f"Alerts when Cosmos DB returns at least {threshold} throttled requests in "
        f"{window} minutes, which is about {alert_tolerance_percent(model)} percent of "
        "the operations a peak burst may legitimately issue."
    )
    if alert.get("description") != description:
        changes.append("cosmosThrottlingAlert description: regenerated")
        alert["description"] = description
    return changes


def alert_tolerance_percent(model: dict[str, Any]) -> str:
    rate = float(model["cosmosSizing"]["throttleAlert"]["toleratedThrottleRate"]) * 100
    return f"{rate:g}"


def monthly_ceiling_inr(environment: str) -> float:
    return _profile_number(environment, "COST_CEILING_INR_MONTHLY")


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

    stale.extend(derive_cosmos(guardrails, model))
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
