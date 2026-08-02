#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(1, 2)]
    [int]$WorkerNumber,

    [switch]$ValidateOnly,

    [switch]$ResolveConflicts
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
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$WorkerName,

        [switch]$ResolveConflicts
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

    if ($ResolveConflicts) {
        try {
            & git -C $WorkingDirectory rerere | Out-Host
            if ($LASTEXITCODE -ne 0) {
                throw "git rerere failed."
            }

            $remainingConflicts = @(& git -C $WorkingDirectory diff --name-only --diff-filter=U)
            if ($LASTEXITCODE -ne 0) {
                throw "Could not inspect unresolved paths."
            }

            if ($remainingConflicts.Count -gt 0) {
                Write-Host "`n$WorkerName has new conflicts that need a semantic decision:" -ForegroundColor Yellow
                $remainingConflicts | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
                Write-Host "Resolve these files in the $WorkerName worktree: $WorkingDirectory"
                Write-Host "Preserve both agents' intended behavior, run any focused validation needed, and return here."

                while ($true) {
                    $confirmation = Read-Host "Type RESOLVED to validate and continue, or ABORT to restore the clean worktree"
                    if ($confirmation -eq "ABORT") {
                        break
                    }
                    if ($confirmation -ne "RESOLVED") {
                        Write-Host "Enter exactly RESOLVED or ABORT." -ForegroundColor Yellow
                        continue
                    }

                    $markerOutput = & git -C $WorkingDirectory grep -n `
                        -e "^<<<<<<< " -e "^||||||| " -e "^=======$" -e "^>>>>>>> " `
                        -- @remainingConflicts
                    $markerExitCode = $LASTEXITCODE
                    if ($markerExitCode -eq 0) {
                        Write-Host "Conflict markers remain:`n$($markerOutput -join [Environment]::NewLine)" -ForegroundColor Yellow
                        continue
                    }
                    if ($markerExitCode -ne 1) {
                        throw "Could not scan resolved files for conflict markers."
                    }

                    & git -C $WorkingDirectory rerere | Out-Host
                    if ($LASTEXITCODE -ne 0) {
                        throw "Could not record the conflict resolution."
                    }
                    & git -C $WorkingDirectory add -A -- @remainingConflicts
                    if ($LASTEXITCODE -ne 0) {
                        throw "Could not stage the resolved paths."
                    }

                    $stillUnresolved = @(& git -C $WorkingDirectory diff --name-only --diff-filter=U)
                    if ($LASTEXITCODE -ne 0) {
                        throw "Could not verify the resolved paths."
                    }
                    if ($stillUnresolved.Count -gt 0) {
                        Write-Host "Still unresolved:`n$($stillUnresolved -join [Environment]::NewLine)" -ForegroundColor Yellow
                        continue
                    }

                    & git -C $WorkingDirectory diff --cached --check
                    if ($LASTEXITCODE -ne 0) {
                        throw "The staged resolution failed git diff --check."
                    }
                    & git -C $WorkingDirectory commit --no-edit
                    if ($LASTEXITCODE -ne 0) {
                        throw "Could not commit the resolved merge."
                    }

                    Write-Host "Recorded and committed the $WorkerName conflict resolution." -ForegroundColor Green
                    return
                }
            } else {
                & git -C $WorkingDirectory commit --no-edit
                if ($LASTEXITCODE -ne 0) {
                    throw "Could not commit the previously recorded conflict resolution."
                }
                Write-Host "Reused a previously recorded $WorkerName conflict resolution." -ForegroundColor Green
                return
            }
        } catch {
            Write-Warning "Automatic conflict handling could not finish: $($_.Exception.Message)"
        }
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
    throw "$WorkerName conflicted with origin/master in: $conflictList. The merge was aborted automatically and the worktree was restored. Reconcile the branches before retrying."
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

$workerName = "Worker $WorkerNumber"
$workerSlug = "worker-$WorkerNumber"
$workerBranchExpected = "agents/$workerSlug"
$scriptRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptRoot
$commonGitDir = Invoke-Git -WorkingDirectory $repoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$workerRoot = "$primaryRoot.worktrees\$workerSlug"

if (-not (Test-Path $workerRoot -PathType Container)) {
    throw "$workerName worktree not found: $workerRoot"
}

Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @("auth", "status") | Out-Null

$primaryBranch = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("branch", "--show-current")
$workerBranch = Invoke-Git -WorkingDirectory $workerRoot -Arguments @("branch", "--show-current")
if ($primaryBranch -ne "master") {
    throw "The primary checkout must be on master, not $primaryBranch."
}
if ($workerBranch -ne $workerBranchExpected) {
    throw "$workerName must be on $workerBranchExpected, not $workerBranch."
}

Assert-CleanWorktree -WorkingDirectory $primaryRoot -Name "Master"
Assert-CleanWorktree -WorkingDirectory $workerRoot -Name $workerName

if ($ValidateOnly) {
    Write-Host "Ready: master and $workerName are clean and on the expected branches."
    return
}

Write-Host "[1/6] Updating master..."
Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "origin") | Out-Null
Invoke-GitMerge -WorkingDirectory $primaryRoot -Arguments @(
    "origin/master", "--ff-only"
) -WorkerName "Master" | Out-Null

