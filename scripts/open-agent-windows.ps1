#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Open the default Tripplanner development and review workspaces.

.DESCRIPTION
  Resolves the primary checkout from Git so the launcher works from the primary
    repository or either persistent worker worktree. VS Code restores each
    workspace's editor groups, tabs, view state, terminal sessions, layout, and
    window position between launches. Agent 2 remains available through
    -IncludeWorker2 when a third parallel workstream is useful.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
        [switch]$IncludeWorker2
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$commonGitDir = & git -C $repoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) {
    throw "Could not resolve the primary Tripplanner checkout from $repoRoot."
}

$primaryRoot = Split-Path -Parent $commonGitDir.Trim()
$developmentWorkspace = @{ Name = "Agent 1 - Development"; File = "tripplanner-worker-1.code-workspace"; Root = "$primaryRoot.worktrees\worker-1" }
$worker2Workspace = @{ Name = "Agent 2 - Worker"; File = "tripplanner-worker-2.code-workspace"; Root = "$primaryRoot.worktrees\worker-2" }
$reviewWorkspace = @{ Name = "Agent 3 - Review & Integration"; File = "tripplanner-integration.code-workspace"; Root = $primaryRoot }
$workspaces = if ($IncludeWorker2) {
    @($developmentWorkspace, $worker2Workspace, $reviewWorkspace)
} else {
    @($developmentWorkspace, $reviewWorkspace)
}

if (-not (Get-Command code -ErrorAction SilentlyContinue)) {
    throw "VS Code command 'code' is unavailable. Add it to PATH, then rerun."
}

foreach ($workspace in $workspaces) {
    $workspacePath = Join-Path $primaryRoot $workspace.File
    if (-not (Test-Path $workspace.Root -PathType Container)) {
        throw "$($workspace.Name) worktree is missing: $($workspace.Root)"
    }
    if (-not (Test-Path $workspacePath -PathType Leaf)) {
        throw "$($workspace.Name) launcher is missing: $workspacePath"
    }
}

foreach ($workspace in $workspaces) {
    $workspacePath = Join-Path $primaryRoot $workspace.File
    if ($PSCmdlet.ShouldProcess($workspacePath, "Open $($workspace.Name) in a new VS Code window")) {
        & code --new-window $workspacePath
        if ($LASTEXITCODE -ne 0) {
            throw "VS Code could not open $($workspace.Name)."
        }
        Write-Host "[opened] $($workspace.Name)"
    }
}
