#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Fast-forward primary master from origin/master, then synchronize registered sandboxes.

.DESCRIPTION
  With no sandbox argument, updates every registered sandbox. Pass a sandbox number,
  full slug, or short name to update only that sandbox.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Position = 0)]
    [string]$Sandbox = "",
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

Write-Host "[sync]    fetching origin/master" -ForegroundColor Cyan
& git -C $primaryRoot fetch -q origin master
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin/master." }
if (-not $ValidateOnly) {
    & git -C $primaryRoot merge --ff-only origin/master
    if ($LASTEXITCODE -ne 0) {
        throw "Could not fast-forward primary master. Commit or stash conflicting local changes first."
    }
}

$registryPath = "$primaryRoot.worktrees/sandboxes.json"
if (-not (Test-Path $registryPath)) {
    Write-Host "[ready]   No sandboxes are registered." -ForegroundColor Green
    return
}
$registered = @(Get-Content -Raw $registryPath | ConvertFrom-Json)
if ($registered.Count -eq 0) {
    Write-Host "[ready]   No sandboxes are registered." -ForegroundColor Green
    return
}

if ($Sandbox) {
    $shortName = $Sandbox -replace "^\d+-", ""
    $targets = @($registered | Where-Object {
        $_.slug -eq $Sandbox -or ($_.slug -replace "^\d+-", "") -eq $shortName
    })
    if ($targets.Count -eq 0 -and $Sandbox -match "^\d+$") {
        $targets = @($registered | Where-Object { ([int]$_.slot + 1) -eq [int]$Sandbox })
    }
    if ($targets.Count -ne 1) {
        $known = ($registered | ForEach-Object { "#$([int]$_.slot + 1) $($_.slug)" }) -join ", "
        throw "Sandbox '$Sandbox' was not uniquely found. Registered: $known."
    }
} else {
    $targets = $registered
}

if ($ValidateOnly) {
    $scope = if ($Sandbox) { "Sandbox '$($targets[0].slug)'" } else { "All registered sandboxes" }
    Write-Host "[ready]   $scope can be updated from origin/master." -ForegroundColor Green
    return
}

$sandboxScript = Join-Path $primaryRoot "scripts/dev/sandbox.ps1"
$failures = [System.Collections.Generic.List[string]]::new()
foreach ($target in $targets) {
    if (-not (Test-Path $target.worktree -PathType Container)) {
        $failures.Add("$($target.slug): worktree is missing")
        continue
    }
    Write-Host "[sync]    sandbox '$($target.slug)'" -ForegroundColor Cyan
    try {
        & $sandboxScript -Update $target.slug -BaseBranch master -NoSync -Confirm:$false
        if ($LASTEXITCODE -ne 0) { throw "sync command returned $LASTEXITCODE" }
    } catch {
        $failures.Add("$($target.slug): $($_.Exception.Message)")
    }
}
if ($failures.Count -gt 0) {
    throw "Sandbox synchronization needs attention:`n$($failures -join "`n")"
}

$masterHead = (& git -C $primaryRoot rev-parse HEAD).Trim()
foreach ($target in $targets) {
    & git -C $target.worktree merge-base --is-ancestor $masterHead HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "Sandbox '$($target.slug)' local branch is behind master $masterHead after synchronization."
    }
    & git -C $primaryRoot merge-base --is-ancestor $masterHead "origin/$($target.branch)"
    if ($LASTEXITCODE -ne 0) {
        throw "Sandbox '$($target.slug)' remote branch is behind master $masterHead after synchronization."
    }
}
$scope = if ($Sandbox) { "Sandbox '$($targets[0].slug)'" } else { "All registered sandboxes" }
Write-Host "[verified] $scope local and remote branches contain master $($masterHead.Substring(0, 7))." -ForegroundColor Green