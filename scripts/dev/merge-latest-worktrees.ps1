#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(1, 2)]
    [int]$WorkerNumber,

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

function Complete-MergeConflict {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("rerere") | Out-Host
    $remaining = @(Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
        "diff", "--name-only", "--diff-filter=U"
    ))
    if ($remaining.Count -eq 0) {
        Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("commit", "--no-edit") | Out-Null
        Write-Host "Reused a recorded conflict resolution for $SourceName." -ForegroundColor Green
        return
    }

    Write-Host "`n$SourceName has new conflicts that need a semantic decision:" -ForegroundColor Yellow
    $remaining | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "Resolve them in the temporary integration worktree: $WorkingDirectory"

    while ($true) {
        $confirmation = Read-Host "Type RESOLVED to verify and continue, or ABORT to leave master unchanged"
        if ($confirmation -eq "ABORT") {
            Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("merge", "--abort") | Out-Null
            throw "Integration of $SourceName was aborted. No real worktree was modified."
        }
        if ($confirmation -ne "RESOLVED") {
            Write-Host "Enter exactly RESOLVED or ABORT." -ForegroundColor Yellow
            continue
        }

        $markers = & git -C $WorkingDirectory grep -n `
            -e "^<<<<<<< " -e "^||||||| " -e "^=======$" -e "^>>>>>>> " `
            -- @remaining
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Conflict markers remain:`n$($markers -join [Environment]::NewLine)" -ForegroundColor Yellow
            continue
        }
        if ($LASTEXITCODE -ne 1) {
            throw "Could not scan resolved files for conflict markers."
        }

        Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("rerere") | Out-Host
        Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments (@("add", "--") + $remaining) | Out-Null
        $unresolved = @(Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
            "diff", "--name-only", "--diff-filter=U"
        ))
        if ($unresolved.Count -gt 0) {
            Write-Host "Still unresolved:`n$($unresolved -join [Environment]::NewLine)" -ForegroundColor Yellow
            continue
        }

        Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("diff", "--cached", "--check") | Out-Null
        Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("commit", "--no-edit") | Out-Null
        Write-Host "Recorded the conflict resolution for $SourceName." -ForegroundColor Green
        return
    }
}

function Get-WorktreeHeads {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    $worktrees = [System.Collections.Generic.List[object]]::new()
    $record = @{}
    $worktreeOutput = @(Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
        "worktree", "list", "--porcelain"
    )) + ""

    foreach ($line in $worktreeOutput) {
        if (-not $line) {
            if ($record.worktree -and $record.HEAD -and
                $record.branch -match "^refs/heads/agents/worker-(1|2)$") {
                $worktrees.Add([pscustomobject]@{
                    Path = $record.worktree
                    Head = $record.HEAD
                    Branch = ($record.branch -replace "^refs/heads/", "")
                    Number = [int]$Matches[1]
                })
            }
            $record = @{}
            continue
        }

        $parts = $line -split " ", 2
        $key = $parts[0]
        $value = $parts[1]
        if ($key -in @("worktree", "HEAD", "branch")) {
            $record[$key] = $value
        }
    }

    return $worktrees
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not available on PATH."
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = Invoke-Git -WorkingDirectory $repoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$primaryBranch = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("branch", "--show-current")
if ($primaryBranch -ne "master") {
    throw "The primary checkout must be on master, not $primaryBranch."
}
$workerNumbers = if ($PSBoundParameters.ContainsKey("WorkerNumber")) {
    @($WorkerNumber)
} else {
    @(1, 2)
}

Write-Host "Fetching the latest origin/master..." -ForegroundColor Cyan
Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "origin") | Out-Null

