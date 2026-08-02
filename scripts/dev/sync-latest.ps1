#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(1, 2, 3)]
    [int]$WorkerNumber,

    [switch]$ValidateOnly
)

$arguments = @{}
if ($PSBoundParameters.ContainsKey("WorkerNumber")) {
    $arguments.WorkerNumber = $WorkerNumber
}
if ($ValidateOnly) {
    $arguments.ValidateOnly = $true
}

Write-Host "Integrating committed worker code into master..." -ForegroundColor Cyan
& "$PSScriptRoot\merge-worktrees.ps1" -ValidateOnly:$ValidateOnly

if ($PSBoundParameters.ContainsKey("WorkerNumber") -and $WorkerNumber -eq 3) {
    Write-Host "Agent 3 is current after worktree integration." -ForegroundColor Green
    return
}

Write-Host "Applying latest master to the selected worktree lanes..." -ForegroundColor Cyan
if (-not $PSBoundParameters.ContainsKey("WorkerNumber")) {
    foreach ($number in 1, 2) {
        & "$PSScriptRoot\update-from-master.ps1" $number -ValidateOnly:$ValidateOnly
    }
    return
}
& "$PSScriptRoot\update-from-master.ps1" @arguments
