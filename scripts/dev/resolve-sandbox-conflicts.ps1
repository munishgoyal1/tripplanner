#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Finish a recorded or manually resolved merge in a managed worktree.

.DESCRIPTION
  Accepts the sandbox number, full slug, or short name, matching every other
  sandbox launcher. Full-2Way-Sync can also pass a worktree directly so the
  same recorded-resolution recovery works for multiagent and standalone lanes.

.EXAMPLE
  ./scripts/dev/resolve-sandbox-conflicts.ps1 1
  ./scripts/dev/resolve-sandbox-conflicts.ps1 1-stay-comparison
  ./scripts/dev/resolve-sandbox-conflicts.ps1 stay-comparison
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Sandbox")]
    [string]$Sandbox,

    [Parameter(Mandatory = $true, ParameterSetName = "Worktree")]
    [string]$WorkingDirectory,

    [Parameter(ParameterSetName = "Worktree")]
    [string]$Lane = ""
)

$ErrorActionPreference = "Stop"
$checkoutRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot/lib/sandbox-registry.ps1"
$repoRoot = Get-PrimaryRepositoryRoot -RepositoryRoot $checkoutRoot

$entry = $null
$statePath = ""
if ($PSCmdlet.ParameterSetName -eq "Sandbox") {
    $registryPath = Get-SandboxRegistryPath -PrimaryRoot $repoRoot
    if (-not (Test-Path $registryPath)) { throw "Sandbox registry not found: $registryPath" }

    $entry = @(Select-SandboxEntry `
        -Entries (Get-SandboxRegistry -PrimaryRoot $repoRoot) `
        -Reference $Sandbox)[0]
    $worktree = $entry.worktree
    $laneName = $entry.slug
    $targetBranch = $entry.branch
    $statePath = Join-Path $repoRoot "logs/sandbox/pending-conflict-$((Split-Path -Leaf $worktree)).json"
} else {
    $worktree = (Resolve-Path $WorkingDirectory).Path
    $targetBranch = (& git -C $worktree branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $targetBranch) {
        throw "Could not resolve the branch checked out in $worktree."
    }
    $laneName = if ($Lane) { $Lane } else { $targetBranch }
}

# Replay resolutions this repository already recorded. rerere only reapplies a
# resolution the owner made themselves, so nothing new is decided here.
& git -C $worktree rerere 2>&1 | Out-Host

$unmerged = @(& git -C $worktree diff --name-only --diff-filter=U)
if ($unmerged.Count -gt 0) {
    throw "Resolve these files before retrying: $($unmerged -join ', ')"
}
& git -C $worktree rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
if ($LASTEXITCODE -ne 0 -and (-not $statePath -or -not (Test-Path $statePath))) {
    Write-Host "[no-op] Lane '$laneName' has no pending merge." -ForegroundColor Yellow
    exit 0
}
if ($LASTEXITCODE -eq 0 -and $PSCmdlet.ShouldProcess($targetBranch, "Finish recorded merge")) {
    & git -C $worktree add -u
    & git -C $worktree commit --no-edit
    if ($LASTEXITCODE -ne 0) { throw "Could not finish the merge for '$laneName'." }
}
if ($statePath -and (Test-Path $statePath)) {
    $state = Get-Content -Raw $statePath | ConvertFrom-Json
    $currentStash = & git -C $worktree rev-parse --quiet --verify refs/stash 2>$null
    if ($LASTEXITCODE -ne 0 -or $currentStash -ne $state.stashCommit) {
        throw "Sandbox safety stash changed; leaving it untouched for manual recovery."
    }
    if ($PSCmdlet.ShouldProcess($targetBranch, "Finalize sandbox safety stash recovery")) {
        & git -C $worktree rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & git -C $worktree stash pop --index "stash@{0}"
            if ($LASTEXITCODE -ne 0) { throw "Sandbox merge finished, but restoring its safety stash conflicted." }
        } else {
            & git -C $worktree stash drop "stash@{0}"
            if ($LASTEXITCODE -ne 0) { throw "Resolved sandbox stash conflict, but could not remove its retained safety stash." }
        }
        Remove-Item -Force $statePath
    }
}
& git -C $worktree rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[resolved] Lane '$laneName' is conflict-free." -ForegroundColor Green
    exit 0
}
throw "Lane '$laneName' still has a pending merge after conflict recovery."
