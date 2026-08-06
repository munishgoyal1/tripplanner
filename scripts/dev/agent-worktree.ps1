#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Manage isolated tripplanner worktrees for parallel coding-agent windows.

.EXAMPLE
    .\scripts\dev\agent-worktree.ps1 -Create route-cache-fix

.EXAMPLE
    .\scripts\dev\agent-worktree.ps1 -Open route-cache-fix

.EXAMPLE
    .\scripts\dev\agent-worktree.ps1 -Remove route-cache-fix
#>

[CmdletBinding(SupportsShouldProcess = $true, DefaultParameterSetName = "List")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Create")]
    [string]$Create,

    [Parameter(Mandatory = $true, ParameterSetName = "Open")]
    [string]$Open,

    [Parameter(Mandatory = $true, ParameterSetName = "Remove")]
    [string]$Remove,

    [Parameter(ParameterSetName = "List")]
    [switch]$List,

    [Parameter(ParameterSetName = "Create")]
    [string]$BaseBranch = "master",

    [Parameter(ParameterSetName = "Create")]
    [switch]$NoOpen,

    [Parameter(ParameterSetName = "Remove")]
    [switch]$DeleteRemoteBranch
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & git -C $WorkingDirectory @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed in $WorkingDirectory."
    }
    return $output
}

function Assert-AgentName {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($Name -notmatch "^[a-z0-9][a-z0-9-]*$") {
        throw "Agent name must use lowercase letters, numbers, and hyphens (for example: route-cache-fix)."
    }
}

function Get-AgentWorktreePath {
    param([Parameter(Mandatory = $true)][string]$Name)
    return Join-Path $worktreesRoot $Name
}

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$worktreesRoot = "$primaryRoot.worktrees"

if ($PSCmdlet.ParameterSetName -eq "List") {
    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("worktree", "list")
    return
}

$agentName = if ($Create) { $Create } elseif ($Open) { $Open } else { $Remove }
Assert-AgentName -Name $agentName
$branchName = "agents/$agentName"
$worktreePath = Get-AgentWorktreePath -Name $agentName

if ($PSCmdlet.ParameterSetName -eq "Open") {
    if (-not (Test-Path $worktreePath -PathType Container)) {
        throw "Worktree not found: $worktreePath"
    }
    if ($PSCmdlet.ShouldProcess($worktreePath, "Open a new VS Code window")) {
        & code --new-window $worktreePath
        if ($LASTEXITCODE -ne 0) {
            throw "VS Code could not open $worktreePath."
        }
    }
    return
}

if ($PSCmdlet.ParameterSetName -eq "Create") {
    if (Test-Path $worktreePath) {
        throw "Path already exists: $worktreePath"
    }
    if (-not $NoOpen -and -not (Get-Command code -ErrorAction SilentlyContinue)) {
        throw "VS Code command 'code' is unavailable. Add it to PATH or use -NoOpen."
    }

    & git -C $scriptRepoRoot show-ref --verify --quiet "refs/heads/$branchName"
    if ($LASTEXITCODE -eq 0) {
        throw "Local branch already exists: $branchName. Use -Open $agentName if its worktree exists."
    }

    if (-not $PSCmdlet.ShouldProcess($worktreePath, "Create $branchName from origin/$BaseBranch")) {
        return
    }

    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("fetch", "origin", "--prune")
    New-Item -ItemType Directory -Path $worktreesRoot -Force | Out-Null
    & git -C $scriptRepoRoot show-ref --verify --quiet "refs/remotes/origin/$branchName"
    if ($LASTEXITCODE -eq 0) {
        Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
            "worktree", "add", "--track", "-b", $branchName, $worktreePath, "origin/$branchName"
        )
    } else {
        Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
            "worktree", "add", "-b", $branchName, $worktreePath, "origin/$BaseBranch"
        )
    }

    $sourceEnv = Join-Path $primaryRoot ".env"
    if (Test-Path $sourceEnv -PathType Leaf) {
        Copy-Item $sourceEnv (Join-Path $worktreePath ".env")
        Write-Host "[copied] .env from the primary checkout"
    } else {
        Write-Warning "The primary checkout has no .env; run setup or create one in the new worktree."
    }

    Write-Host "[created] $branchName"
    Write-Host "[path]    $worktreePath"
    Write-Host "[setup]   .\scripts\setup-dev-machine.ps1 -SkipToolInstall"

    if (-not $NoOpen) {
        & code --new-window $worktreePath
        if ($LASTEXITCODE -ne 0) {
            throw "Worktree was created, but VS Code could not open $worktreePath."
        }
    }
    return
}

if (-not (Test-Path $worktreePath -PathType Container)) {
    throw "Worktree not found: $worktreePath"
}

$currentPath = (Get-Location).Path.TrimEnd("\")
$resolvedWorktreePath = (Resolve-Path $worktreePath).Path.TrimEnd("\")
if ($currentPath -eq $resolvedWorktreePath -or $currentPath.StartsWith("$resolvedWorktreePath\")) {
    throw "Run removal from the primary checkout or another worktree, not from the worktree being removed."
}

$changes = Invoke-Git -WorkingDirectory $worktreePath -Arguments @("status", "--porcelain")
if ($changes) {
    throw "Worktree has uncommitted changes. Commit and push them before cleanup."
}

Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("fetch", "origin", "master")
& git -C $scriptRepoRoot merge-base --is-ancestor $branchName "origin/master"
if ($LASTEXITCODE -ne 0) {
    throw "$branchName is not merged into origin/master. Merge its PR before cleanup."
}

if ($PSCmdlet.ShouldProcess($worktreePath, "Remove merged worktree and local branch $branchName")) {
    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("worktree", "remove", $worktreePath)
    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("branch", "--delete", $branchName)

    if ($DeleteRemoteBranch) {
        Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
            "push", "origin", "--delete", $branchName
        )
    }
    Write-Host "[removed] $worktreePath"
}
