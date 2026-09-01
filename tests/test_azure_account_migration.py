from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION_ROOT = ROOT / "infra" / "migration"


def test_hosted_cosmos_excludes_local_emulator_database() -> None:
    data_template = (ROOT / "infra" / "data.bicep").read_text(encoding="utf-8")
    manifest = json.loads(
        (MIGRATION_ROOT / "migration.example.json").read_text(encoding="utf-8")
    )

    assert manifest["azure"]["cosmosDatabases"] == [
        "tripplanner-canary",
        "tripplanner-prod",
    ]
    assert "'tripplanner-local'" not in data_template
    assert "'tripplanner-canary'" in data_template
    assert "'tripplanner-prod'" in data_template


def test_azure_migration_copies_only_configured_hosted_databases() -> None:
    script = (
        MIGRATION_ROOT / "azure" / "Invoke-AzureMigration.ps1"
    ).read_text(encoding="utf-8")

    assert "$cosmosDatabases = @($azure.cosmosDatabases)" in script
    assert "must not include tripplanner-local" in script
    assert "return @($cosmosDatabases)" in script