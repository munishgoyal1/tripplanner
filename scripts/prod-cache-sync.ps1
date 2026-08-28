#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Merge eligible cache entries between the local emulator and production Cosmos.

.EXAMPLE
    # Defaults to a two-way apply and prompts for APPROVE_PROD_CACHE_SYNC.
  ./scripts/prod-cache-sync.ps1
  ./scripts/prod-cache-sync.ps1 -Direction Pull
    ./scripts/prod-cache-sync.ps1 -Approval APPROVE_PROD_CACHE_SYNC
#>

param(
    [ValidateSet("Status", "Pull", "Push", "Both")]
        [string]$Direction = "Both",
    [switch]$WhatIf = $false,
    [string]$Approval = "",
    [string]$SubscriptionId = "",
    [string]$CosmosResourceGroup = "rg-tripplanner-data",
    [string]$CosmosAccountName = "",
    [string]$LocalDatabase = "tripplanner-cache",
    [string]$ReportPath = "",
    [string]$CheckpointPath = "",
    [ValidateRange(0, 86400)]
        [int]$WatermarkOverlapSeconds = 300,
    [switch]$FullScan = $false
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
. "$repoRoot/infra/deployment-common.ps1"
Start-RunLog -Name "prod-cache-sync" | Out-Null

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) {
        throw "Could not select Azure subscription $SubscriptionId."
    }
}

$accountJson = az account show --query "{id:id,name:name,user:user.name}" -o json
if ($LASTEXITCODE -ne 0) {
    throw "Azure CLI is not authenticated. Run az login with the approved personal account."
}
$account = $accountJson | ConvertFrom-Json
if ($account.user -ne "munishgoyal1@gmail.com") {
    throw "Refusing Azure access as '$($account.user)'. Use munishgoyal1@gmail.com."
}
if ($account.name -ne "Visual Studio Enterprise Subscription") {
    throw "Refusing subscription '$($account.name)'. Select the Visual Studio Enterprise subscription."
}

if ([string]::IsNullOrWhiteSpace($CosmosAccountName)) {
    $accounts = @(az cosmosdb list -g $CosmosResourceGroup --query "[].name" -o tsv)
    if ($LASTEXITCODE -ne 0 -or $accounts.Count -ne 1) {
        throw "Expected exactly one Cosmos account in $CosmosResourceGroup. Pass -CosmosAccountName explicitly."
    }
    $CosmosAccountName = $accounts[0]
}
$prodEndpoint = az cosmosdb show `
    -g $CosmosResourceGroup `
    -n $CosmosAccountName `
    --query documentEndpoint `
    -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($prodEndpoint)) {
    throw "Could not resolve the production Cosmos endpoint."
}

$writesProduction = $Direction -in @("Push", "Both") -and -not $WhatIf
if ($writesProduction) {
    if ([string]::IsNullOrWhiteSpace($Approval)) {
        $Approval = Read-Host "Type APPROVE_PROD_CACHE_SYNC to write production cache entries"
    }
    if ($Approval -ne "APPROVE_PROD_CACHE_SYNC") {
        throw "Production cache sync approval was not provided; nothing was written."
    }
}

if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $ReportPath = Join-Path (Get-PrimaryRepoRoot) "logs/cache-sync/$stamp.json"
}
$primaryRoot = Get-PrimaryRepoRoot
if ([string]::IsNullOrWhiteSpace($CheckpointPath)) {
    $CheckpointPath = Join-Path $primaryRoot "logs/cache-sync/checkpoint.json"
}
$pythonCandidates = @(
    (Join-Path $primaryRoot ".venv/bin/python"),
    (Join-Path $primaryRoot ".venv/Scripts/python.exe"),
    "python3",
    "python"
)
$pythonCommand = $null
foreach ($candidate in $pythonCandidates) {
    if ((Test-Path $candidate) -or (Get-Command $candidate -ErrorAction SilentlyContinue)) {
        $pythonCommand = $candidate
        break
    }
}
if ($null -eq $pythonCommand) {
    throw "Python was not found. Restore the primary checkout virtual environment first."
}
$apply = $Direction -ne "Status" -and -not $WhatIf
$mode = if ($apply) { "APPLY" } else { "DRY RUN" }
Write-Host "[cache]   $mode ${Direction}: $LocalDatabase <-> tripplanner-prod"
Write-Host "[azure]   $($account.user) / $($account.name) / $($account.id)"

$env:TRIPPLANNER_PROD_COSMOS_KEY = az cosmosdb keys list `
    -g $CosmosResourceGroup `
    -n $CosmosAccountName `
    --type keys `
    --query primaryMasterKey `
    -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($env:TRIPPLANNER_PROD_COSMOS_KEY)) {
    throw "Could not obtain a process-scoped Cosmos credential."
}

try {
    $arguments = @(
        "$repoRoot/scripts/prod_cache_sync.py",
        "--direction", $Direction.ToLowerInvariant(),
        "--prod-endpoint", $prodEndpoint,
        "--local-database", $LocalDatabase,
        "--local-config", "$repoRoot/config/environments/local.env",
        "--prod-config", "$repoRoot/config/environments/prod.env",
        "--checkpoint", $CheckpointPath,
        "--watermark-overlap-seconds", $WatermarkOverlapSeconds,
        "--report", $ReportPath
    )
    if ($apply) {
        $arguments += "--apply"
    }
    if ($FullScan) {
        $arguments += "--full-scan"
    }
    & $pythonCommand @arguments
    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:TRIPPLANNER_PROD_COSMOS_KEY -ErrorAction SilentlyContinue
}

if ($exitCode -ne 0) {
    throw "Cache synchronization failed with exit code $exitCode. Review $ReportPath."
}