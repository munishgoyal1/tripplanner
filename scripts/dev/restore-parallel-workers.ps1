#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Open the archived fixed-worker workflow in an isolated worktree.

.DESCRIPTION
  This restores the historical workflow for reference or temporary use without
  merging its orchestration code back into the current sandbox-first master.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$archiveRef = "archive/drop-workersconcept-use-sandboxes"
$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = & git -C $scriptRepoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) {
    throw "Could not resolve the primary Tripplanner checkout from $scriptRepoRoot."
}

$primaryRoot = Split-Path -Parent $commonGitDir.Trim()
$archivePath = "$primaryRoot.worktrees/archive-parallel-workers"

& git -C $primaryRoot fetch origin "refs/tags/${archiveRef}:refs/tags/${archiveRef}"
if ($LASTEXITCODE -ne 0) {
    throw "Could not fetch archive tag '$archiveRef'."
}

& git -C $primaryRoot rev-parse --verify --quiet "refs/tags/$archiveRef^{tag}" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Archive tag '$archiveRef' is missing or is not annotated."
}

if (-not (Test-Path $archivePath -PathType Container)) {
    if ($PSCmdlet.ShouldProcess($archivePath, "Create detached archive worktree from $archiveRef")) {
        & git -C $primaryRoot worktree add --detach $archivePath $archiveRef
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create archive worktree at $archivePath."
        }
    }
} else {
    & git -C $archivePath rev-parse --is-inside-work-tree | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Archive path exists but is not a Git worktree: $archivePath"
    }
}

Write-Host "[archive] $archiveRef"
Write-Host "[path]    $archivePath"
Write-Host "[note]    This checkout is read-only reference material. Do not merge it into master."

if (-not $NoOpen) {
    if (-not (Get-Command code -ErrorAction SilentlyContinue)) {
        throw "VS Code command 'code' is unavailable. Open $archivePath manually."
    }
    & code --new-window $archivePath
    if ($LASTEXITCODE -ne 0) {
        throw "VS Code could not open $archivePath."
    }
}