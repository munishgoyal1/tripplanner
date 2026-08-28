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
    assert '[string]$ConfigFile = "config/environments/canary.env"' in canary
    assert '[string]$ConfigFile = "config/environments/prod.env"' in production
    assert "Import-DeploymentEnvironment -Path $ConfigFile" in canary
    assert "Import-DeploymentEnvironment -Path $ConfigFile" in production
    assert "Import-DeploymentEnvironment -Path $EnvFile" in canary
    assert "Import-DeploymentEnvironment -Path $EnvFile" in production
    assert canary.index("-Path $ConfigFile") < canary.index("-Path $EnvFile")
    assert production.index("-Path $ConfigFile") < production.index("-Path $EnvFile")
    assert '$OAuthRedirectBase = $env:OAUTH_REDIRECT_BASE' in canary
    assert '$OAuthRedirectBase = $env:OAUTH_REDIRECT_BASE' in production
    assert '[string]$OAuthRedirectBase = ""' in production


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
    assert '"--environment=$Environment"' in smoke
    assert "window.gm_authFailure" in browser_smoke
    assert "new window.google.maps.Map" in browser_smoke
    assert "/api/auth/guest/session" in browser_smoke
    assert "Authorization: `Bearer ${guestToken}`" in browser_smoke
    assert "/api/destination/overview?destination=Paris&news=false" in browser_smoke
    assert 'environment === "canary"' in browser_smoke
    assert "Google Places is intentionally disabled in canary" in browser_smoke
    assert "destination overview returned no photo" in browser_smoke


def test_google_api_cloud_policy_comes_from_disabled_runtime_profiles() -> None:
    root = Path(__file__).parents[1]
    guardrails = (root / "infra" / "billing-guardrails.json").read_text(encoding="utf-8")
    apply_script = (root / "infra" / "gcp" / "apply-billing-guardrails.ps1").read_text(
        encoding="utf-8"
    )
    control_script = (root / "infra" / "gcp" / "set-google-places-access.ps1").read_text(
        encoding="utf-8"
    )
    shared_control = (root / "infra" / "gcp" / "set-google-api-access.ps1").read_text(
        encoding="utf-8"
    )
    control_contract = (
        root / "infra" / "gcp" / "google-api-control-common.ps1"
    ).read_text(encoding="utf-8")

    assert "placesEnabled" not in guardrails
    for environment in ("local", "canary", "prod"):
        profile = (root / "config" / "environments" / f"{environment}.env").read_text(
            encoding="utf-8"
        )
        assert "ENABLE_GOOGLE_PLACES=0" in profile
        assert "ENABLE_GOOGLE_MAPS=0" in profile
    assert (
        '"quotaId": "SearchTextRequestPerDayPerProject", '
        '"local": 1, "canary": 1, "prod": 100'
    ) in guardrails
    assert (
        '"quotaId": "GetPhotoMediaRequestPerDayPerProject", '
        '"local": 1, "canary": 1, "prod": 200'
    ) in guardrails
    assert "Get-GoogleApiDesiredState" in apply_script
    assert "$GooglePlacesApproval" in apply_script
    assert "$GoogleMapsApproval" in apply_script
    assert '"quotas", "preferences", "update", $preferenceId' in apply_script
    assert "kept tighter" in apply_script
    assert "$AllowQuotaIncreases" in apply_script
    assert "set-google-api-access.ps1" in control_script
    assert "APPROVE_GOOGLE_PLACES_SPEND" in control_contract
    assert "APPROVE_GOOGLE_MAPS_SPEND" in control_contract
    assert "routes.googleapis.com" in control_contract
    assert "static-maps-backend.googleapis.com" in control_contract
    assert "maps-backend.googleapis.com" in control_contract
    assert "Set-GoogleApiDesiredState" in shared_control
    assert "No application deployment was performed." in shared_control


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


def test_azure_services_control_is_scoped_reversible_and_approval_gated() -> None:
    root = Path(__file__).parents[1]
    control = (
        root / "infra" / "azure" / "set-azure-services-access.ps1"
    ).read_text(encoding="utf-8")

    assert "APPROVE_AZURE_DISABLE" in control
    assert "APPROVE_AZURE_SPEND" in control
    assert "munishgoyal1@gmail.com" in control
    assert "Visual Studio Enterprise Subscription" in control
    assert "config.azure.environments" in control
    assert '[ValidateSet("all", "local", "canary", "prod")]' in control
    assert '$Environment -eq "all" -or $_.name -eq $Environment' in control
    assert '$Environment -eq "all" -and $config.azure.actionGroupResourceGroup' in control
    assert "Cosmos serves local, canary, and prod" in control
    assert "Microsoft.App/containerApps" in control
    assert "Microsoft.App/jobs" in control
    assert "Microsoft.CognitiveServices/accounts" in control
    assert "Microsoft.DocumentDB/databaseAccounts" in control
    assert "Microsoft.Cache/redisEnterprise" in control
    assert "tripplannerControlOriginalTrigger" in control
    assert "public-network-access" in control
    assert '"delete"' not in control.lower()
    assert "never deletes resources or data" in control


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


def test_production_cache_sync_defaults_to_approval_gated_two_way_merge() -> None:
    script = (
        Path(__file__).parents[1] / "scripts" / "prod-cache-sync.ps1"
    ).read_text(encoding="utf-8")

    approval_gate = script.index('if ($Approval -ne "APPROVE_PROD_CACHE_SYNC")')
    credential = script.index("$env:TRIPPLANNER_PROD_COSMOS_KEY = az cosmosdb keys list")

    assert '[string]$Direction = "Both"' in script
    assert '$writesProduction = $Direction -in @("Push", "Both") -and -not $WhatIf' in script
    assert approval_gate < credential
    assert '$apply = $Direction -ne "Status" -and -not $WhatIf' in script
    assert '"--checkpoint", $CheckpointPath' in script
    assert '"--watermark-overlap-seconds", $WatermarkOverlapSeconds' in script
    assert 'if ($FullScan)' in script


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
