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

$ErrorActionPreference = "Stop"

$prodRG = "rg-multiagent-trip-planner"
$prodApp = "multiagent-app-rb4t6btfs5x5m"

Write-Host "`n╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ⚠️  PRODUCTION ROLLBACK                                  ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

Write-Host "This will revert production to the previous revision."
Write-Host "Data and database are NOT affected — only the app code."
Write-Host "Downtime: ~2-5 seconds`n"

$confirmation = Read-Host "Type ROLLBACK to confirm"
if ($confirmation -ne "ROLLBACK") {
    Write-Host "`n❌ Rollback cancelled.`n"
    exit 1
}

Write-Host "`nFetching revision history...`n"
$revisions = az containerapp revision list `
    --resource-group $prodRG `
    --name $prodApp `
    --query "[0:2].{name:name, createdTime:properties.createdTime, active:properties.active}" `
    --output table

Write-Host $revisions
Write-Host "`n"

Write-Host "Rolling back to previous revision..."
$currentRevision = az containerapp revision list `
    --resource-group $prodRG `
    --name $prodApp `
    --query "[0].name" -o tsv

$previousRevision = az containerapp revision list `
    --resource-group $prodRG `
    --name $prodApp `
    --query "[1].name" -o tsv

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
