#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Deploy to CANARY environment (no approval needed, for testing)

.DESCRIPTION
    Deploys the current Git commit to the canary RG for testing before prod.
  No approval gate — use for all testing, bug fixes, and feature development.
  Builds & pushes the image from current code first by default (pass -NoBuild
    with -ImageTag to deploy an existing immutable image).

.EXAMPLE
  ./infra/deploy-canary.ps1
#>

param(
    [string]$ImageTag = "latest",
    [switch]$NoBuild = $false,
    [switch]$DryRun = $false,
    [string]$SubscriptionId = "",
    [string]$ResourceGroup = "rg-tripplanner-canary",
    [string]$NamePrefix = "canary",
    [string]$Location = "eastus2",
    [string]$BicepFile = "infra/main.bicep",
    [string]$BicepParams = "infra/canary.bicepparam",
    [string]$CosmosResourceGroup = "rg-tripplanner-data",
    [string]$CosmosAccountName = "",
    [string]$AzureOpenAIAccountName = "aoaicanarymd1ks",
    [string]$OAuthRedirectBase = "",
    [string]$EnvFile = ".env.canary"
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot/deployment-common.ps1"
Import-DeploymentEnvironment -Path $EnvFile

if (-not $NoBuild -and $ImageTag -eq "latest") {
    $ImageTag = (git rev-parse --short HEAD 2>$null)
    if ([string]::IsNullOrWhiteSpace($ImageTag)) {
        throw "Could not resolve the current Git commit for the immutable image tag."
    }
}

# Configuration
$canaryRG = $ResourceGroup
$canaryPrefix = $NamePrefix
$bicepFile = $BicepFile
$bicepParams = $BicepParams

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    az account set --subscription $SubscriptionId
}

