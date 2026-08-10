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

$registryPath = "$primaryRoot.worktrees/sandboxes.json"
$entries = @(Get-Content -Raw $registryPath | ConvertFrom-Json)
$shortName = $Sandbox -replace "^\d+-", ""
$entry = @($entries | Where-Object {
    $_.slug -eq $Sandbox -or ($_.slug -replace "^\d+-", "") -eq $shortName
})
if ($entry.Count -eq 0 -and $Sandbox -match "^\d+$") {
    $entry = @($entries | Where-Object { ([int]$_.slot + 1) -eq [int]$Sandbox })
}
if ($entry.Count -ne 1) { throw "Sandbox '$Sandbox' was not uniquely found after synchronization." }

$masterHead = (& git -C $primaryRoot rev-parse HEAD).Trim()
& git -C $entry[0].worktree merge-base --is-ancestor $masterHead HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Sandbox '$($entry[0].slug)' local branch does not contain master $masterHead after synchronization."
}
& git -C $primaryRoot merge-base --is-ancestor $masterHead "origin/$($entry[0].branch)"
if ($LASTEXITCODE -ne 0) {
    throw "Sandbox '$($entry[0].slug)' remote branch does not contain master $masterHead after synchronization."
}
Write-Host "[verified] Sandbox '$($entry[0].slug)' local and remote branches contain master $($masterHead.Substring(0, 7))." -ForegroundColor Green