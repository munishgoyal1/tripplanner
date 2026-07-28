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
    assert "Import-DotEnv -Path $EnvFile" in canary
    assert "Import-DotEnv -Path $EnvFile" in production
