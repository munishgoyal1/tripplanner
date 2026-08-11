#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Deploy to PRODUCTION environment (requires manual approval)

.DESCRIPTION
  Deploys changes to production ONLY with explicit approval.
  Displays a readiness checklist and requires you to type APPROVE_PROD_DEPLOYMENT.
  All prod deployments are logged with timestamp and approval confirmation.

.EXAMPLE
  ./infra/deploy-prod.ps1
  
  # After reviewing the checklist, you must type exactly:
  # > APPROVE_PROD_DEPLOYMENT
#>

param(
    [string]$ImageTag = "",
    [switch]$Build = $false,
    [switch]$DryRun = $false,
    [string]$SubscriptionId = "",
    [string]$ResourceGroup = "rg-tripplanner-prod",
    [string]$NamePrefix = "prod",
    [string]$Location = "eastus2",
    [string]$BicepFile = "infra/main.bicep",
    [string]$BicepParams = "infra/prod.bicepparam",
    [string]$CosmosResourceGroup = "rg-tripplanner-data",
    [string]$CosmosAccountName = "",
    [string]$AzureOpenAIAccountName = "aoaiprodmd1ks",
    [string]$OAuthRedirectBase = "https://aitripplanner.co/api",
    [string]$CanaryResourceGroup = "rg-tripplanner-canary",
    [string]$CanaryNamePrefix = "canary",
    [string]$CanaryAppNamePrefix = "",
    [string]$EnvFile = ".env.prod"
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot/deployment-common.ps1"
Start-RunLog -Name "prod-deploy" | Out-Null

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) {
        throw "Could not select Azure subscription $SubscriptionId."
    }
}

$imageTagWasExplicit = -not [string]::IsNullOrWhiteSpace($ImageTag)
if (-not $imageTagWasExplicit) {
    $ImageTag = (git rev-parse --short HEAD 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ImageTag)) {
        throw "Could not resolve the current Git commit for the immutable image tag."
    }
}
if ($ImageTag -eq "latest") {
    throw "Production requires an immutable image tag. Deploy a SHA to canary or pass -ImageTag <sha>."
}
if ($Build) {
    throw "Production cannot rebuild an image after canary verification. Let the canary gate build the current SHA or pass an existing -ImageTag <sha>."
}
if ([string]::IsNullOrWhiteSpace($CanaryAppNamePrefix)) {
    $CanaryAppNamePrefix = "${CanaryNamePrefix}-app-"
} elseif (-not $PSBoundParameters.ContainsKey("CanaryNamePrefix") -and $CanaryAppNamePrefix -match '^(.*)-app-$') {
    $CanaryNamePrefix = $matches[1]
} elseif ($CanaryAppNamePrefix -ne "${CanaryNamePrefix}-app-") {
    throw "CanaryNamePrefix and CanaryAppNamePrefix identify different Container Apps."
}

$imagePrefix = "ghcr.io/munishgoyal1/tripplanner:"
$canaryHistoryLog = Join-Path (Get-PrimaryRepoRoot) "logs/deployments-canary.log"

function Get-CanaryImages {
    $images = @(az containerapp list `
        --resource-group $CanaryResourceGroup `
        --query "[?starts_with(name, '$CanaryAppNamePrefix')].properties.template.containers[0].image" `
        --output tsv)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect canary images in $CanaryResourceGroup."
    }
    return @($images | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Test-CanaryImageVerified {
    if (-not (Test-Path $canaryHistoryLog)) {
        return $false
    }
    return [bool](Select-String `
        -Path $canaryHistoryLog `
        -SimpleMatch "Image: ${imagePrefix}${ImageTag}" `
        -Quiet)
}

$canaryImages = @(Get-CanaryImages)
$uniqueCanaryImages = @($canaryImages | Select-Object -Unique)
$canaryImageMatches = $uniqueCanaryImages.Count -eq 1 -and $uniqueCanaryImages[0] -eq "${imagePrefix}${ImageTag}"
$canarySmokeVerified = Test-CanaryImageVerified

