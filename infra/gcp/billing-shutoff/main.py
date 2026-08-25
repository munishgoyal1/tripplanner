"""Detach every project from the billing account when the global budget breaks.

Cloud Billing budgets only ever send notifications; nothing in GCP stops spend on
its own. This function is the enforcement half: the global budget publishes each
threshold update to Pub/Sub, and once reported cost reaches the budget amount we
remove the billing account from every project it funds.

Reported cost lags real usage by hours, so treat this as a backstop rather than a
guarantee. Per-key API quotas are what actually bound a runaway loop.
"""

from __future__ import annotations

import base64
import json
import logging
import os

import functions_framework
import googleapiclient.discovery

BILLING_ACCOUNT = os.environ["BILLING_ACCOUNT"]
GUARDED_BUDGET = os.environ["GUARDED_BUDGET"]


def _billing_client():
    return googleapiclient.discovery.build("cloudbilling", "v1", cache_discovery=False)


def _funded_projects(billing) -> list[str]:
    projects: list[str] = []
    request = billing.billingAccounts().projects().list(
        name=f"billingAccounts/{BILLING_ACCOUNT}"
    )
    while request is not None:
        response = request.execute()
        for info in response.get("projectBillingInfo", []):
            if info.get("billingEnabled"):
                projects.append(info["projectId"])
        request = billing.billingAccounts().projects().list_next(request, response)
    return projects


@functions_framework.cloud_event
def shutoff(cloud_event) -> None:
    payload = json.loads(base64.b64decode(cloud_event.data["message"]["data"]))

    # Every budget on the account can publish here; only the global one may detach.
    if payload.get("budgetDisplayName") != GUARDED_BUDGET:
        return

    cost = float(payload.get("costAmount") or 0)
    budget = float(payload.get("budgetAmount") or 0)
    if budget <= 0 or cost < budget:
        logging.info("Global budget intact: %s of %s", cost, budget)
        return

    billing = _billing_client()
    for project_id in _funded_projects(billing):
        billing.projects().updateBillingInfo(
            name=f"projects/{project_id}",
            body={"billingAccountName": ""},
        ).execute()
        logging.warning("Detached billing from %s", project_id)

    logging.warning(
        "Global budget breached at %s of %s; billing disabled account-wide", cost, budget
    )