Write-Host "[2/6] Bringing $workerName onto the current master..."
Invoke-Git -WorkingDirectory $workerRoot -Arguments @("fetch", "origin") | Out-Null
if ($ResolveConflicts) {
    Invoke-Git -WorkingDirectory $workerRoot -Arguments @("config", "rerere.enabled", "true") | Out-Null
    Invoke-Git -WorkingDirectory $workerRoot -Arguments @("config", "rerere.autoupdate", "true") | Out-Null
}
Invoke-GitMerge -WorkingDirectory $workerRoot -Arguments @(
    "origin/master", "--no-edit"
) -WorkerName $WorkerName -ResolveConflicts:$ResolveConflicts | Out-Null

Write-Host "[3/6] Pushing $workerName..."
$workerHead = Invoke-Git -WorkingDirectory $workerRoot -Arguments @("rev-parse", "HEAD")
Invoke-Git -WorkingDirectory $workerRoot -Arguments @(
    "push", "origin", "${workerHead}:refs/heads/$workerBranchExpected"
) | Out-Null

$aheadCount = [int](Invoke-Git -WorkingDirectory $primaryRoot -Arguments @(
    "rev-list", "--count", "origin/master..$workerBranchExpected"
))
if ($aheadCount -eq 0) {
    Write-Host "$workerName has no commits to merge."
    return
}

Write-Host "[4/6] Creating or reusing the $workerName pull request..."
$prJson = Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @(
    "pr", "list", "--base", "master", "--head", $workerBranchExpected,
    "--state", "open", "--json", "number,url"
)
$pullRequests = @($prJson | ConvertFrom-Json)
if ($pullRequests.Count -eq 0) {
    Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @(
        "pr", "create", "--base", "master", "--head", $workerBranchExpected, "--fill"
    ) | Out-Host
    $prJson = Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @(
        "pr", "list", "--base", "master", "--head", $workerBranchExpected,
        "--state", "open", "--json", "number,url"
    )
    $pullRequests = @($prJson | ConvertFrom-Json)
}
if ($pullRequests.Count -ne 1) {
    throw "Expected one open $workerName pull request, found $($pullRequests.Count)."
}

$pullRequest = $pullRequests[0]
Write-Host "[5/6] Merging $workerName PR #$($pullRequest.number): $($pullRequest.url)"
Invoke-Gh -WorkingDirectory $primaryRoot -Arguments @(
    "pr", "merge", "$($pullRequest.number)", "--merge", "--match-head-commit", $workerHead
) | Out-Host

Write-Host "[6/6] Updating master and synchronizing $workerName..."
Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "origin") | Out-Null
Invoke-GitMerge -WorkingDirectory $primaryRoot -Arguments @(
    "origin/master", "--ff-only"
) -WorkerName "Master" | Out-Null
Invoke-Git -WorkingDirectory $workerRoot -Arguments @("fetch", "origin") | Out-Null
Invoke-GitMerge -WorkingDirectory $workerRoot -Arguments @(
    "origin/master", "--ff-only"
) -WorkerName $workerName | Out-Null
Invoke-Git -WorkingDirectory $workerRoot -Arguments @("push", "-u", "origin", "HEAD") | Out-Null

Write-Host "Done: $workerName is merged, master is current, and $workerName is synchronized."