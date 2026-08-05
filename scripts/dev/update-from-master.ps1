#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(0, 1, 2, 3)]
    [int]$WorkerNumber,

    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sync-common.ps1"

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

function Merge-RemoteRef {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$RemoteRef,

        [Parameter(Mandatory = $true)]
        [string]$LaneName,

        [Parameter(Mandatory = $true)]
        [string]$Branch,

        [string]$StashCommit = ""
    )

    & git -C $WorkingDirectory merge --no-edit $RemoteRef
    if ($LASTEXITCODE -eq 0) {
        return
    }

    & git -C $WorkingDirectory rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not merge $RemoteRef into $LaneName."
    }

    Complete-MergeConflict -WorkingDirectory $WorkingDirectory -Label $LaneName `
        -Kind "lane" -Branch $Branch -StashCommit $StashCommit
}

function Restore-SafetyStash {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$LaneName,

        [Parameter(Mandatory = $true)]
        [string]$StashCommit
    )

    $currentStash = Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
        "rev-parse", "refs/stash"
    )
    if ($currentStash -ne $StashCommit) {
        throw "$LaneName safety stash is no longer the newest stash; it was retained."
    }

    Write-Host "Restoring uncommitted $LaneName changes..." -ForegroundColor Cyan
    & git -C $WorkingDirectory stash pop --index "stash@{0}"
    if ($LASTEXITCODE -eq 0) {
        return
    }

    $remaining = @(Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
        "diff", "--name-only", "--diff-filter=U"
    ))
    if ($remaining.Count -gt 0) {
        Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("rerere") | Out-Host
        $remaining = @(Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
            "diff", "--name-only", "--diff-filter=U"
        ))
    }

    if ($remaining.Count -gt 0) {
        $entry = Save-PendingMerge -Kind "stash" -WorkingDirectory $WorkingDirectory `
            -Label $LaneName -Branch (& git -C $WorkingDirectory branch --show-current) `
            -StashCommit $StashCommit -ConflictedFiles $remaining
        $global:TripplannerSyncPending = $true
        Write-SyncLog -Level Warn "$LaneName local changes need semantic resolution: $($remaining -join ', ')"
        throw "SYNC_CONFLICT_PENDING: $LaneName stash restore. Automatic resolution runs next; if it cannot finish, run scripts/user/Resolve-Conflicts.cmd. Details: $($entry.reportPath)"
    }

    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("diff", "--check") | Out-Null
    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
        "diff", "--cached", "--check"
    ) | Out-Null
    $currentStash = Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
        "rev-parse", "refs/stash"
    )
    if ($currentStash -ne $StashCommit) {
        throw "$LaneName conflict was resolved, but its safety stash identity changed; no stash was dropped."
    }

    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @(
        "stash", "drop", "stash@{0}"
    ) | Out-Null
    Write-Host "Reused a recorded resolution for $LaneName local changes." -ForegroundColor Green
}

function Update-Lane {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Number,

        [Parameter(Mandatory = $true)]
        [string]$PrimaryRoot,

        [switch]$ValidateOnly
    )

    $laneName = if ($Number -eq 0) { "MasterAgent (0)" } else { "Agent $Number" }
    $workingDirectory = if ($Number -eq 0) {
        $PrimaryRoot
    } else {
        "$PrimaryRoot.worktrees\worker-$Number"
    }
    $branch = if ($Number -eq 0) { "master" } else { "agents/worker-$Number" }

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
    $stashCommit = $null
    $changes = Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("status", "--porcelain")
    if ($changes) {
        Write-Host "Preserving uncommitted $laneName changes..." -ForegroundColor Cyan
        Invoke-Git -WorkingDirectory $workingDirectory -Arguments @(
            "stash", "push", "--include-untracked", "--message", "update-from-master temporary $laneName changes"
        ) | Out-Null
        $stashCreated = $true
        $stashCommit = Invoke-Git -WorkingDirectory $workingDirectory -Arguments @(
            "rev-parse", "refs/stash"
        )
    }

    try {
        Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("config", "rerere.enabled", "true") | Out-Null
        Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("config", "rerere.autoupdate", "true") | Out-Null
        Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("config", "merge.conflictstyle", "zdiff3") | Out-Null

        $ownRemote = "origin/$branch"
        & git -C $workingDirectory rev-parse --verify --quiet $ownRemote | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Merge-RemoteRef -WorkingDirectory $workingDirectory -RemoteRef $ownRemote `
                -LaneName $laneName -Branch $branch -StashCommit $stashCommit
        } elseif ($LASTEXITCODE -ne 1) {
            throw "Could not inspect $ownRemote."
        }

        if ($Number -ne 0) {
            Merge-RemoteRef -WorkingDirectory $workingDirectory -RemoteRef "origin/master" `
                -LaneName $laneName -Branch $branch -StashCommit $stashCommit
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
                Restore-SafetyStash -WorkingDirectory $workingDirectory `
                    -LaneName $laneName -StashCommit $stashCommit
            }
        }
    }

    $head = Invoke-Git -WorkingDirectory $workingDirectory -Arguments @("rev-parse", "--short", "HEAD")
    Write-Host "Done: $laneName is current at $head." -ForegroundColor Green
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not available on PATH."
}

$syncLogOwned = Start-SyncLog -Component "update-from-master"
try {

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = Invoke-Git -WorkingDirectory $repoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$workerNumbers = if ($PSBoundParameters.ContainsKey("WorkerNumber")) {
    @($WorkerNumber)
} else {
    @(0, 1, 2, 3)
}

if (-not $ValidateOnly) {
    Write-Host "Fetching latest remote branches..." -ForegroundColor Cyan
    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "origin") | Out-Null
}

foreach ($number in $workerNumbers) {
    Update-Lane -Number $number -PrimaryRoot $primaryRoot -ValidateOnly:$ValidateOnly
}

}
finally {
    if ($syncLogOwned) { Stop-SyncLog }
}