Write-Host "`n╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  🧪 CANARY DEPLOYMENT — No Approval Required             ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "Environment: CANARY (rg-tripplanner-canary)"
Write-Host "App Prefix: ${canaryPrefix}-app-*"
Write-Host "Image Tag: $ImageTag`n"

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
az cosmosdb sql database show -g $CosmosResourceGroup -a $CosmosAccountName -n tripplanner-canary -o none
if ($LASTEXITCODE -ne 0) {
    throw "Required database tripplanner-canary does not exist in $CosmosAccountName."
}
$resourceGroupExists = az group exists --name $canaryRG | ConvertFrom-Json
if ($DryRun -and -not $resourceGroupExists) {
    throw "Dry run cannot target missing resource group $canaryRG without creating it. Create the group separately after approval, then rerun."
}
if (-not $resourceGroupExists) {
    az group create --name $canaryRG --location $Location -o none
}
$azureOpenAiApiKey = az cognitiveservices account keys list `
    --resource-group $canaryRG `
    --name $AzureOpenAIAccountName `
    --query key1 `
    --output tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($azureOpenAiApiKey)) {
    throw "Could not read the API key for Azure OpenAI account $AzureOpenAIAccountName in $canaryRG."
}
$env:AZURE_OPENAI_API_KEY = $azureOpenAiApiKey
if ([string]::IsNullOrWhiteSpace($OAuthRedirectBase)) {
    $appFqdns = @(az containerapp list `
        --resource-group $canaryRG `
        --query "[?starts_with(name, '${canaryPrefix}-app-')].properties.configuration.ingress.fqdn" `
        --output tsv)
    if ($appFqdns.Count -gt 1) {
        throw "Multiple Container Apps match ${canaryPrefix}-app-* in $canaryRG. Pass -OAuthRedirectBase explicitly."
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
    --resource-group $canaryRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$canaryPrefix" "cosmosResourceGroupName=$CosmosResourceGroup" "cosmosAccountName=$CosmosAccountName" "oauthRedirectBase=$OAuthRedirectBase" `
    2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Bicep validation failed: $validation"
}
Write-Host "  ✓ Template is valid`n"

# Step 3: Dry run (optional)
if ($DryRun) {
    Write-Host "✓ Step 3: Performing DRY RUN (no changes)..."
    az deployment group what-if `
        --resource-group $canaryRG `
        --template-file $bicepFile `
        --parameters $bicepParams `
        --parameters "namePrefix=$canaryPrefix" "cosmosResourceGroupName=$CosmosResourceGroup" "cosmosAccountName=$CosmosAccountName" "oauthRedirectBase=$OAuthRedirectBase" | Out-String
    Write-Host "  ✓ Dry run completed`n"
    exit 0
}

Write-Host "✓ Step 3: Checking infrastructure changes..."
$rawWhatIf = az deployment group what-if `
    --resource-group $canaryRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$canaryPrefix" "cosmosResourceGroupName=$CosmosResourceGroup" "cosmosAccountName=$CosmosAccountName" "oauthRedirectBase=$OAuthRedirectBase" `
    --result-format ResourceIdOnly `
    --no-pretty-print `
    --only-show-errors `
    --output json 2>$null | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "Canary infrastructure what-if failed."
}
$whatIf = ConvertFrom-AzureCliJson -Output $rawWhatIf -Action "Canary what-if"
Assert-DeploymentHasNoDeletes -WhatIf $whatIf -EnvironmentName "Canary"
Write-Host "  ✓ What-if contains no deletes`n"

# Build + push only after all no-change paths have exited.
if (-not $NoBuild) {
    Write-Host "✓ Step 0: Building & pushing image from current code..."
    & "$PSScriptRoot/push-image.ps1" -Tag $ImageTag
    if ($LASTEXITCODE -ne 0) { throw "Image build/push failed." }
    Write-Host "  ✓ Image ready`n"
}

# Step 4: Deploy
Write-Host "✓ Step 3: Deploying to CANARY..."
$rawDeploy = az deployment group create `
    --resource-group $canaryRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$canaryPrefix" "cosmosResourceGroupName=$CosmosResourceGroup" "cosmosAccountName=$CosmosAccountName" "oauthRedirectBase=$OAuthRedirectBase" `
    --only-show-errors `
    --query "{state:properties.provisioningState, containerAppUrl:properties.outputs.containerAppUrl.value, containerAppName:properties.outputs.containerAppName.value}" `
    --output json 2>&1 | Out-String
$deployExitCode = $LASTEXITCODE
if ($deployExitCode -ne 0) {
    throw "Canary infrastructure deployment failed. Azure CLI output:`n$rawDeploy"
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
    --resource-group $canaryRG `
    --name $deployment.containerAppName `
    --image "ghcr.io/munishgoyal1/tripplanner:$ImageTag" `
    --set-env-vars "OAUTH_REDIRECT_BASE=$OAuthRedirectBase" `
    -o none
if ($LASTEXITCODE -ne 0) {
    throw "Container App image update failed."
}
Write-Host "  ✓ Image updated`n"

Write-Host "✓ Step 5: Running hosted smoke tests..."
$expectedOAuthCallback = "$($OAuthRedirectBase.TrimEnd('/'))/auth/callback/google"
& "$PSScriptRoot/smoke-hosted.ps1" `
    -Environment canary `
    -BaseUrl $deployment.containerAppUrl `
    -ExpectedOAuthCallback $expectedOAuthCallback
if ($LASTEXITCODE -ne 0) {
    throw "Canary smoke tests failed. Production promotion is blocked."
}
Write-Host "  ✓ Canary smoke tests passed`n"

# Step 6: Output results
Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ✓ CANARY DEPLOYMENT COMPLETE                            ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "App URL: $($deployment.containerAppUrl)"
Write-Host "Container App: $($deployment.containerAppName)"
Write-Host "Resource Group: $canaryRG"
Write-Host "`nNext: Test the canary app, then use ./infra/deploy-prod.ps1 to promote"
Write-Host "       if all tests pass and you're ready for production.`n"

# Log deployment
$logDir = "logs"
if (-not (Test-Path $logDir)) { mkdir $logDir -Force | Out-Null }
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content "logs/deployments-canary.log" "[$timestamp] Deployed canary | RG: $canaryRG | Image: ghcr.io/munishgoyal1/tripplanner:$ImageTag | By: $env:USERNAME"
Write-Host "✓ Logged to logs/deployments-canary.log`n"

