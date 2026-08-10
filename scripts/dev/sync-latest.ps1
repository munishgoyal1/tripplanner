#!/usr/bin/env pwsh
<#!
.SYNOPSIS
  Synchronize one sandbox with the latest primary master.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Sandbox,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = & git -C $scriptRepoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) {
    throw "Could not resolve the primary Tripplanner checkout."
}
$primaryRoot = Split-Path -Parent $commonGitDir.Trim()
$branch = (& git -C $primaryRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne "master") {
    throw "The primary checkout must be on master before synchronizing sandboxes."
}
$changes = & git -C $primaryRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Could not inspect primary master changes." }
if ($changes -and -not $ValidateOnly) {
    throw "Primary master has uncommitted changes. Commit or stash them before synchronizing sandboxes."
}

Write-Host "[sync]    fetching origin/master" -ForegroundColor Cyan
& git -C $primaryRoot fetch origin master
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin/master." }
if (-not $ValidateOnly) {
    & git -C $primaryRoot merge --ff-only origin/master
    if ($LASTEXITCODE -ne 0) { throw "Could not fast-forward primary master." }
}

$sandboxScript = Join-Path $primaryRoot "scripts/dev/sandbox.ps1"
if ($ValidateOnly) {
    Write-Host "[ready]   Sandbox '$Sandbox' can be updated from origin/master." -ForegroundColor Green
    return
}
& $sandboxScript -Update $Sandbox -BaseBranch master -Confirm:$false
if ($LASTEXITCODE -ne 0) { throw "Could not synchronize sandbox '$Sandbox'." }