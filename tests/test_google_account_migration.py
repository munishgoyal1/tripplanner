from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION_ROOT = ROOT / "infra" / "migration" / "google"


def test_google_migration_manifest_selects_every_source_billed_project() -> None:
    manifest = json.loads(
        (MIGRATION_ROOT / "google-account-migration.json").read_text(encoding="utf-8")
    )

    assert manifest["schemaVersion"] == 1
    assert manifest["source"]["principal"] == "munishgoyal1@gmail.com"
    assert manifest["target"]["principal"] == "munishgoyal@aitripplanner.co"
    assert manifest["projectSelection"] == {
        "mode": "all-linked-to-source-billing",
        "excludeProjectIds": [],
    }
    assert {project["environment"] for project in manifest["knownProjects"]} == {
        "local",
        "canary",
        "prod",
        "ops",
    }


def test_google_migration_requires_checkpoints_before_retirement() -> None:
    script = (MIGRATION_ROOT / "migrate-google-account.ps1").read_text(encoding="utf-8")
    common = (MIGRATION_ROOT / "google-migration-common.ps1").read_text(encoding="utf-8")

    assert "Get-SourceBillingProjects" in script
    assert "all-linked-to-source-billing" in common
    assert "Write-MigrationProjectCheckpoint" in script
    assert "Get-ExistingMigrationProjectIds" in script
    assert "Assert-ProjectsAccessible" in script
    assert script.index("Invoke-Verify\n") < script.index(
        '"Remove source principal project owner"'
    )
    assert "CONFIRM_GA4_AND_PAYMENTS_TRANSFERRED" in script
    assert "RETIRE_OLD_GOOGLE_ACCOUNT" in script
    assert '"billing", "budgets", "delete"' in script
    assert "gcloud has no billing-account close command" in script


def test_google_cutover_preserves_projects_and_reapplies_guardrails() -> None:
    script = (MIGRATION_ROOT / "migrate-google-account.ps1").read_text(encoding="utf-8")

    assert '"beta", "projects", "move"' in script
    assert '"beta", "billing", "projects", "link"' in script
    assert "apply-billing-guardrails.ps1" in script
    assert "APPROVE_GOOGLE_MAPS_SPEND" in script
    assert "APPROVE_GOOGLE_PLACES_SPEND" in script
    assert "Set-RepositoryTargetConfiguration" in script
    assert "unexpected billing account" in script
    assert "$state.billingAccount -ne $manifest.target.billingAccount" in script
    assert '"projects", "delete"' not in script


def test_google_all_mode_switches_pre_authenticated_configurations() -> None:
    script = (MIGRATION_ROOT / "migrate-google-account.ps1").read_text(encoding="utf-8")

    assert "$SourceGcloudConfiguration" in script
    assert "$TargetGcloudConfiguration" in script
    assert "Select-GcloudConfiguration" in script
    all_mode = script.split('"All" {', maxsplit=1)[1]
    assert all_mode.index("Invoke-Plan") < all_mode.index("Invoke-Grant")
    assert all_mode.index("Invoke-Grant") < all_mode.index("Invoke-Cutover")
    assert all_mode.index("Invoke-Cutover") < all_mode.index("Invoke-Retire")


def test_google_operator_identity_is_configured_separately_from_azure() -> None:
    guardrails = json.loads((ROOT / "infra" / "billing-guardrails.json").read_text())
    runtime = (ROOT / "infra" / "azure" / "set-google-runtime-access.ps1").read_text(
        encoding="utf-8"
    )

    assert guardrails["gcp"]["operatorAccount"] == "munishgoyal1@gmail.com"
    assert "$config.gcp.operatorAccount" in runtime
    assert 'if ($account.user -ine "munishgoyal1@gmail.com")' in runtime