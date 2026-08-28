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


def test_production_declares_custom_domain_and_browser_photo_smoke() -> None:
    root = Path(__file__).parents[1]
    guardrails = (root / "infra" / "billing-guardrails.json").read_text(encoding="utf-8")
    production = (root / "infra" / "deploy-prod.ps1").read_text(encoding="utf-8")
    smoke = (root / "infra" / "smoke-hosted.ps1").read_text(encoding="utf-8")
    browser_smoke = (root / "frontend" / "scripts" / "hosted-maps-smoke.mjs").read_text(
        encoding="utf-8"
    )

    assert '"https://aitripplanner.co/*"' in guardrails
    assert '"browserKey": "aitripplanner-prod-browser"' in guardrails
    assert '-BrowserBaseUrl "https://aitripplanner.co"' in production
    assert "hosted-maps-smoke.mjs" in smoke
    assert "window.gm_authFailure" in browser_smoke
    assert "new window.google.maps.Map" in browser_smoke
    assert "/api/auth/guest/session" in browser_smoke
    assert "Authorization: `Bearer ${guestToken}`" in browser_smoke
    assert "/api/destination/overview?destination=Paris&news=false" in browser_smoke
    assert "destination overview returned no photo" in browser_smoke


def test_google_places_cloud_policy_is_production_only_and_observation_scaled() -> None:
    root = Path(__file__).parents[1]
    guardrails = (root / "infra" / "billing-guardrails.json").read_text(encoding="utf-8")
    apply_script = (root / "infra" / "gcp" / "apply-billing-guardrails.ps1").read_text(
        encoding="utf-8"
    )
    control_script = (root / "infra" / "gcp" / "set-google-places-access.ps1").read_text(
        encoding="utf-8"
    )

    assert guardrails.count('"placesEnabled": false') == 2
    assert guardrails.count('"placesEnabled": true') == 1
    assert (
        '"quotaId": "SearchTextRequestPerDayPerProject", '
        '"local": 1, "canary": 1, "prod": 100'
    ) in guardrails
    assert (
        '"quotaId": "GetPhotoMediaRequestPerDayPerProject", '
        '"local": 1, "canary": 1, "prod": 200'
    ) in guardrails
    assert "Where-Object { $_ -ne $placesService }" in apply_script
    assert '"services", "disable", $placesService' in apply_script
    assert '"quotas", "preferences", "update", $preferenceId' in apply_script
    assert "kept tighter" in apply_script
    assert "$AllowQuotaIncreases" in apply_script
    assert "APPROVE_GOOGLE_PLACES_SPEND" in control_script
    assert "central desired state" in control_script


def test_billing_shutoff_trigger_can_invoke_its_cloud_run_service() -> None:
    root = Path(__file__).parents[1]
    guardrails = (root / "infra" / "billing-guardrails.json").read_text(encoding="utf-8")
    apply_script = (
        root / "infra" / "gcp" / "apply-billing-guardrails.ps1"
    ).read_text(encoding="utf-8")

    assert '"functions", "delete", "billing-shutoff"' in apply_script
    assert "--trigger-service-account=$sa" in apply_script
    assert "--member=serviceAccount:$triggerServiceAccount" in apply_script
    assert "APPROVE_ACCOUNT_WIDE_BILLING_SHUTOFF" in apply_script
    assert '"shutoffEnabled": false' in guardrails


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


def test_production_repairs_missing_canary_gate_before_approval() -> None:
    production = (
        Path(__file__).parents[1] / "infra" / "deploy-prod.ps1"
    ).read_text(encoding="utf-8")

    git_resolution = production.index("git rev-parse --short HEAD")
    canary_check = production.index("$canaryImageMatches")
    canary_deploy = production.index('"$PSScriptRoot/deploy-canary.ps1"')
    approval = production.index('$approval = Read-Host "Enter approval code"')

    assert git_resolution < canary_check < canary_deploy < approval
    assert "Test-CanaryImageVerified" in production
    assert "Canary deployment or smoke verification failed" in production
    assert "Dry run cannot repair the canary gate" in production
    assert "Production cannot rebuild an image after canary verification" in production
    assert '"-NamePrefix", $CanaryNamePrefix' in production
    assert "if ($canaryImageMatches)" in production
    assert "no canary redeploy was required" in production
    assert "$uniqueCanaryImages = @($canaryImages | Select-Object -Unique)" in production


def test_image_push_requires_fresh_publish_authentication_before_build() -> None:
    script = (
        Path(__file__).parents[1] / "infra" / "push-image.ps1"
    ).read_text(encoding="utf-8")

    login = script.index("docker login $Registry")
    build = script.index('Invoke-LoggedNative -FilePath "docker" -ArgumentList $buildArgs')

    assert login < build
    assert "assuming an existing session" not in script
    assert "gh auth token --hostname github.com" in script
    assert '$ghLogin -eq $GhcrUser -and $ghScopes -contains "write:packages"' in script
    assert 'docker manifest inspect "$repo`:latest"' in script
    assert "Docker credential store" in script
    assert '"build", "--platform", "linux/amd64"' in script
    assert "gh auth refresh -h github.com -s write:packages" in script


def test_container_app_job_name_stays_within_azure_limit() -> None:
    template = (Path(__file__).parents[1] / "infra" / "main.bicep").read_text(
        encoding="utf-8"
    )

    assert "var publicDemoJobName = '${namePrefix}-demo-refresh-${take(suffix, 8)}'" in template
    assert "var publicDemoJobName = '${namePrefix}-public-demo-refresh-${suffix}'" not in template
