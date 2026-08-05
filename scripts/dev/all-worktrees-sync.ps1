#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$ValidateOnly,
    [switch]$NoAutoResolve
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sync-common.ps1"
$scriptRoot = $PSScriptRoot
$laneNames = @{
    0 = "MasterAgent (0)"
    1 = "Agent 1"
    2 = "Agent 2"
    3 = "Agent 3 - Sandbox"
}

$syncLogOwned = Start-SyncLog -Component "all-worktrees-sync"
try {

Invoke-SyncWithAutoResolve -NoAutoResolve:$NoAutoResolve -Body {

$failures = [System.Collections.Generic.List[object]]::new()

if (-not $ValidateOnly) { Invoke-PendingMergeHeal }

Write-Host "Integrating all committed worktree heads through master..." -ForegroundColor Cyan
& "$scriptRoot\merge-latest-worktrees.ps1" -SkipPrimaryUpdate -ValidateOnly:$ValidateOnly

foreach ($number in @(0, 1, 2, 3)) {
    $laneName = $laneNames[$number]
    Write-Host "`nSynchronizing $laneName..." -ForegroundColor Cyan
    try {
        & "$scriptRoot\update-from-master.ps1" $number -ValidateOnly:$ValidateOnly
    } catch {
        $failures.Add([pscustomobject]@{
            Lane = $laneName
            Error = $_.Exception.Message
        })
        Write-Warning "$laneName could not be fully synchronized. Continuing with the other worktrees."
    }
}

if ($failures.Count -gt 0) {
    $global:TripplannerSyncFailed = $true
    Write-Host "`nWorktrees requiring attention:" -ForegroundColor Yellow
    foreach ($failure in $failures) {
        Write-Host "  $($failure.Lane): $($failure.Error)" -ForegroundColor Yellow
    }
    throw "All-worktrees synchronization finished with $($failures.Count) worktree failure(s)."
}

if ($ValidateOnly) {
    Write-Host "`nReady: all worktrees can be synchronized from this launcher." -ForegroundColor Green
    return
}

Write-Host "`nDone: master and every worker worktree are synchronized." -ForegroundColor Green

}

}
finally {
    if ($syncLogOwned) { Stop-SyncLog }
}