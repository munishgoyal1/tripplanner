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

# Sandboxes drift the same way worker lanes do, and their branches are the ones
# that live longest without seeing master. The env guard stops the sandbox
# updater from calling this script back.
$registryPath = Join-Path "$((Get-SyncPaths).PrimaryRoot).worktrees" "sandboxes.json"
if (-not $ValidateOnly -and (Test-Path $registryPath -PathType Leaf)) {
    $raw = Get-Content -Raw -Path $registryPath
    $sandboxes = if ([string]::IsNullOrWhiteSpace($raw)) { @() } else { @($raw | ConvertFrom-Json) }
    foreach ($sandbox in $sandboxes) {
        if (-not (Test-Path $sandbox.worktree -PathType Container)) { continue }
        # A promoted sandbox whose cleanup did not finish still has its folder but
        # no .git, and there is nothing to sync in it. Discard is the fix, not sync.
        & git -C $sandbox.worktree rev-parse --git-dir 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Skipping sandbox '$($sandbox.slug)': $($sandbox.worktree) is no longer a git worktree. Finish the teardown with Discard-Sandbox $($sandbox.slug)."
            continue
        }
        Write-Host "`nSynchronizing sandbox '$($sandbox.slug)'..." -ForegroundColor Cyan
        $env:TRIPPLANNER_SANDBOX_NO_SYNC = "1"
        try {
            & "$scriptRoot\sandbox.ps1" -Update $sandbox.slug -Confirm:$false
        } catch {
            $failures.Add([pscustomobject]@{
                Lane = "Sandbox '$($sandbox.slug)'"
                Error = $_.Exception.Message
            })
            Write-Warning "Sandbox '$($sandbox.slug)' could not be fully synchronized."
        } finally {
            Remove-Item Env:\TRIPPLANNER_SANDBOX_NO_SYNC -ErrorAction SilentlyContinue
        }
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

Write-Host "`nDone: master, every worker worktree, and every sandbox are synchronized." -ForegroundColor Green

}

}
finally {
    if ($syncLogOwned) { Stop-SyncLog }
}