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
    [string]$ImageTag = "latest",
    [switch]$DryRun = $false,
    [string]$SubscriptionId = "",
    [string]$ResourceGroup = "rg-tripplanner-prod",
    [string]$NamePrefix = "prod",
    [string]$Location = "eastus2",
    [string]$BicepFile = "infra/main.bicep",
    [string]$BicepParams = "infra/main.bicepparam",
    [bool]$EnableCosmosFreeTier = $false
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
$prodRG = $ResourceGroup
$prodPrefix = $NamePrefix
$bicepFile = $BicepFile
$bicepParams = $BicepParams

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    az account set --subscription $SubscriptionId
}

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
    "Canary environment tested and stable",
    "All critical features verified",
    "No canary errors or exceptions (last 24 hours)",
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
az group create --name $prodRG --location $Location -o none
Write-Host "  ✓ Files exist`n"

# Step 2: Validate Bicep
Write-Host "✓ Step 2: Validating Bicep template..."
$validation = az deployment group validate `
    --resource-group $prodRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$prodPrefix" "enableCosmosFreeTier=$EnableCosmosFreeTier" `
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
        --parameters "namePrefix=$prodPrefix" "enableCosmosFreeTier=$EnableCosmosFreeTier" | Out-String
    Write-Host "  ✓ Dry run completed`n"
    exit 0
}

# Step 4: Deploy
Write-Host "✓ Step 3: Deploying to PRODUCTION..."
$deployment = az deployment group create `
    --resource-group $prodRG `
    --template-file $bicepFile `
    --parameters $bicepParams `
    --parameters "namePrefix=$prodPrefix" "enableCosmosFreeTier=$EnableCosmosFreeTier" `
    --only-show-errors `
    --query "{state:properties.provisioningState, containerAppUrl:properties.outputs.containerAppUrl.value, containerAppName:properties.outputs.containerAppName.value}" `
    --output json 2>$null | ConvertFrom-Json

if ($deployment.state -ne "Succeeded") {
    throw "Deployment failed: $($deployment.state)"
}
Write-Host "  ✓ Infrastructure deployed`n"

# Step 5: Always set app image so deployments never stay on the hello-world default.
Write-Host "✓ Step 4: Updating Container App image to $ImageTag..."
az containerapp update `
    --resource-group $prodRG `
    --name $deployment.containerAppName `
    --image "ghcr.io/munishgoyal1/tripplanner:$ImageTag" `
    -o none
Write-Host "  ✓ Image updated`n"

# Step 6: Output results
Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ✓ PRODUCTION DEPLOYMENT COMPLETE                        ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "App URL: https://$($deployment.containerAppUrl)"
Write-Host "Environment: PRODUCTION"
Write-Host "Resource Group: $prodRG"
Write-Host "Container App: $($deployment.containerAppName)"
Write-Host "Image: ghcr.io/munishgoyal1/tripplanner:$ImageTag`n"

# Log deployment
$logDir = "logs"
if (-not (Test-Path $logDir)) { mkdir $logDir -Force | Out-Null }
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$approver = $env:USERNAME
Add-Content "logs/deployments-prod.log" "[$timestamp] APPROVED by $approver | RG: $prodRG | Image: ghcr.io/munishgoyal1/tripplanner:$ImageTag | Status: SUCCESS"

Write-Host "✓ Logged to logs/deployments-prod.log"
Write-Host "✓ All users can now access the production deployment`n"

# Post-deployment validation hint
Write-Host "Next steps:"
Write-Host "  1. Monitor production logs: az containerapp logs show -g $prodRG -n $prodApp"
Write-Host "  2. Test critical flows (chat, map, email)"
Write-Host "  3. If issues arise, run: ./infra/rollback-prod.ps1`n"

