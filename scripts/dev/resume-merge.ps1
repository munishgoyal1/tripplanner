#!/usr/bin/env pwsh
# Finishes any merge that the sync scripts recorded as pending after an
# agent (or the user) resolved the conflicting files. Reads the pending state
# written by scripts/dev/lib/sync-common.ps1, verifies no conflict markers
# remain, then commits, pushes, and cleans up without any interactive prompt.
[CmdletBinding()]
param(
    [switch]$KeepIntegrationWorktree
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sync-common.ps1"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not available on PATH."
}

$logOwned = Start-SyncLog -Component "resume-merge"
try {
    $paths = Get-SyncPaths
    $pending = @(Get-PendingMerges)
    if ($pending.Count -eq 0) {
        Write-SyncLog "No pending merges recorded; nothing to resume."
        return
    }

    Write-SyncLog "Resuming $($pending.Count) pending merge(s)..."
    $stillPending = [System.Collections.Generic.List[object]]::new()

    foreach ($entry in $pending) {
        $wd = [string]$entry.workingDirectory
        Write-SyncLog "Resuming $($entry.kind) merge for $($entry.label) in $wd"

        if (-not (Test-Path $wd -PathType Container)) {
            Write-SyncLog -Level Error "Working directory is missing: $wd. Dropping this entry."
            continue
        }

        $marked = @(Get-FilesWithConflictMarkers -WorkingDirectory $wd -Files @($entry.conflictedFiles))
        if ($marked.Count -gt 0) {
            Write-SyncLog -Level Error "Conflict markers still present in: $($marked -join ', '). Resolve them, then re-run resume-merge."
            $stillPending.Add($entry)
            continue
        }

        & git -C $wd rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
        $midMerge = ($LASTEXITCODE -eq 0)
        if ($midMerge) {
            & git -C $wd rerere 2>&1 | Out-Host
            Invoke-SyncGit -WorkingDirectory $wd -Arguments (@("add", "--") + @($entry.conflictedFiles)) | Out-Null
            $unresolved = @(Invoke-SyncGit -WorkingDirectory $wd -Arguments @("diff", "--name-only", "--diff-filter=U"))
            if ($unresolved.Count -gt 0) {
                Write-SyncLog -Level Error "Still unresolved after staging: $($unresolved -join ', ')."
                $stillPending.Add($entry)
                continue
            }
            Invoke-SyncGit -WorkingDirectory $wd -Arguments @("diff", "--cached", "--check") | Out-Null
            Invoke-SyncGit -WorkingDirectory $wd -Arguments @("commit", "--no-edit") | Out-Null
            Write-SyncLog "Committed the resolved merge for $($entry.label)."
        } else {
            Write-SyncLog "No merge in progress in $wd; assuming the resolution was already committed."
        }

        if ($entry.kind -eq "integration") {
            $resultHead = Invoke-SyncGit -WorkingDirectory $wd -Arguments @("rev-parse", "HEAD")
            Write-SyncLog "Pushing integrated result $($resultHead.Substring(0, 7)) to master..."
            Invoke-SyncGit -WorkingDirectory $wd -Arguments @("push", "origin", "${resultHead}:refs/heads/master") | Out-Null

            if (-not $KeepIntegrationWorktree) {
                & git -C $paths.PrimaryRoot worktree remove --force $wd 2>$null
                if ($LASTEXITCODE -ne 0) {
                    Write-SyncLog -Level Warn "Could not remove temporary integration worktree: $wd"
                }
            }

            try {
                Invoke-SyncGit -WorkingDirectory $paths.PrimaryRoot -Arguments @("fetch", "origin") | Out-Null
                $primaryBranch = Invoke-SyncGit -WorkingDirectory $paths.PrimaryRoot -Arguments @("branch", "--show-current")
                if ($primaryBranch -eq "master") {
                    Invoke-SyncGit -WorkingDirectory $paths.PrimaryRoot -Arguments @("merge", "origin/master", "--ff-only") | Out-Null
                    Write-SyncLog "Fast-forwarded primary master to the integrated result."
                }
            } catch {
                Write-SyncLog -Level Warn "Primary fast-forward skipped: $($_.Exception.Message)"
            }
        } else {
            $branch = [string]$entry.branch
            Invoke-SyncGit -WorkingDirectory $wd -Arguments @("push", "-u", "origin", "HEAD:refs/heads/$branch") | Out-Null
            Write-SyncLog "Pushed $($entry.label) to $branch."
            if ($entry.stashCommit) {
                Restore-LaneStash -WorkingDirectory $wd -Label $entry.label -StashCommit ([string]$entry.stashCommit)
            }
        }

        Write-SyncLog "Resolved pending merge for $($entry.label)."
    }

    Save-PendingList -Entries @($stillPending)
    if ($stillPending.Count -eq 0) {
        Write-SyncLog "All pending merges resolved. Re-run Run-Latest to propagate master into every lane."
    } else {
        throw "$($stillPending.Count) merge(s) still need resolution; see the sync log above."
    }
} finally {
    if ($logOwned) {
        Stop-SyncLog
    }
}
