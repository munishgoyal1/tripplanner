from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
MIGRATION_ROOT = ROOT / "infra" / "migration"


def test_one_click_operations_compose_existing_guarded_phases() -> None:
    script = (MIGRATION_ROOT / "Invoke-OneClickMigration.ps1").read_text(encoding="utf-8")

    assert '[ValidateSet("Provision", "CopyData", "Migrate")]' in script
    assert '"PROVISION_ALL_CLOUD_INFRASTRUCTURE"' in script
    assert '"COPY_ALL_CLOUD_DATA"' in script
    assert '"MIGRATE_TO_NEW_AZURE_AND_GOOGLE_ACCOUNTS"' in script
    assert (
        'Invoke-AzurePhase -Phase provision -PhaseApproval "APPROVE_TARGET_PROVISIONING"'
        in script
    )
    assert 'Invoke-AzurePhase -Phase data -PhaseApproval "APPROVE_DATA_COPY"' in script
    assert "Invoke-AzurePhase -Phase validate" in script
    assert "-Phase Migrate" in script
    assert "-Resume" in script
    assert "googleManifest.source.gcloudConfiguration" in script
    assert "googleManifest.target.gcloudConfiguration" in script
    assert "APPROVE_SOURCE_RETIREMENT" not in script
    assert "RETIRE_OLD_GOOGLE_ACCOUNT" not in script


def test_click_launchers_exist_for_macos_and_windows() -> None:
    names = (
        "Provision-All-Cloud-Infrastructure",
        "Copy-All-Cloud-Data",
        "Migrate-To-New-Cloud-Accounts",
    )

    for name in names:
        mac = (MIGRATION_ROOT / f"{name}.command").read_text(encoding="utf-8")
        windows = (MIGRATION_ROOT / f"{name}.cmd").read_text(encoding="utf-8")
        assert "Invoke-OneClickMigration.ps1" in mac
        assert "Invoke-OneClickMigration.ps1" in windows


def test_checked_in_manifest_has_exact_current_target_without_secrets() -> None:
    manifest = json.loads(
        (MIGRATION_ROOT / "cloud-account-migration.json").read_text(encoding="utf-8")
    )

    assert manifest["azure"]["target"]["subscriptionId"] == (
        "9fe3951c-d440-4d09-91f1-cb47e02f04c3"
    )
    assert manifest["azure"]["cosmosDatabases"] == ["tripplanner-canary", "tripplanner-prod"]
    assert manifest["azure"]["deleteSourceResourceGroupsOnRetire"] is False
    serialized = json.dumps(manifest).lower()
    for credential_field in ('"apikey"', '"clientsecret"', '"connectionstring"', '"token"'):
        assert credential_field not in serialized


def test_google_migrate_mode_stops_before_retirement() -> None:
    script = (MIGRATION_ROOT / "google" / "migrate-google-account.ps1").read_text(
        encoding="utf-8"
    )
    migrate_mode = script.split('"Migrate" {', maxsplit=1)[1].split('"All" {', maxsplit=1)[0]

    assert "Invoke-Plan" in migrate_mode
    assert "Invoke-Grant" in migrate_mode
    assert "Invoke-Cutover" in migrate_mode
    assert "Invoke-Retire" not in migrate_mode
