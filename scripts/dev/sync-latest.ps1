#!/usr/bin/env pwsh
[CmdletBinding()]
param(
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

$workerNumber = switch ($branch) {
    "master" { 3 }
    "agents/worker-1" { 1 }
    "agents/worker-2" { 2 }
    default {
        throw "Sync-Latest supports master, agents/worker-1, or agents/worker-2; found $branch."
    }
}
$laneName = if ($workerNumber -eq 3) { "Agent 3 (master)" } else { "Agent $workerNumber" }

Write-Host "Synchronizing latest committed code into $laneName..." -ForegroundColor Cyan
& "$PSScriptRoot\merge-latest-worktrees.ps1" -ValidateOnly:$ValidateOnly

if ($workerNumber -eq 3) {
    Write-Host "Agent 3 is current after worktree integration." -ForegroundColor Green
    return
}

Write-Host "Applying integrated master to $laneName..." -ForegroundColor Cyan
& "$PSScriptRoot\update-from-master.ps1" $workerNumber -ValidateOnly:$ValidateOnly
