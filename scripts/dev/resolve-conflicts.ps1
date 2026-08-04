#!/usr/bin/env pwsh
# Fallback resolver: invoke the GitHub Copilot CLI to resolve the NOVEL semantic
# conflicts that the sync scripts recorded as pending, then hand off to
# resume-merge.ps1 to validate and publish. This is the scripted stand-in for
# pasting "conflict" into a chat session when you want a quick, local attempt.
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

function Resolve-CopilotCli {
    param([string]$Override)
    if ($Override) {
        if (-not (Test-Path $Override)) { throw "Copilot CLI not found at: $Override" }
        return $Override
    }
    if ($env:COPILOT_CLI -and (Test-Path $env:COPILOT_CLI)) { return $env:COPILOT_CLI }
    # Prefer the npm global install (stable, non-interactive) over any shim.
    try {
        $npmPrefix = (& npm prefix -g 2>$null)
        if ($npmPrefix) {
            $prefix = $npmPrefix.Trim()
            foreach ($name in @("copilot.cmd", "copilot")) {
                $candidate = Join-Path $prefix $name
                if (Test-Path $candidate) { return $candidate }
            }
        }
    } catch { }
    $onPath = Get-Command copilot -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty Source
    if ($onPath) { return $onPath }
    throw "GitHub Copilot CLI not found. Install with: npm install -g @github/copilot"
}

function Build-ResolutionPrompt {
    param([string[]]$Files)
    $fileList = ($Files -join ", ")
    return (
        "You are resolving Git MERGE CONFLICTS in this repository checkout. The " +
        "working tree is mid-merge and these files ONLY contain conflict markers " +
        "(<<<<<<<, |||||||, =======, >>>>>>>) shown with the common ancestor " +
        "(zdiff3): $fileList. Resolve every conflict with a correct SEMANTIC merge " +
        "that PRESERVES the intent of BOTH sides; never blanket-pick one side and " +
        "discard the other; prefer the additive or superset outcome when both " +
        "changes must coexist. Rules: edit ONLY those files; remove ALL conflict " +
        "markers and leave valid, compilable code; do NOT run git add, commit, " +
        "merge, or push and do NOT create branches (only edit files); do NOT " +
        "change unrelated code, imports, or formatting beyond what the merge needs."
    )
}

$copilot = Resolve-CopilotCli -Override $CopilotPath

$logOwned = Start-SyncLog -Component "resolve-conflicts"
try {
    $pending = @(Get-PendingMerges)
    if ($pending.Count -eq 0) {
        Write-SyncLog "No pending merges recorded; nothing to resolve."
        return
    }

    Write-SyncLog "Using Copilot CLI: $copilot"
    Write-SyncLog "Attempting Copilot resolution for $($pending.Count) pending merge(s)..."
    $unresolved = 0

    foreach ($entry in $pending) {
        $wd = [string]$entry.workingDirectory
        $label = [string]$entry.label
        if (-not (Test-Path $wd -PathType Container)) {
            Write-SyncLog -Level Warn "Working directory missing for ${label}: $wd. Skipping."
            $unresolved++
            continue
        }

        $files = @(Get-FilesWithConflictMarkers -WorkingDirectory $wd -Files @($entry.conflictedFiles))
        if ($files.Count -eq 0) {
            Write-SyncLog "$label is already marker-free; nothing for Copilot to do."
            continue
        }

        Write-SyncLog "Asking Copilot to resolve $($files.Count) file(s) for ${label}: $($files -join ', ')"
        $prompt = Build-ResolutionPrompt -Files $files
        $copilotArgs = @("-p", $prompt, "--allow-all-tools", "--deny-tool=shell(git push)")
        if ($AllowAllPaths) { $copilotArgs += "--allow-all-paths" }
        if ($Model) { $copilotArgs += @("--model", $Model) }

        Push-Location $wd
        try {
            & $copilot @copilotArgs
            $copilotExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($copilotExit -ne 0) {
            Write-SyncLog -Level Warn "Copilot exited with code $copilotExit for $label (continuing to marker check)."
        }

        $still = @(Get-FilesWithConflictMarkers -WorkingDirectory $wd -Files @($files))
        if ($still.Count -gt 0) {
            Write-SyncLog -Level Error "Copilot did not clear all markers for ${label}: $($still -join ', '). Left for manual or chat resolution."
            $unresolved++
        } else {
            Write-SyncLog "Copilot cleared all conflict markers for $label."
        }
    }

    if ($unresolved -gt 0) {
        throw "$unresolved pending merge(s) still have conflict markers after Copilot. Resolve them manually (or via chat), then run scripts/dev/resume-merge.ps1."
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