$originMaster = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("rev-parse", "origin/master")
$primaryHead = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("rev-parse", "HEAD")
$sources = [System.Collections.Generic.List[object]]::new()
$sources.Add([pscustomobject]@{
    Path = $primaryRoot
    Head = $primaryHead
    Branch = "master"
})
foreach ($worktree in Get-WorktreeHeads -WorkingDirectory $primaryRoot) {
    if ($worktree.Number -in $workerNumbers) {
        $sources.Add($worktree)
    }
}
foreach ($number in $workerNumbers) {
    $remoteBranch = "origin/agents/worker-$number"
    & git -C $primaryRoot rev-parse --verify --quiet $remoteBranch | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $remoteHead = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("rev-parse", $remoteBranch)
        $sources.Add([pscustomobject]@{
            Path = $remoteBranch
            Head = $remoteHead
            Branch = $remoteBranch
        })
    } elseif ($LASTEXITCODE -ne 1) {
        throw "Could not inspect $remoteBranch."
    }
}

Write-Host "Committed worktree heads selected for integration:" -ForegroundColor Cyan
foreach ($source in $sources) {
    $shortHead = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("rev-parse", "--short", $source.Head)
    Write-Host "  $($source.Branch) at $shortHead ($($source.Path))"
}
Write-Host "Uncommitted, staged, and untracked worker files are intentionally ignored."

if ($ValidateOnly) {
    Write-Host "Ready: committed worktree heads can be integrated without modifying worker worktrees."
    return
}

$integrationRoot = Join-Path ([System.IO.Path]::GetTempPath()) "tripplanner-merge-$([guid]::NewGuid().ToString('N'))"
$integrationAdded = $false

try {
    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @(
        "worktree", "add", "--detach", $integrationRoot, $originMaster
    ) | Out-Null
    $integrationAdded = $true
    Invoke-Git -WorkingDirectory $integrationRoot -Arguments @("config", "rerere.enabled", "true") | Out-Null
    Invoke-Git -WorkingDirectory $integrationRoot -Arguments @("config", "rerere.autoupdate", "true") | Out-Null

    foreach ($source in $sources) {
        & git -C $integrationRoot merge-base --is-ancestor $source.Head HEAD
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Already integrated: $($source.Branch) at $($source.Head.Substring(0, 7))."
            continue
        }
        if ($LASTEXITCODE -ne 1) {
            throw "Could not compare $($source.Branch) with the integration head."
        }

        Write-Host "Merging committed $($source.Branch) head $($source.Head.Substring(0, 7))..." -ForegroundColor Cyan
        & git -C $integrationRoot merge --no-edit --no-ff $source.Head
        if ($LASTEXITCODE -ne 0) {
            Complete-MergeConflict -WorkingDirectory $integrationRoot -SourceName $source.Branch
        }
    }

    $resultHead = Invoke-Git -WorkingDirectory $integrationRoot -Arguments @("rev-parse", "HEAD")
    if ($resultHead -ne $originMaster) {
        Write-Host "Pushing the integrated result to master..." -ForegroundColor Cyan
        Invoke-Git -WorkingDirectory $integrationRoot -Arguments @(
            "push", "origin", "${resultHead}:refs/heads/master"
        ) | Out-Null
    } else {
        Write-Host "No committed worktree changes need integration."
    }
} finally {
    if ($integrationAdded) {
        & git -C $primaryRoot worktree remove --force $integrationRoot 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not remove temporary integration worktree: $integrationRoot"
        }
    }
}

$stashCreated = $false
$primaryChanges = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("status", "--porcelain")
if ($primaryChanges) {
    Write-Host "Temporarily preserving uncommitted primary changes..." -ForegroundColor Cyan
    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @(
        "stash", "push", "--include-untracked", "--message", "merge-latest-worktrees temporary primary changes"
    ) | Out-Null
    $stashCreated = $true
}

try {
    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "origin") | Out-Null
    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("merge", "origin/master", "--ff-only") | Out-Null
} finally {
    if ($stashCreated) {
        Write-Host "Restoring uncommitted primary changes..." -ForegroundColor Cyan
        & git -C $primaryRoot stash pop --index
        if ($LASTEXITCODE -ne 0) {
            throw "Primary changes overlap the new master. Resolve the primary worktree; the safety stash was retained for 'git stash pop --index'. Worker worktrees were not modified."
        }
    }
}

$updatedHead = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("rev-parse", "HEAD")
Write-Host "Done: master is current at $($updatedHead.Substring(0, 7)); worker worktrees were untouched." -ForegroundColor Green