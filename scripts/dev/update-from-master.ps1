#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(1, 2, 3)]
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
        [string]$LaneName
    )

    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("rerere") | Out-Host
    $remaining = @(Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
        "diff", "--name-only", "--diff-filter=U"
    ))
    if ($remaining.Count -eq 0) {
        Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("commit", "--no-edit") | Out-Null
        Write-Host "Reused a recorded conflict resolution in $LaneName." -ForegroundColor Green
        return
    }

    Write-Host "`n$LaneName has new conflicts that need a semantic decision:" -ForegroundColor Yellow
    $remaining | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "Resolve them in: $WorkingDirectory"

    while ($true) {
        $confirmation = Read-Host "Type RESOLVED to verify and continue, or ABORT to restore the pre-merge state"
        if ($confirmation -eq "ABORT") {
            Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("merge", "--abort") | Out-Null
            throw "$LaneName merge was aborted."
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
        Write-Host "Recorded the conflict resolution in $LaneName." -ForegroundColor Green
        return
    }
}

function Merge-RemoteRef {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$RemoteRef,

        [Parameter(Mandatory = $true)]
        [string]$LaneName
    )

    & git -C $WorkingDirectory merge --no-edit $RemoteRef
    if ($LASTEXITCODE -eq 0) {
        return
    }

    & git -C $WorkingDirectory rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not merge $RemoteRef into $LaneName."
    }

    Complete-MergeConflict -WorkingDirectory $WorkingDirectory -LaneName $LaneName
}

function Update-Lane {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Number,

        [Parameter(Mandatory = $true)]
        [string]$PrimaryRoot,

        [switch]$ValidateOnly
    )

    $laneName = if ($Number -eq 3) { "Agent 3 (master)" } else { "Agent $Number" }
    $workingDirectory = if ($Number -eq 3) {
        $PrimaryRoot
    } else {
        "$PrimaryRoot.worktrees\worker-$Number"
    }
    $branch = if ($Number -eq 3) { "master" } else { "agents/worker-$Number" }

    if (-not (Test-Path $workingDirectory -PathType Container)) {
        throw "$laneName worktree not found: $workingDirectory"
    }
    $actualBranch = Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("branch", "--show-current")
    if ($actualBranch -ne $branch) {
        throw "$laneName must be on $branch, not $actualBranch."
    }

    if ($ValidateOnly) {
        Write-Host "Ready: $laneName can receive its remote branch and origin/master."
        return
    }

    $stashCreated = $false
    $changes = Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("status", "--porcelain")
    if ($changes) {
        Write-Host "Preserving uncommitted $laneName changes..." -ForegroundColor Cyan
        Invoke-Git -WorkingDirectory $workingDirectory -Arguments @(
            "stash", "push", "--include-untracked", "--message", "update-from-master temporary $laneName changes"
        ) | Out-Null
        $stashCreated = $true
    }

    try {
        Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("config", "rerere.enabled", "true") | Out-Null
        Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("config", "rerere.autoupdate", "true") | Out-Null

        $ownRemote = "origin/$branch"
        & git -C $workingDirectory rev-parse --verify --quiet $ownRemote | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Merge-RemoteRef -WorkingDirectory $workingDirectory -RemoteRef $ownRemote -LaneName $laneName
        } elseif ($LASTEXITCODE -ne 1) {
            throw "Could not inspect $ownRemote."
        }

        if ($Number -ne 3) {
            Merge-RemoteRef -WorkingDirectory $workingDirectory -RemoteRef "origin/master" -LaneName $laneName
        }

        Invoke-Git -WorkingDirectory $workingDirectory -Arguments @(
            "push", "-u", "origin", "HEAD:refs/heads/$branch"
        ) | Out-Null
    } finally {
        if ($stashCreated) {
            & git -C $workingDirectory rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Warning "$laneName local changes remain in the safety stash until its merge conflict is resolved."
            } else {
                Write-Host "Restoring uncommitted $laneName changes..." -ForegroundColor Cyan
                & git -C $workingDirectory stash pop --index
                if ($LASTEXITCODE -ne 0) {
                    throw "$laneName local changes overlap the latest code. Resolve this worktree; the safety stash was retained."
                }
            }
        }
    }

    $head = Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("rev-parse", "--short", "HEAD")
    Write-Host "Done: $laneName is current at $head." -ForegroundColor Green
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not available on PATH."
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = Invoke-Git -WorkingDirectory $repoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$workerNumbers = if ($PSBoundParameters.ContainsKey("WorkerNumber")) {
    @($WorkerNumber)
} else {
    @(3, 1, 2)
}

if (-not $ValidateOnly) {
    Write-Host "Fetching latest remote branches..." -ForegroundColor Cyan
    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "origin") | Out-Null
}

foreach ($number in $workerNumbers) {
    Update-Lane -Number $number -PrimaryRoot $primaryRoot -ValidateOnly:$ValidateOnly
}
