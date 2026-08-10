#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Finish a manually resolved merge in an active sandbox.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Sandbox
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$registryPath = "$repoRoot.worktrees/sandboxes.json"
if (-not (Test-Path $registryPath)) { throw "Sandbox registry not found: $registryPath" }

$entries = @(Get-Content -Raw $registryPath | ConvertFrom-Json)
$shortName = $Sandbox -replace "^\d+-", ""
$entry = @($entries | Where-Object {
    $_.slug -eq $Sandbox -or ($_.slug -replace "^\d+-", "") -eq $shortName
})
if ($entry.Count -eq 0 -and $Sandbox -match "^\d+$") {
    $entry = @($entries | Where-Object { ([int]$_.slot + 1) -eq [int]$Sandbox })
}
if ($entry.Count -ne 1) { throw "Sandbox '$Sandbox' was not uniquely found." }
$worktree = $entry[0].worktree
$statePath = Join-Path $repoRoot "logs/sandbox/pending-conflict-$((Split-Path -Leaf $worktree)).json"

$unmerged = @(& git -C $worktree diff --name-only --diff-filter=U)
if ($unmerged.Count -gt 0) {
    throw "Resolve these files before retrying: $($unmerged -join ', ')"
}
& git -C $worktree rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[no-op] Sandbox '$($entry[0].slug)' has no pending merge." -ForegroundColor Yellow
    return
}
if ($PSCmdlet.ShouldProcess($entry[0].branch, "Finish resolved sandbox merge")) {
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
    if ($PSCmdlet.ShouldProcess($entry[0].branch, "Restore sandbox safety stash")) {
        & git -C $worktree stash pop --index "stash@{0}"
        if ($LASTEXITCODE -ne 0) { throw "Sandbox merge finished, but restoring its safety stash conflicted." }
        Remove-Item -Force $statePath
    }
}
if ($PSCmdlet.ShouldProcess($entry[0].branch, "Push resolved sandbox branch")) {
    & git -C $worktree push -u origin "HEAD:refs/heads/$($entry[0].branch)"
    if ($LASTEXITCODE -ne 0) { throw "Could not push the resolved sandbox branch." }
}
Write-Host "[resolved] Sandbox '$($entry[0].slug)' is ready to update or promote." -ForegroundColor Green