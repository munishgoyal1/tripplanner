#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Finish a manually resolved merge in an active sandbox.

.DESCRIPTION
  Accepts the sandbox number, full slug, or short name, matching every other
  sandbox launcher.

.EXAMPLE
  ./scripts/dev/resolve-sandbox-conflicts.ps1 1
  ./scripts/dev/resolve-sandbox-conflicts.ps1 1-stay-comparison
  ./scripts/dev/resolve-sandbox-conflicts.ps1 stay-comparison
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Sandbox
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. "$PSScriptRoot/lib/sandbox-registry.ps1"

$registryPath = Get-SandboxRegistryPath -PrimaryRoot $repoRoot
if (-not (Test-Path $registryPath)) { throw "Sandbox registry not found: $registryPath" }

$entry = @(Select-SandboxEntry -Entries (Get-SandboxRegistry -PrimaryRoot $repoRoot) -Reference $Sandbox)
$worktree = $entry[0].worktree
$statePath = Join-Path $repoRoot "logs/sandbox/pending-conflict-$((Split-Path -Leaf $worktree)).json"

# Replay resolutions this repository already recorded. rerere only reapplies a
# resolution the owner made themselves, so nothing new is decided here.
& git -C $worktree rerere 2>&1 | Out-Host

$unmerged = @(& git -C $worktree diff --name-only --diff-filter=U)
if ($unmerged.Count -gt 0) {
    throw "Resolve these files before retrying: $($unmerged -join ', ')"
}
& git -C $worktree rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
if ($LASTEXITCODE -ne 0 -and -not (Test-Path $statePath)) {
    Write-Host "[no-op] Sandbox '$($entry[0].slug)' has no pending merge." -ForegroundColor Yellow
    return
}
if ($LASTEXITCODE -eq 0 -and $PSCmdlet.ShouldProcess($entry[0].branch, "Finish resolved sandbox merge")) {
    & git -C $worktree add -u
    & git -C $worktree commit --no-edit
    if ($LASTEXITCODE -ne 0) { throw "Could not finish the sandbox merge." }
}
if (Test-Path $statePath) {
    $state = Get-Content -Raw $statePath | ConvertFrom-Json
    $currentStash = & git -C $worktree rev-parse --quiet --verify refs/stash 2>$null
    if ($LASTEXITCODE -ne 0 -or $currentStash -ne $state.stashCommit) {
        throw "Sandbox safety stash changed; leaving it untouched for manual recovery."
    }
    if ($PSCmdlet.ShouldProcess($entry[0].branch, "Finalize sandbox safety stash recovery")) {
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
    Write-Host "[resolved] Sandbox '$($entry[0].slug)' local changes are restored; rerun Sync Me or Sync All." -ForegroundColor Green
    return
}
if ($PSCmdlet.ShouldProcess($entry[0].branch, "Push resolved sandbox branch")) {
    & git -C $worktree push -u origin "HEAD:refs/heads/$($entry[0].branch)"
    if ($LASTEXITCODE -ne 0) { throw "Could not push the resolved sandbox branch." }
}
Write-Host "[resolved] Sandbox '$($entry[0].slug)' is ready to update or promote." -ForegroundColor Green