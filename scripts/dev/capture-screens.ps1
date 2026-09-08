#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Capture screenshots, API view-models, console output, and DOM for a local run.

.DESCRIPTION
  Points at the primary stack by default. Pass -Sandbox <n> to target that
  sandbox's SPA port instead. Output lands in debug-store/assets/<label>.
#>

[CmdletBinding()]
param(
    [int]$Sandbox = 0,
    [string]$Url = "",
    [string]$Label = "capture",
    [string]$User = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

if (-not $Url) {
    $port = 5173
    if ($Sandbox -gt 0) {
        $worktrees = if ((Split-Path -Leaf (Split-Path -Parent $repoRoot)) -eq "tripplanner.worktrees") {
            Split-Path -Parent $repoRoot
        } else {
            "$(Split-Path -Parent $repoRoot)/tripplanner.worktrees"
        }
        $registryPath = Join-Path $worktrees "sandboxes.json"
        if (-not (Test-Path $registryPath)) { throw "No sandbox registry at $registryPath." }
        $entry = Get-Content -Raw $registryPath | ConvertFrom-Json |
            Where-Object { [int]$_.slot + 1 -eq $Sandbox }
        if (-not $entry) { throw "Sandbox #$Sandbox is not registered." }
        $port = [int]$entry.frontendPort
    }
    $Url = "http://127.0.0.1:$port"
}

$node = (Get-Command node -ErrorAction SilentlyContinue)?.Source
if (-not $node) { throw "Node.js is required for UI capture but was not found on PATH." }

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$outDir = Join-Path $repoRoot "debug-store/assets/$Label-$stamp"

Write-Host "Capturing UI evidence from $Url" -ForegroundColor Cyan
Push-Location (Join-Path $repoRoot "frontend")
try {
    & $node (Join-Path $repoRoot "frontend/scripts/capture-screens.mjs") `
        "--url=$Url" "--out=$outDir" "--label=$Label" "--user=$User"
    if ($LASTEXITCODE -ne 0) { throw "UI capture failed." }
}
finally {
    Pop-Location
}
Write-Host "Saved to $outDir" -ForegroundColor Green