if ($canaryImageMatches) {
    if ($canarySmokeVerified) {
        Write-Host "[canary] Current release $ImageTag is deployed and has passing smoke evidence."
    } else {
        Write-Host -ForegroundColor Yellow "[canary] Current release $ImageTag is already deployed. Local smoke evidence is missing, so no canary redeploy was required."
    }
} else {
    $reasons = @()
    if (-not $canaryImageMatches) {
        $deployed = if ($canaryImages.Count -eq 0) { "none" } else { $canaryImages -join ", " }
        $reasons += "deployed image is $deployed"
    }
    if (-not $canarySmokeVerified) {
        $reasons += "passing smoke evidence is missing"
    }
    Write-Host -ForegroundColor Yellow "[canary] Release $ImageTag is not ready: $($reasons -join '; ')."

    if ($DryRun) {
        throw "Dry run cannot repair the canary gate. Deploy and verify $ImageTag in canary, then retry."
    }

    Write-Host "[canary] Deploying and verifying $ImageTag before production approval..."
    $canaryArguments = @(
        "-NoProfile",
        "-File", "$PSScriptRoot/deploy-canary.ps1",
        "-ImageTag", $ImageTag,
        "-ResourceGroup", $CanaryResourceGroup,
        "-NamePrefix", $CanaryNamePrefix
    )
    if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
        $canaryArguments += @("-SubscriptionId", $SubscriptionId)
    }
    if ($imageTagWasExplicit -or $canaryImageMatches) {
        $canaryArguments += "-NoBuild"
    }

    & pwsh @canaryArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Canary deployment or smoke verification failed. Production promotion is blocked."
    }

    $canaryImages = @(Get-CanaryImages)
    $uniqueCanaryImages = @($canaryImages | Select-Object -Unique)
    $canaryImageMatches = $uniqueCanaryImages.Count -eq 1 -and $uniqueCanaryImages[0] -eq "${imagePrefix}${ImageTag}"
    if (-not $canaryImageMatches -or -not (Test-CanaryImageVerified)) {
        throw "Canary did not retain verified image ${imagePrefix}${ImageTag}. Production promotion is blocked."
    }
    Write-Host "[canary] Deployment and smoke verification passed for $ImageTag."
}

Import-DeploymentEnvironment -Path $EnvFile

# Configuration
$prodRG = $ResourceGroup
$prodPrefix = $NamePrefix
$bicepFile = $BicepFile
$bicepParams = $BicepParams

Write-Host "`n╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ⚠️  PRODUCTION DEPLOYMENT — APPROVAL GATE               ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "Environment: PRODUCTION (rg-tripplanner-prod)"
Write-Host "App Prefix: ${prodPrefix}-app-*"
Write-Host "Image Tag: $ImageTag`n"

# Display readiness checklist
Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  PRE-DEPLOYMENT CHECKLIST — VERIFY ALL BEFORE PROCEEDING ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

$checklist = @(
    "Exact immutable image tag deployed to canary",
    "Read-only and deep canary smoke suites passed",
    "Critical and changed workflows manually verified",
    "Canary bake period completed with acceptable telemetry",
    "Email endpoint tested end-to-end (test send successful)",
    "Database migrations validated (if any)",
    "Secrets/config parity confirmed between canary and prod",
    "Rollback plan documented and tested",
    "Team notified of planned deployment",
    "You have backups/recovery plan in place",
    "This is your explicit decision to promote to production"
)

for ($i = 0; $i -lt $checklist.Count; $i++) {
    Write-Host " ☐ $($checklist[$i])"
}

Write-Host "`n"

# Approval gate
Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  🔐 APPROVAL REQUIRED                                     ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "This will deploy to PRODUCTION and affect all users."
Write-Host "Type exactly (case-sensitive): APPROVE_PROD_DEPLOYMENT`n"
Write-Host -ForegroundColor Yellow "If you're not ready, press Ctrl+C now.`n"

$approval = Read-Host "Enter approval code"

if ($approval -ne "APPROVE_PROD_DEPLOYMENT") {
    Write-Host "`n❌ Approval DENIED. Deployment aborted."
    Write-Host "   (You entered: '$approval')`n"
    exit 1
}

Write-Host "`n✓ Approval confirmed. Proceeding with production deployment...`n"

