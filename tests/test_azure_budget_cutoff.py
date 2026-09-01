from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AZURE_INFRA = ROOT / "infra" / "azure"


def test_cutoff_runbook_has_narrow_non_delete_behavior() -> None:
    runbook = (AZURE_INFRA / "budget-cutoff-runbook.ps1").read_text(encoding="utf-8")
    deployer = (AZURE_INFRA / "deploy-budget-cutoff.ps1").read_text(encoding="utf-8")

    assert 'budgetName -ne "tripplanner-global-8000inr"' in runbook
    assert "threshold -lt 100" in runbook
    assert "[Parameter(Mandatory)]\n    [object]$WebhookData" not in runbook
    assert "Microsoft.App/containerApps" in runbook
    assert "Microsoft.App/jobs" in runbook
    assert "Microsoft.CognitiveServices/accounts" in runbook
    assert "/delete" not in runbook.lower()
    assert '"Microsoft.App/containerApps/write"' in deployer
    assert '"Microsoft.CognitiveServices/accounts/write"' in deployer
    assert '"*"' not in deployer
    assert "/delete" not in deployer.lower()


def test_cutoff_uses_separate_action_group_at_actual_100_only() -> None:
    deployer = (AZURE_INFRA / "deploy-budget-cutoff.ps1").read_text(encoding="utf-8")
    config = json.loads((ROOT / "infra" / "billing-guardrails.json").read_text(encoding="utf-8"))

    assert config["azure"]["cutoff"]["actionGroupName"] == "tripplanner-budget-cutoff"
    assert "^actual100$" in deployer
    assert "automationRunbookReceivers" in deployer
    assert "useCommonAlertSchema = $false" in deployer
    assert "Connect-AzAccount -AccessToken $token" in deployer
    assert "ConvertTo-SecureString $token" not in deployer
