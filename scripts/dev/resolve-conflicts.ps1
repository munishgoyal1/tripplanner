#!/usr/bin/env pwsh
# Manual entry point for the scripted conflict resolver: invoke the GitHub Copilot
# CLI to resolve the NOVEL semantic conflicts that the sync scripts recorded as
# pending, then hand off to resume-merge.ps1 to validate and publish.
#
# You normally do NOT need to run this. Run-Latest and the Sync-*-To-Latest
# launchers invoke the same resolution automatically when a sync stops on a
# conflict (see Invoke-SyncWithAutoResolve in lib/sync-common.ps1). Use this when
# automatic resolution was disabled (-NoAutoResolve or TRIPPLANNER_NO_AUTO_RESOLVE)
# or when you want to retry a resolution on its own.
#
# Separation of duties (safety): the Copilot CLI only EDITS the conflicted files.
# This script keeps control of git staging, the pre-publish validation gate, and
# the push (all via resume-merge.ps1). Copilot is denied `git push`, so it can
# never bypass the validation gate.
#
# Requires the GitHub Copilot CLI (npm install -g @github/copilot) and that it is
# signed in (run `copilot` once interactively, or set GH_TOKEN/GITHUB_TOKEN).
[CmdletBinding()]
param(
    [switch]$ResolveOnly,               # Clear markers only; do not finish/validate/push.
    [switch]$KeepIntegrationWorktree,   # Forwarded to resume-merge.ps1.
    [string]$CopilotPath,               # Override the Copilot CLI executable.
    [string]$Model,                     # Optional model, e.g. gpt-5.4.
    [switch]$AllowAllPaths              # Pass --allow-all-paths (shared worktree/.git dirs).
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sync-common.ps1"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not available on PATH."
}

# The resolution itself lives in sync-common.ps1 so the automatic in-flow path used
# by Run-Latest and this manual entry point can never drift apart.
if (-not (Resolve-CopilotCli -Override $CopilotPath)) {
    throw "GitHub Copilot CLI not found. Install with: npm install -g @github/copilot"
}

$logOwned = Start-SyncLog -Component "resolve-conflicts"
try {
    $resolved = Invoke-CopilotConflictResolution -CopilotPath $CopilotPath -Model $Model `
        -AllowAllPaths:$AllowAllPaths
    if (-not $resolved) {
        throw "Pending merge(s) still have conflict markers after Copilot. Resolve them manually (or via chat), then run scripts/dev/resume-merge.ps1."
    }

    if ($ResolveOnly) {
        Write-SyncLog "All markers cleared. -ResolveOnly set; review the edits, then run scripts/dev/resume-merge.ps1 to validate and publish."
        return
    }

    Write-SyncLog "All markers cleared. Handing off to resume-merge to validate and publish..."
    & "$PSScriptRoot/resume-merge.ps1" -KeepIntegrationWorktree:$KeepIntegrationWorktree
} finally {
    if ($logOwned) {
        Stop-SyncLog
    }
}
