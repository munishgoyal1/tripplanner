#!/usr/bin/env pwsh
<#!
.SYNOPSIS
  Synchronize every registered sandbox with the latest primary master.
#>

[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = & git -C $scriptRepoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) {
    throw "Could not resolve the primary Tripplanner checkout."
}
$primaryRoot = Split-Path -Parent $commonGitDir.Trim()
$registryPath = "$primaryRoot.worktrees/sandboxes.json"
if (-not (Test-Path $registryPath)) {
    Write-Host "[ready]   No sandboxes are registered." -ForegroundColor Green
    return
}
$sandboxes = @(Get-Content -Raw $registryPath | ConvertFrom-Json)
if ($sandboxes.Count -eq 0) {
    Write-Host "[ready]   No sandboxes are registered." -ForegroundColor Green
    return
}

$syncScript = Join-Path $primaryRoot "scripts/dev/sync-latest.ps1"
$failures = [System.Collections.Generic.List[string]]::new()
foreach ($sandbox in $sandboxes) {
    if (-not (Test-Path $sandbox.worktree -PathType Container)) {
        $failures.Add("$($sandbox.slug): worktree is missing")
        continue
    }
    Write-Host "[sync]    sandbox '$($sandbox.slug)'" -ForegroundColor Cyan
    try {
        & $syncScript $sandbox.slug -ValidateOnly:$ValidateOnly
        if ($LASTEXITCODE -ne 0) { throw "sync command returned $LASTEXITCODE" }
    } catch {
        $failures.Add("$($sandbox.slug): $($_.Exception.Message)")
    }
}
if ($failures.Count -gt 0) {
    throw "Sandbox synchronization needs attention:`n$($failures -join "`n")"
}

if (-not $ValidateOnly) {
    $masterHead = (& git -C $primaryRoot rev-parse HEAD).Trim()
    foreach ($sandbox in $sandboxes) {
        & git -C $sandbox.worktree merge-base --is-ancestor $masterHead HEAD
        if ($LASTEXITCODE -ne 0) {
            throw "Sandbox '$($sandbox.slug)' local branch is behind master $masterHead after Sync All."
        }
        & git -C $primaryRoot merge-base --is-ancestor $masterHead "origin/$($sandbox.branch)"
        if ($LASTEXITCODE -ne 0) {
            throw "Sandbox '$($sandbox.slug)' remote branch is behind master $masterHead after Sync All."
        }
    }
    Write-Host "[verified] All registered local and remote sandbox branches contain master $($masterHead.Substring(0, 7))." -ForegroundColor Green
}
Write-Host "[done]    All registered sandboxes are current with master." -ForegroundColor Green