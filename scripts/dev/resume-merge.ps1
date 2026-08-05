#!/usr/bin/env pwsh
# Finishes any merge that the sync scripts recorded as pending after an
# agent (or the user) resolved the conflicting files, then propagates the
# integrated master into every worktree so nothing needs a re-run. Reads the
# pending state written by scripts/dev/lib/sync-common.ps1 and runs without any
# interactive prompt.
[CmdletBinding()]
param(
    [switch]$KeepIntegrationWorktree,
    [switch]$NoPropagate
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sync-common.ps1"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not available on PATH."
}

$logOwned = Start-SyncLog -Component "resume-merge"
try {
    Register-OrphanedLaneConflicts
    if (@(Get-PendingMerges).Count -eq 0) {
        Write-SyncLog "No pending merges recorded; nothing to resume."
        return
    }

    $result = Complete-PendingMerges -KeepIntegrationWorktree:$KeepIntegrationWorktree
    if ($result.StillPending -gt 0) {
        throw "$($result.StillPending) merge(s) still need resolution; resolve the files listed above, then re-run resume-merge."
    }

    if ($result.IntegrationCompleted -and -not $NoPropagate) {
        Invoke-LanePropagation -ScriptRoot $PSScriptRoot
        Write-SyncLog "Done: master and every worktree are current. No re-run needed."
    } else {
        Write-SyncLog "All pending merges resolved."
    }
} finally {
    if ($logOwned) {
        Stop-SyncLog
    }
}
