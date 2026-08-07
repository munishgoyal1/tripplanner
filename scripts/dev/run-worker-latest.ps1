#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet(1, 2, 3)]
    [int]$WorkerNumber
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
Start-RunLog -Name "run-worker-latest" | Out-Null
. "$PSScriptRoot/lib/sync-common.ps1"

Write-Warning "Fast path: integrating only Agent $WorkerNumber into master; tests are skipped."
& "$PSScriptRoot/merge-latest-worktrees.ps1" $WorkerNumber -SkipValidation

$primaryRoot = (Get-SyncPaths).PrimaryRoot
$primaryDevSpa = Join-Path $primaryRoot "scripts/dev/dev-spa.ps1"
Write-Host "Starting the canonical master dev stack from $primaryRoot..." -ForegroundColor Cyan
Push-Location $primaryRoot
try {
    & $primaryDevSpa
} finally {
    Pop-Location
}
