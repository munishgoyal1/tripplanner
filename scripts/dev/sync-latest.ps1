#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("onlyfrommaster")]
    [string]$Target,

    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sync-common.ps1"
$syncLogOwned = Start-SyncLog -Component "sync-latest"
try {

if (-not $ValidateOnly) { Invoke-PendingMergeHeal }

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$branch = & git -C $repoRoot branch --show-current
$gitExitCode = $LASTEXITCODE
if ($gitExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
    throw "Could not identify the launcher worktree branch at $repoRoot."
}
$branch = @($branch)[0].Trim()

$agentNumber = switch ($branch) {
    "master" { 0 }
    "agents/worker-1" { 1 }
    "agents/worker-2" { 2 }
    "agents/worker-3" { 3 }
    default {
        throw "Sync-Latest supports master or agents/worker-1 through agents/worker-3; found $branch."
    }
}
$laneName = if ($agentNumber -eq 0) { "MasterAgent (0)" } else { "Agent $agentNumber" }

Write-Host "Synchronizing latest committed code into $laneName..." -ForegroundColor Cyan
if ($agentNumber -eq 0) {
    if ($Target -eq "onlyfrommaster") {
        & "$PSScriptRoot\update-from-master.ps1" 0 -ValidateOnly:$ValidateOnly
        Write-Host "MasterAgent is current with origin/master only." -ForegroundColor Green
    }
    else {
        & "$PSScriptRoot\merge-latest-worktrees.ps1" -ValidateOnly:$ValidateOnly
        Write-Host "MasterAgent is current after worktree integration." -ForegroundColor Green
    }
    return
}

if ($Target -ne "onlyfrommaster") {
    Write-Host "Integrating all committed worktree heads through master..." -ForegroundColor Cyan
    & "$PSScriptRoot\merge-latest-worktrees.ps1" -SkipPrimaryUpdate -ValidateOnly:$ValidateOnly
}

Write-Host "Applying latest master to $laneName..." -ForegroundColor Cyan
& "$PSScriptRoot\update-from-master.ps1" $agentNumber -ValidateOnly:$ValidateOnly

}
finally {
    if ($syncLogOwned) { Stop-SyncLog }
}
