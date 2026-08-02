#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("all")]
    [string]$Target,

    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
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
    default {
        throw "Sync-Latest supports master, agents/worker-1, or agents/worker-2; found $branch."
    }
}
$laneName = if ($agentNumber -eq 0) { "MasterAgent (0)" } else { "Agent $agentNumber" }

Write-Host "Synchronizing latest committed code into $laneName..." -ForegroundColor Cyan
if ($agentNumber -eq 0) {
    & "$PSScriptRoot\merge-latest-worktrees.ps1" -ValidateOnly:$ValidateOnly
    Write-Host "MasterAgent is current after worktree integration." -ForegroundColor Green
    return
}

if ($Target -eq "all") {
    Write-Host "Integrating all committed worktree heads through master..." -ForegroundColor Cyan
    & "$PSScriptRoot\merge-latest-worktrees.ps1" -SkipPrimaryUpdate -ValidateOnly:$ValidateOnly
}

Write-Host "Applying latest master to $laneName..." -ForegroundColor Cyan
& "$PSScriptRoot\update-from-master.ps1" $agentNumber -ValidateOnly:$ValidateOnly