# Step 1: Validate prerequisites
Write-Host "✓ Step 1: Validating prerequisites..."
if (-not (Test-Path $bicepFile)) {
    throw "Bicep file not found: $bicepFile"
}
if (-not (Test-Path $bicepParams)) {
    throw "Bicep params not found: $bicepParams"
}
if ([string]::IsNullOrWhiteSpace($CosmosAccountName)) {
    $cosmosAccounts = @(az cosmosdb list -g $CosmosResourceGroup --query "[].name" -o tsv)
    if ($cosmosAccounts.Count -ne 1) {
        throw "Expected exactly one shared Cosmos account in $CosmosResourceGroup; found $($cosmosAccounts.Count). Pass -CosmosAccountName explicitly."
    }
    $CosmosAccountName = $cosmosAccounts[0]
}
if ([string]::IsNullOrWhiteSpace($CosmosAccountName)) {
    throw "No shared Cosmos account found in $CosmosResourceGroup. Run ./infra/deploy-data.ps1 after approval."
}
az cosmosdb show -g $CosmosResourceGroup -n $CosmosAccountName -o none
if ($LASTEXITCODE -ne 0) {
    throw "Shared Cosmos account $CosmosAccountName is not accessible."
}
az cosmosdb sql database show -g $CosmosResourceGroup -a $CosmosAccountName -n tripplanner-prod -o none
if ($LASTEXITCODE -ne 0) {
    throw "Required database tripplanner-prod does not exist in $CosmosAccountName."
}
$resourceGroupExists = az group exists --name $prodRG | ConvertFrom-Json
if ($DryRun -and -not $resourceGroupExists) {
    throw "Dry run cannot target missing resource group $prodRG without creating it. Create the group separately after approval, then rerun."
}
if (-not $resourceGroupExists) {
    az group create --name $prodRG --location $Location -o none
}
$azureOpenAiApiKey = az cognitiveservices account keys list `
    --resource-group $prodRG `
    --name $AzureOpenAIAccountName `
    --query key1 `
    --output tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($azureOpenAiApiKey)) {
    throw "Could not read the API key for Azure OpenAI account $AzureOpenAIAccountName in $prodRG."
}
$env:AZURE_OPENAI_API_KEY = $azureOpenAiApiKey
if ([string]::IsNullOrWhiteSpace($OAuthRedirectBase)) {
    $appFqdns = @(az containerapp list `
        --resource-group $prodRG `
        --query "[?starts_with(name, '${prodPrefix}-app-')].properties.configuration.ingress.fqdn" `
        --output tsv)
    if ($appFqdns.Count -gt 1) {
        throw "Multiple Container Apps match ${prodPrefix}-app-* in $prodRG. Pass -OAuthRedirectBase explicitly."
    }
    if ($appFqdns.Count -eq 1 -and -not [string]::IsNullOrWhiteSpace($appFqdns[0])) {
        $OAuthRedirectBase = "https://$($appFqdns[0])/api"
    }
}
if (-not [string]::IsNullOrWhiteSpace($OAuthRedirectBase) -and $OAuthRedirectBase -notmatch '^https://') {
    throw "Hosted OAuth redirect base must use HTTPS: $OAuthRedirectBase"
}
Write-Host "  ✓ Files exist`n"

# Step 2: Validate Bicep
Write-Host "✓ Step 2: Validating Bicep template..."
$validation = az deployment group validate `
    --resource-group $prodRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$prodPrefix" "cosmosResourceGroupName=$CosmosResourceGroup" "cosmosAccountName=$CosmosAccountName" "oauthRedirectBase=$OAuthRedirectBase" `
    2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Bicep validation failed: $validation"
}
Write-Host "  ✓ Template is valid`n"

# Step 3: Dry run (optional)
if ($DryRun) {
    Write-Host "✓ Step 3: Performing DRY RUN (no changes)..."
    az deployment group what-if `
        --resource-group $prodRG `
        --template-file $bicepFile `
        --parameters $bicepParams `
        --parameters "namePrefix=$prodPrefix" "cosmosResourceGroupName=$CosmosResourceGroup" "cosmosAccountName=$CosmosAccountName" "oauthRedirectBase=$OAuthRedirectBase" | Out-String
    Write-Host "  ✓ Dry run completed`n"
    exit 0
}

Write-Host "✓ Step 3: Checking infrastructure changes..."
$rawWhatIf = az deployment group what-if `
    --resource-group $prodRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$prodPrefix" "cosmosResourceGroupName=$CosmosResourceGroup" "cosmosAccountName=$CosmosAccountName" "oauthRedirectBase=$OAuthRedirectBase" `
    --result-format ResourceIdOnly `
    --no-pretty-print `
    --only-show-errors `
    --output json 2>$null | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "Production infrastructure what-if failed."
}
$whatIf = ConvertFrom-AzureCliJson -Output $rawWhatIf -Action "Production what-if"
Assert-DeploymentHasNoDeletes -WhatIf $whatIf -EnvironmentName "Production"
Write-Host "  ✓ What-if contains no deletes`n"

# Step 4: Deploy
Write-Host "✓ Step 3: Deploying to PRODUCTION..."
$rawDeploy = az deployment group create `
    --resource-group $prodRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$prodPrefix" "cosmosResourceGroupName=$CosmosResourceGroup" "cosmosAccountName=$CosmosAccountName" "oauthRedirectBase=$OAuthRedirectBase" `
    --only-show-errors `
    --query "{state:properties.provisioningState, containerAppUrl:properties.outputs.containerAppUrl.value, containerAppName:properties.outputs.containerAppName.value}" `
    --output json 2>&1 | Out-String
$deployExitCode = $LASTEXITCODE
if ($deployExitCode -ne 0) {
    throw "Production infrastructure deployment failed. Azure CLI output:`n$rawDeploy"
}

$deployment = ConvertFrom-AzureCliJson -Output $rawDeploy -Action "Deployment"

if ($deployment.state -ne "Succeeded") {
    throw "Deployment failed: $($deployment.state)"
}
Write-Host "  ✓ Infrastructure deployed`n"

if ([string]::IsNullOrWhiteSpace($OAuthRedirectBase)) {
    $OAuthRedirectBase = "$($deployment.containerAppUrl.TrimEnd('/'))/api"
}

# Step 5: Always set app image so deployments never stay on the hello-world default.
Write-Host "✓ Step 4: Updating Container App image to $ImageTag..."
az containerapp update `
    --resource-group $prodRG `
    --name $deployment.containerAppName `
    --image "ghcr.io/munishgoyal1/tripplanner:$ImageTag" `
    --set-env-vars "OAUTH_REDIRECT_BASE=$OAuthRedirectBase" `
    -o none
if ($LASTEXITCODE -ne 0) {
    throw "Container App image update failed."
}
Write-Host "  ✓ Image updated`n"

Write-Host "✓ Step 5: Running read-only hosted smoke tests..."
$expectedOAuthCallback = "$($OAuthRedirectBase.TrimEnd('/'))/auth/callback/google"
& "$PSScriptRoot/smoke-hosted.ps1" `
    -Environment production `
    -BaseUrl $deployment.containerAppUrl `
    -ExpectedOAuthCallback $expectedOAuthCallback
if ($LASTEXITCODE -ne 0) {
    throw "Production smoke tests failed. Run ./infra/rollback-prod.ps1 after confirming the failure."
}
Write-Host "  ✓ Production smoke tests passed`n"

# Step 6: Output results
Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ✓ PRODUCTION DEPLOYMENT COMPLETE                        ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "App URL: $($deployment.containerAppUrl)"
Write-Host "Environment: PRODUCTION"
Write-Host "Resource Group: $prodRG"
Write-Host "Container App: $($deployment.containerAppName)"
Write-Host "Image: ghcr.io/munishgoyal1/tripplanner:$ImageTag`n"

# Log deployment
$historyLog = Join-Path (Get-PrimaryRepoRoot) "logs/deployments-prod.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $historyLog) | Out-Null
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$approver = Get-DeploymentUser
Add-Content $historyLog "[$timestamp] APPROVED by $approver | RG: $prodRG | Image: ghcr.io/munishgoyal1/tripplanner:$ImageTag | Status: SUCCESS"

Write-Host "✓ Logged to $historyLog"
Write-Host "✓ All users can now access the production deployment`n"

# Post-deployment validation hint
Write-Host "Next steps:"
Write-Host "  1. Monitor production logs: az containerapp logs show -g $prodRG -n $($deployment.containerAppName)"
Write-Host "  2. Test critical flows (chat, map, email)"
Write-Host "  3. If issues arise, run: ./infra/rollback-prod.ps1`n"
Stop-RunLog

