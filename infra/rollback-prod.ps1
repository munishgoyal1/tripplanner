#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Rollback production to the previous stable revision

.DESCRIPTION
  Reverts the production app to the previous revision without data loss.
  Use this if a production deployment causes issues.

.EXAMPLE
  ./infra/rollback-prod.ps1
#>

param(
  [string]$SubscriptionId = "",
  [string]$ResourceGroup = "rg-tripplanner-prod",
  [string]$AppName = "",
  [string]$AppNamePrefix = "prod-app-"
)

$ErrorActionPreference = "Stop"

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
  az account set --subscription $SubscriptionId
}

$prodRG = $ResourceGroup

if ([string]::IsNullOrWhiteSpace($AppName)) {
  $matchedApps = az containerapp list `
    --resource-group $prodRG `
    --query "[?starts_with(name, '$AppNamePrefix')].name" `
    --output tsv

  $appNames = @($matchedApps -split "`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  if ($appNames.Count -eq 0) {
    throw "No Container App found in $prodRG with prefix '$AppNamePrefix'."
  }
  if ($appNames.Count -gt 1) {
    throw "Multiple Container Apps match prefix '$AppNamePrefix' in ${prodRG}: $($appNames -join ', '). Pass -AppName explicitly."
  }
  $prodApp = $appNames[0]
} else {
  $prodApp = $AppName
}

Write-Host "`n╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ⚠️  PRODUCTION ROLLBACK                                  ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "This will revert production to the previous revision."
Write-Host "Data and database are NOT affected — only the app code."
Write-Host "Downtime: ~2-5 seconds`n"
Write-Host "Target RG: $prodRG"
Write-Host "Target App: $prodApp`n"

$confirmation = Read-Host "Type ROLLBACK to confirm"
if ($confirmation -ne "ROLLBACK") {
    Write-Host "`n❌ Rollback cancelled.`n"
    exit 1
}

Write-Host "`nFetching revision history...`n"
$revisionRows = az containerapp revision list `
  --resource-group $prodRG `
  --name $prodApp `
  --query "[].{name:name, createdTime:properties.createdTime, active:properties.active}" `
  --output json | ConvertFrom-Json

$orderedRevisions = @($revisionRows | Sort-Object { $_.createdTime } -Descending)
$currentRevision = ($orderedRevisions | Where-Object { $_.active } | Select-Object -First 1).name
$previousRevision = ($orderedRevisions | Where-Object { $_.name -ne $currentRevision } | Select-Object -First 1).name

if ($orderedRevisions.Count -gt 0) {
  $orderedRevisions | Select-Object -First 2 | Format-Table name, createdTime, active | Out-Host
  Write-Host "`n"
}

Write-Host "Rolling back to previous revision..."

if ([string]::IsNullOrEmpty($previousRevision)) {
    Write-Error "No previous revision found. Cannot rollback."
}

az containerapp revision set-active `
    --resource-group $prodRG `
    --name $prodApp `
    --revision $previousRevision -o none

Write-Host "`n✓ Rollback complete!"
Write-Host "  Current: $currentRevision (deactivated)"
Write-Host "  Active: $previousRevision`n"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$logDir = "logs"
if (-not (Test-Path $logDir)) { mkdir $logDir -Force | Out-Null }
Add-Content "logs/deployments-prod.log" "[$timestamp] ROLLBACK from $currentRevision to $previousRevision | By: $env:USERNAME"

Write-Host "✓ Logged to logs/deployments-prod.log`n"

