#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$ValidateOnly
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

function Invoke-GitMerge {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & git -C $WorkingDirectory merge @Arguments
    if ($LASTEXITCODE -eq 0) {
        return $output
    }

    $conflicts = & git -C $WorkingDirectory diff --name-only --diff-filter=U
    & git -C $WorkingDirectory rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "git merge $($Arguments -join ' ') failed in $WorkingDirectory."
    }

    & git -C $WorkingDirectory merge --abort
    if ($LASTEXITCODE -ne 0) {
        throw "git merge failed and its automatic abort also failed in $WorkingDirectory. Resolve the merge manually."
    }

    $remainingChanges = & git -C $WorkingDirectory status --porcelain
    if ($LASTEXITCODE -ne 0 -or $remainingChanges) {
        throw "git merge was aborted, but $WorkingDirectory was not restored to a clean state. Inspect it before retrying."
    }

    $conflictList = if ($conflicts) { $conflicts -join ", " } else { "unknown paths" }
    throw "Worker 1 conflicted with origin/master in: $conflictList. The merge was aborted automatically and the worktree was restored. Reconcile the branches before retrying."
}

function Invoke-Gh {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Push-Location $WorkingDirectory
    try {
        $output = & gh @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "gh $($Arguments -join ' ') failed."
        }
        return $output
    } finally {
        Pop-Location
    }
}

function Assert-CleanWorktree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $changes = Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("status", "--porcelain")
    if ($changes) {
        throw "$Name has uncommitted changes. Ask its agent to commit and push first.`n$($changes -join [Environment]::NewLine)"
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not available on PATH."
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI is not available on PATH. Install it and run 'gh auth login' once."
}

$scriptRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptRoot
$commonGitDir = Invoke-Git -WorkingDirectory $repoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$workerRoot = "$primaryRoot.worktrees\worker-1"

if (-not (Test-Path $workerRoot -PathType Container)) {
    throw "Worker 1 worktree not found: $workerRoot"
}

Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @("auth", "status") | Out-Null

$primaryBranch = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("branch", "--show-current")
$workerBranch = Invoke-Git -WorkingDirectory $workerRoot -Arguments @("branch", "--show-current")
if ($primaryBranch -ne "master") {
    throw "The primary checkout must be on master, not $primaryBranch."
}
if ($workerBranch -ne "agents/worker-1") {
    throw "Worker 1 must be on agents/worker-1, not $workerBranch."
}

Assert-CleanWorktree -WorkingDirectory $primaryRoot -Name "Master"
Assert-CleanWorktree -WorkingDirectory $workerRoot -Name "Worker 1"

if ($ValidateOnly) {
    Write-Host "Ready: master and Worker 1 are clean and on the expected branches."
    return
}

Write-Host "[1/6] Updating master..."
Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "origin") | Out-Null
Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("pull", "--ff-only", "origin", "master") | Out-Null

Write-Host "[2/6] Bringing Worker 1 onto the current master..."
Invoke-GitMerge -WorkingDirectory $workerRoot -Arguments @("origin/master", "--no-edit") | Out-Null

Write-Host "[3/6] Pushing Worker 1..."
Invoke-Git -WorkingDirectory $workerRoot -Arguments @("push", "-u", "origin", "HEAD") | Out-Null

$aheadCount = [int](Invoke-Git -WorkingDirectory $primaryRoot -Arguments @(
    "rev-list", "--count", "origin/master..agents/worker-1"
))
if ($aheadCount -eq 0) {
    Write-Host "Worker 1 has no commits to merge."
    return
}

Write-Host "[4/6] Creating or reusing the pull request..."
$prJson = Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @(
    "pr", "list", "--base", "master", "--head", "agents/worker-1",
    "--state", "open", "--json", "number,url"
)
$pullRequests = @($prJson | ConvertFrom-Json)
if ($pullRequests.Count -eq 0) {
    Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @(
        "pr", "create", "--base", "master", "--head", "agents/worker-1", "--fill"
    ) | Out-Host
    $prJson = Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @(
        "pr", "list", "--base", "master", "--head", "agents/worker-1",
        "--state", "open", "--json", "number,url"
    )
    $pullRequests = @($prJson | ConvertFrom-Json)
}
if ($pullRequests.Count -ne 1) {
    throw "Expected one open Worker 1 pull request, found $($pullRequests.Count)."
}

$pullRequest = $pullRequests[0]
Write-Host "[5/6] Merging PR #$($pullRequest.number): $($pullRequest.url)"
Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @(
    "pr", "merge", "$($pullRequest.number)", "--merge"
) | Out-Host

Write-Host "[6/6] Updating master and resetting Worker 1 for its next assignment..."
Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("pull", "--ff-only", "origin", "master") | Out-Null
Invoke-Git -WorkingDirectory $workerRoot -Arguments @("fetch", "origin") | Out-Null
Invoke-GitMerge -WorkingDirectory $workerRoot -Arguments @("origin/master", "--ff-only") | Out-Null
Invoke-Git -WorkingDirectory $workerRoot -Arguments @("push", "-u", "origin", "HEAD") | Out-Null

Write-Host "Done: Worker 1 is merged, master is current, and Worker 1 is ready for its next assignment."