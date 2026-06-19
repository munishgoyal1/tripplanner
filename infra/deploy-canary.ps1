#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Deploy to CANARY environment (no approval needed, for testing)

.DESCRIPTION
  Deploys the latest changes to the canary RG for testing before prod.
  No approval gate — use for all testing, bug fixes, and feature development.

.EXAMPLE
  ./infra/deploy-canary.ps1
#>

param(
    [string]$ImageTag = "latest",
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path = ".env")

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()

            if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, 'Process'))) {
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
                Set-Item -Path "Env:$name" -Value $value
            }
        }
    }
}

Import-DotEnv

# Configuration
$canaryRG = "rg-multiagent-canary"
$canaryPrefix = "canary"
$canaryApp = "${canaryPrefix}-app"
$bicepFile = "infra/main.bicep"
$bicepParams = "infra/main.bicepparam"

Write-Host "`n╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  🧪 CANARY DEPLOYMENT — No Approval Required             ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "Environment: CANARY (rg-multiagent-canary)"
Write-Host "App: $canaryApp"
Write-Host "Image Tag: $ImageTag`n"

# Step 1: Validate prerequisites
Write-Host "✓ Step 1: Validating prerequisites..."
if (-not (Test-Path $bicepFile)) {
    throw "Bicep file not found: $bicepFile"
}
if (-not (Test-Path $bicepParams)) {
    throw "Bicep params not found: $bicepParams"
}
az group create --name $canaryRG --location eastus2 -o none
Write-Host "  ✓ Files exist`n"

# Step 2: Validate Bicep
Write-Host "✓ Step 2: Validating Bicep template..."
$validation = az deployment group validate `
    --resource-group $canaryRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$canaryPrefix" "enableCosmosFreeTier=false" `
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
        --parameters "namePrefix=$canaryPrefix" "enableCosmosFreeTier=false" | Out-String
    Write-Host "  ✓ Dry run completed`n"
    exit 0
}

# Step 4: Deploy
Write-Host "✓ Step 3: Deploying to CANARY..."
$deployment = az deployment group create `
    --resource-group $canaryRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$canaryPrefix" "enableCosmosFreeTier=false" `
    --only-show-errors `
    --query "{state:properties.provisioningState, containerAppUrl:properties.outputs.containerAppUrl.value}" `
    --output json 2>$null | ConvertFrom-Json

if ($deployment.state -ne "Succeeded") {
    throw "Deployment failed: $($deployment.state)"
}
Write-Host "  ✓ Infrastructure deployed`n"

# Step 5: Update image tag (if not 'latest')
if ($ImageTag -ne "latest") {
    Write-Host "✓ Step 4: Updating Container App image to $ImageTag..."
    az containerapp update `
        --resource-group $canaryRG `
        --name $canaryApp `
        --image "ghcr.io/munishgoyal1/multiagent:$ImageTag" `
        -o none
    Write-Host "  ✓ Image updated`n"
}

# Step 6: Output results
Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ✓ CANARY DEPLOYMENT COMPLETE                            ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "App URL: https://$($deployment.containerAppUrl)"
Write-Host "Resource Group: $canaryRG"
Write-Host "`nNext: Test the canary app, then use ./infra/deploy-prod.ps1 to promote"
Write-Host "       if all tests pass and you're ready for production.`n"

# Log deployment
$logDir = "logs"
if (-not (Test-Path $logDir)) { mkdir $logDir -Force | Out-Null }
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content "logs/deployments-canary.log" "[$timestamp] Deployed canary | RG: $canaryRG | Image: ghcr.io/munishgoyal1/multiagent:$ImageTag | By: $env:USERNAME"
Write-Host "✓ Logged to logs/deployments-canary.log`n"
