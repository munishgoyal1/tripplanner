from __future__ import annotations

from pathlib import Path


def test_manual_image_workflow_cannot_bypass_guarded_release() -> None:
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "docker/build-push-action" in workflow
    assert "${{ github.sha }}" in workflow
    assert "azure/login" not in workflow
    assert "azure/cli" not in workflow
    assert "az deployment" not in workflow
    assert "RESOURCE_GROUP" not in workflow


def test_hosted_deployments_do_not_import_local_environment() -> None:
    root = Path(__file__).parents[1]
    canary = (root / "infra" / "deploy-canary.ps1").read_text(encoding="utf-8")
    production = (root / "infra" / "deploy-prod.ps1").read_text(encoding="utf-8")

    assert '[string]$EnvFile = ".env.canary"' in canary
    assert '[string]$EnvFile = ".env.prod"' in production
    assert "Import-DeploymentEnvironment -Path $EnvFile" in canary
    assert "Import-DeploymentEnvironment -Path $EnvFile" in production


def test_hosted_deployments_use_shared_azure_json_and_delete_guards() -> None:
    root = Path(__file__).parents[1]
    canary = (root / "infra" / "deploy-canary.ps1").read_text(encoding="utf-8")
    production = (root / "infra" / "deploy-prod.ps1").read_text(encoding="utf-8")
    common = (root / "infra" / "deployment-common.ps1").read_text(encoding="utf-8")

    for script in (canary, production):
        assert '. "$PSScriptRoot/deployment-common.ps1"' in script
        assert "ConvertFrom-AzureCliJson" in script
        assert "Assert-DeploymentHasNoDeletes" in script
    assert "function ConvertFrom-AzureCliJson" in common


def test_azure_openai_provisioning_defaults_match_deployment_accounts() -> None:
    script = (
        Path(__file__).parents[1] / "infra" / "provision-aoai.ps1"
    ).read_text(encoding="utf-8")

    assert '"aoaiprodmd1ks"' in script
    assert '"aoaicanarymd1ks"' in script
    assert "aoaiprodtripplanner" not in script
    assert "aoaicanarytripplanner" not in script


def test_hosted_deployments_surface_azure_cli_failures() -> None:
    root = Path(__file__).parents[1]
    canary = (root / "infra" / "deploy-canary.ps1").read_text(encoding="utf-8")
    production = (root / "infra" / "deploy-prod.ps1").read_text(encoding="utf-8")

    for script in (canary, production):
        deploy_block = script.split("$rawDeploy = az deployment group create", 1)[1]
        assert "--output json 2>&1 | Out-String" in deploy_block
        assert "$deployExitCode = $LASTEXITCODE" in deploy_block
        assert "if ($deployExitCode -ne 0)" in deploy_block
