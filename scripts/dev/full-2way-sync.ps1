#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Bring every local branch current, and keep going when one branch cannot.

.DESCRIPTION
  The convergence tool for when the lanes have drifted and you want them all on
    the same code again. It differs from sync-across-master-sbx.ps1 in what it
  tolerates rather than in what it does:

    * Uncommitted work stays visible in its worktree. A lane takes incoming code
        when it does not overlap that work; otherwise the exact overlap is reported
        before git changes the files. Work in progress is never published.
  * One bad lane does not stop the others. Every failure is caught, the run
    continues, and the end of the report is a numbered list of what is left.
  * Conflicts are handed to the existing resolver, which replays resolutions
    this repository has already recorded. Anything genuinely new is left for a
    person and reported.

  It is idempotent: run it, fix what it lists, run it again. A run with nothing
  to do says so and changes nothing. It never stops to ask: only commits a lane
  already had are published, so there is nothing to approve that the lane's own
  author has not already approved by committing it.

  Validation is run where it can tell you something. A lane with no commits of
  its own is never merged, so it is never validated; a lane whose changes touch
  only documentation or captured data is merged without the suite, because no
  test reads those files. Pass -AlwaysValidate to disable that judgement.

    With no positional argument, every local branch is included: registered
    sandboxes, multiagent worktrees, and branches without an attached worktree.
    Pass "sbx" to retain the original registered-sandboxes-only behavior.

.EXAMPLE
  ./scripts/dev/full-2way-sync.ps1 -WhatIf
  ./scripts/dev/full-2way-sync.ps1
    ./scripts/dev/full-2way-sync.ps1 sbx
  ./scripts/dev/full-2way-sync.ps1 -PullOnly
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "sbx")]
    [string]$Scope = "all",
    [string]$BaseBranch = "master",
    [switch]$AlwaysValidate,
    # Bring lanes up to the base without publishing any lane work to it.
    [switch]$PullOnly
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
. "$PSScriptRoot/lib/sandbox-registry.ps1"

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = & git -C $scriptRepoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) {
    throw "Could not resolve the primary Tripplanner checkout."
}
$primaryRoot = Split-Path -Parent $commonGitDir.Trim()
$primaryBranch = (& git -C $primaryRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $primaryBranch -ne $BaseBranch) {
    throw "The primary checkout must be on $BaseBranch. It is on '$primaryBranch'."
}

Start-RunLog -Name "full-2way-sync" | Out-Null

$sandboxScript = Join-Path $PSScriptRoot "sandbox.ps1"
$resolverScript = Join-Path $PSScriptRoot "resolve-sandbox-conflicts.ps1"

# Numbered at the end. Each entry is one thing a person still has to do.
$remaining = [System.Collections.Generic.List[string]]::new()
$did = [System.Collections.Generic.List[string]]::new()
$deferredPublication = [System.Collections.Generic.List[object]]::new()

function Add-Did {
    # A dry run must not claim it changed anything.
    param([string]$Entry)
    if (-not $WhatIfPreference) { $did.Add($Entry) }
}

function Add-Remaining {
    param([string]$Lane, [string]$Problem, [string]$NextStep)
    $remaining.Add("$Lane|$Problem|$NextStep")
}

function Update-PrimaryCheckout {
    param([string]$Problem, [string]$NextStep)

    if (-not $PSCmdlet.ShouldProcess(
        $BaseBranch,
        "Fast-forward primary checkout to origin/$BaseBranch"
    )) {
        return
    }
    & git -C $primaryRoot merge --ff-only "origin/$BaseBranch" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0 -and -not (
        $remaining | Where-Object { $_.StartsWith("$BaseBranch|") }
    )) {
        Add-Remaining -Lane $BaseBranch -Problem $Problem -NextStep $NextStep
    }
}

function Get-Dirty {
    param([string]$WorkingDirectory)
    return @(& git -C $WorkingDirectory status --porcelain)
}

function Get-LaneCommits {
    param([object]$Entry)
    $workingDirectory = if ($Entry.worktree) { $Entry.worktree } else { $primaryRoot }
    $head = if ($Entry.worktree) { "HEAD" } else { $Entry.branch }
    return @(& git -C $workingDirectory log --oneline "origin/$BaseBranch..$head")
}

function Get-SyncLanes {
    param([object[]]$RegisteredSandboxes)

    $lanes = [System.Collections.Generic.List[object]]::new()
    $knownBranches = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($entry in $RegisteredSandboxes) {
        $lanes.Add([pscustomobject]@{
            slug = $entry.slug
            branch = $entry.branch
            worktree = $entry.worktree
            kind = "sandbox"
        })
        $knownBranches.Add($entry.branch) | Out-Null
    }
    if ($Scope -eq "sbx") { return @($lanes) }

    $worktreePath = ""
    foreach ($line in @(& git -C $primaryRoot @("worktree", "list", "--porcelain"))) {
        if ($line.StartsWith("worktree ")) {
            $worktreePath = $line.Substring(9)
            continue
        }
        if (-not $line.StartsWith("branch refs/heads/")) { continue }
        $branchName = $line.Substring(18)
        if ($branchName -eq $BaseBranch -or $knownBranches.Contains($branchName)) { continue }
        $lanes.Add([pscustomobject]@{
            slug = $branchName
            branch = $branchName
            worktree = $worktreePath
            kind = "branch"
        })
        $knownBranches.Add($branchName) | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not enumerate Git worktrees." }

    $localBranches = @(& git -C $primaryRoot @(
        "for-each-ref", "--format=%(refname:short)", "refs/heads"
    ))
    if ($LASTEXITCODE -ne 0) { throw "Could not enumerate local branches." }
    foreach ($branchName in $localBranches) {
        if ($branchName -eq $BaseBranch -or $knownBranches.Contains($branchName)) { continue }
        $lanes.Add([pscustomobject]@{
            slug = $branchName
            branch = $branchName
            worktree = ""
            kind = "branch"
        })
        $knownBranches.Add($branchName) | Out-Null
    }
    return @($lanes)
}

function Update-BranchLane {
    param([object]$Entry)

    if (-not $PSCmdlet.ShouldProcess(
        $Entry.branch,
        "Merge origin/$BaseBranch into branch lane"
    )) {
        return $true
    }

    $temporaryWorktree = ""
    $workingDirectory = $Entry.worktree
    if (-not $workingDirectory) {
        $safeName = $Entry.branch -replace '[^A-Za-z0-9_.-]', '-'
        $temporaryWorktree = Join-Path ([System.IO.Path]::GetTempPath()) "tripplanner-sync-$PID-$safeName"
        & git -C $primaryRoot worktree add --quiet $temporaryWorktree $Entry.branch
        if ($LASTEXITCODE -ne 0) {
            Add-Remaining -Lane $Entry.slug -Problem "could not create a temporary worktree" `
                -NextStep "Check the local branch and Git worktree metadata, then run this script again."
            return $false
        }
        $workingDirectory = $temporaryWorktree
    }

    try {
        & git -C $workingDirectory merge --no-edit "origin/$BaseBranch" 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) {
            & git -C $workingDirectory rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Add-Remaining -Lane $Entry.slug -Problem "could not take $BaseBranch" `
                    -NextStep "Inspect branch '$($Entry.branch)', then run this script again."
                return $false
            }
            Write-Host "[resolve] $($Entry.slug) - replaying recorded conflict resolutions" `
                -ForegroundColor Yellow
            try {
                & $resolverScript -WorkingDirectory $workingDirectory `
                    -Lane $Entry.slug -Confirm:$false
                if ($LASTEXITCODE -ne 0) { throw "the resolver returned $LASTEXITCODE" }
                Add-Did "$($Entry.slug) - resolved a recorded merge conflict"
            } catch {
                if ($temporaryWorktree) {
                    & git -C $workingDirectory merge --abort 2>$null
                }
                Add-Remaining -Lane $Entry.slug `
                    -Problem "could not take $BaseBranch without a recorded resolution" `
                    -NextStep "Resolve $BaseBranch into branch '$($Entry.branch)', then run this script again."
                return $false
            }
        }
        & git -C $workingDirectory push -q -u origin "HEAD:refs/heads/$($Entry.branch)"
        if ($LASTEXITCODE -ne 0) {
            Add-Remaining -Lane $Entry.slug -Problem "is current locally but could not be pushed" `
                -NextStep "Push branch '$($Entry.branch)' manually, then run this script again."
            return $false
        }
        return $true
    } finally {
        if ($temporaryWorktree) {
            & git -C $primaryRoot worktree remove --force $temporaryWorktree 2>$null
        }
    }
}

function Invoke-BranchValidation {
    param([string]$WorkingDirectory)

    $pythonCandidates = @(
        (Join-Path $primaryRoot ".venv/bin/python"),
        (Join-Path $primaryRoot ".venv/Scripts/python.exe")
    )
    $python = $pythonCandidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
    if (-not $python) { $python = "python" }

    $previousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $WorkingDirectory "src"
    Push-Location $WorkingDirectory
    try {
        Write-Host "[check]   pytest" -ForegroundColor Cyan
        & $python -m pytest tests -q
        if ($LASTEXITCODE -ne 0) { throw "pytest failed; fix it before shipping." }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $previousPythonPath
    }

    $frontend = Join-Path $WorkingDirectory "frontend"
    if (-not (Test-Path (Join-Path $frontend "package.json") -PathType Leaf)) { return }
    Push-Location $frontend
    try {
        Write-Host "[check]   tsc" -ForegroundColor Cyan
        & npx tsc --noEmit
        if ($LASTEXITCODE -ne 0) { throw "tsc failed; fix it before shipping." }
        Write-Host "[check]   vitest" -ForegroundColor Cyan
        & npx vitest run
        if ($LASTEXITCODE -ne 0) { throw "vitest failed; fix it before shipping." }
    } finally {
        Pop-Location
    }
}

function Publish-BranchLane {
    param([object]$Entry, [bool]$Validate)

    $temporaryWorktree = ""
    $workingDirectory = $Entry.worktree
    if (-not $workingDirectory) {
        $safeName = $Entry.branch -replace '[^A-Za-z0-9_.-]', '-'
        $temporaryWorktree = Join-Path ([System.IO.Path]::GetTempPath()) "tripplanner-publish-$PID-$safeName"
        & git -C $primaryRoot worktree add --quiet $temporaryWorktree $Entry.branch
        if ($LASTEXITCODE -ne 0) { throw "could not create a temporary validation worktree" }
        $workingDirectory = $temporaryWorktree
    }

    try {
        if ($Validate) { Invoke-BranchValidation -WorkingDirectory $workingDirectory }
        & git -C $workingDirectory push -q -u origin "HEAD:refs/heads/$($Entry.branch)"
        if ($LASTEXITCODE -ne 0) { throw "could not push $($Entry.branch)" }

        $gh = Get-Command gh -ErrorAction SilentlyContinue
        if (-not $gh) { throw "GitHub CLI 'gh' is required to publish non-sandbox branches" }
        $prNumber = (& $gh.Source pr list --head $Entry.branch `
            --base $BaseBranch --state open --json number --jq ".[0].number" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "gh pr list failed" }
        if (-not $prNumber) {
            Push-Location $workingDirectory
            try {
                & $gh.Source pr create --base $BaseBranch --head $Entry.branch --fill
                if ($LASTEXITCODE -ne 0) { throw "gh pr create failed" }
            } finally {
                Pop-Location
            }
            $prNumber = (& $gh.Source pr list --head $Entry.branch `
                --base $BaseBranch --state open --json number --jq ".[0].number" | Out-String).Trim()
        }
        if (-not $prNumber) { throw "could not determine the pull request number" }
        & $gh.Source pr merge $prNumber --merge
        if ($LASTEXITCODE -ne 0) { throw "gh pr merge failed for #$prNumber" }
        Write-Host "[merged]  #$prNumber from $($Entry.branch)" -ForegroundColor Green
    } finally {
        if ($temporaryWorktree) {
            & git -C $primaryRoot worktree remove --force $temporaryWorktree 2>$null
        }
    }
}

function Get-Unmerged {
    # Ask git rather than matching an error message; the launchers rewrap text.
    param([string]$WorkingDirectory)
    return @(& git -C $WorkingDirectory diff --name-only --diff-filter=U)
}

function Test-MergePending {
    param([string]$WorkingDirectory)

    & git -C $WorkingDirectory rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Resolve-Pending {
    <#
      Finish a merge left half-done by an earlier run, using recorded
      resolutions only. Returns whether the lane is clear afterwards.
    #>
    param([string]$WorkingDirectory, [string]$Lane, [string]$Kind)

    $unmerged = @(Get-Unmerged -WorkingDirectory $WorkingDirectory)
    if ($unmerged.Count -eq 0 -and -not (
        Test-MergePending -WorkingDirectory $WorkingDirectory
    )) {
        return $true
    }
    Write-Host "[resolve] $Lane - replaying recorded conflict resolutions" -ForegroundColor Yellow
    try {
        if ($Kind -eq "sandbox") {
            & $resolverScript -Sandbox $Lane -Confirm:$false
        } else {
            & $resolverScript -WorkingDirectory $WorkingDirectory -Lane $Lane -Confirm:$false
        }
        if ($LASTEXITCODE -ne 0) { throw "the resolver returned $LASTEXITCODE" }
    } catch {
        # Expected whenever the conflict is genuinely new.
    }
    $left = Get-Unmerged -WorkingDirectory $WorkingDirectory
    $mergeStillPending = Test-MergePending -WorkingDirectory $WorkingDirectory
    if ($left.Count -gt 0 -or $mergeStillPending) {
        $problem = if ($left.Count -gt 0) {
            "has $($left.Count) conflicted file(s): $($left -join ', ')"
        } else {
            "still has an unfinished merge"
        }
        Add-Remaining -Lane $Lane -Problem $problem `
            -NextStep "Resolve them in $WorkingDirectory, then run this script again."
        return $false
    }
    Write-Host "[resolve] $Lane - recovered" -ForegroundColor Green
    Add-Did "$Lane - resolved a pending merge"
    return $true
}

function Update-Lane {
    <# Merge the base into one lane, recovering from a conflict once. #>
    param([object]$Entry)

    $WorkingDirectory = $Entry.worktree
    $Lane = $Entry.slug
    if ($Entry.kind -eq "branch") {
        return Update-BranchLane -Entry $Entry
    }

    try {
        & $sandboxScript -Update $Lane -BaseBranch $BaseBranch -NoSync -Confirm:$false
        if ($LASTEXITCODE -ne 0) { throw "update returned $LASTEXITCODE" }
        return $true
    } catch {
        $firstError = $_.Exception.Message
        if ((Get-Unmerged -WorkingDirectory $WorkingDirectory).Count -eq 0) {
            Add-Remaining -Lane $Lane -Problem "could not take $BaseBranch : $firstError" `
                -NextStep "Run 'scripts/dev/sandbox.ps1 -Update $Lane' in a terminal and read the error."
            return $false
        }
        if (-not (Resolve-Pending -WorkingDirectory $WorkingDirectory -Lane $Lane)) { return $false }
        try {
            & $sandboxScript -Update $Lane -BaseBranch $BaseBranch -NoSync -Confirm:$false
            if ($LASTEXITCODE -ne 0) { throw "update returned $LASTEXITCODE after recovery" }
            return $true
        } catch {
            Add-Remaining -Lane $Lane -Problem "still could not take $BaseBranch : $($_.Exception.Message)" `
                -NextStep "Run 'scripts/dev/sandbox.ps1 -Update $Lane' in a terminal and read the error."
            return $false
        }
    }
}

function Test-NeedsValidation {
    <#
      Whether landing this lane could break anything a test would catch.
      Documentation and captured data are read by no test, so validating a lane
      that only touches them spends minutes to prove nothing.
    #>
    param([object]$Entry, [string[]]$Commits)

    if ($AlwaysValidate) { return $true }
    $workingDirectory = if ($Entry.worktree) { $Entry.worktree } else { $primaryRoot }
    $head = if ($Entry.worktree) { "HEAD" } else { $Entry.branch }
    $changed = @(& git -C $workingDirectory diff --name-only "origin/$BaseBranch...$head")
    if ($LASTEXITCODE -ne 0 -or $changed.Count -eq 0) { return $true }
    $inert = $changed | Where-Object {
        $_ -like "docs/*" -or $_ -like "debug-store/*" -or $_ -like "logs/*" -or
        $_ -like "corpus/*" -or $_ -like "*.md"
    }
    return $inert.Count -ne $changed.Count
}

Write-Host "[sync]    fetching origin" -ForegroundColor Cyan
& git -C $primaryRoot fetch -q origin
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin." }

# The primary checkout is a live lane too. Git may fast-forward around
# non-overlapping WIP, but must never make those files disappear.
Update-PrimaryCheckout `
    -Problem "could not take origin/$BaseBranch without disturbing its visible work in progress" `
    -NextStep "Finish or reconcile the overlapping files in $primaryRoot, then run this script again."
$primaryAhead = @(& git -C $primaryRoot log --oneline "origin/$BaseBranch..HEAD")
if ($primaryAhead.Count -gt 0 -and $PSCmdlet.ShouldProcess($BaseBranch, "Push $($primaryAhead.Count) local commit(s)")) {
    & git -C $primaryRoot push -q origin HEAD
    if ($LASTEXITCODE -ne 0) {
        Add-Remaining -Lane $BaseBranch -Problem "has $($primaryAhead.Count) unpushed commit(s)" `
            -NextStep "Push $primaryRoot by hand, then run this script again."
    } else {
        Add-Did "$BaseBranch - pushed $($primaryAhead.Count) commit(s)"
    }
}

$registered = @(Get-SandboxRegistry -PrimaryRoot $primaryRoot)
$lanes = @(Get-SyncLanes -RegisteredSandboxes $registered)
if ($lanes.Count -eq 0) {
    Write-Host "[ready]   No branches are in scope." -ForegroundColor Green
    Stop-RunLog
    return
}

Write-Host ""
Write-Host "== 1/4 bring every lane current without hiding work ==" -ForegroundColor Green
$ready = [System.Collections.Generic.List[object]]::new()
foreach ($entry in $lanes) {
    $lane = $entry.slug
    if ($entry.worktree -and -not (Test-Path $entry.worktree -PathType Container)) {
        Add-Remaining -Lane $lane -Problem "has no worktree at $($entry.worktree)" `
            -NextStep "Recreate it with New-Sandbox, or drop it with Discard-Sandbox."
        continue
    }
    Write-Host "[lane]    $lane" -ForegroundColor Cyan
    if ($entry.worktree -and -not (
        Resolve-Pending -WorkingDirectory $entry.worktree -Lane $lane -Kind $entry.kind
    )) {
        continue
    }
    if (-not (Update-Lane -Entry $entry)) { continue }
    $ready.Add($entry)
}

Write-Host ""
Write-Host "== 2/4 publish finished lane work to $BaseBranch ==" -ForegroundColor Green
if ($PullOnly) {
    Write-Host "[skip]    -PullOnly: nothing is published." -ForegroundColor Yellow
} else {
    $withWork = [System.Collections.Generic.List[object]]::new()
    foreach ($entry in $ready) {
        $commits = @(Get-LaneCommits -Entry $entry)
        if ($commits.Count -eq 0) { continue }
        $dirty = if ($entry.worktree) { @(Get-Dirty -WorkingDirectory $entry.worktree) } else { @() }
        if ($dirty.Count -gt 0) {
            $deferredPublication.Add([pscustomobject]@{ Entry = $entry; Commits = $commits })
            Write-Host "[active]  $($entry.slug) - kept $($dirty.Count) visible WIP path(s); publication deferred" -ForegroundColor Yellow
            continue
        }
        $withWork.Add([pscustomobject]@{
            Entry = $entry
            Commits = $commits
            Validate = Test-NeedsValidation -Entry $entry -Commits $commits
        })
    }

    if ($withWork.Count -eq 0) {
        Write-Host "[current] No lane has work for $BaseBranch." -ForegroundColor Green
    } else {
        foreach ($item in $withWork) {
            $note = if ($item.Validate) { "with validation" } else { "no code changed, skipping validation" }
            Write-Host ("  {0} - {1} commit(s), {2}" -f $item.Entry.slug, $item.Commits.Count, $note)
        }
        foreach ($item in $withWork) {
            $lane = $item.Entry.slug
            Write-Host ""
            Write-Host "== merging $lane ==" -ForegroundColor Green
            if ($WhatIfPreference) {
                # Merging for real is what clears the lane first, so attempting it
                # here would report a blocker that a real run would not hit.
                Write-Host "What if: would merge $($item.Commits.Count) commit(s) into $BaseBranch"
                continue
            }
            try {
                # One lane failing must not strand the rest, so unlike the
                # gated two-way sync this keeps going and reports at the end.
                if ($item.Entry.kind -eq "sandbox") {
                    & $sandboxScript -Merge $lane -BaseBranch $BaseBranch `
                        -SkipValidation:(-not $item.Validate) -AllowDirtyPrimary -Confirm:$false
                    if ($LASTEXITCODE -ne 0) { throw "merge returned $LASTEXITCODE" }
                } else {
                    Publish-BranchLane -Entry $item.Entry -Validate $item.Validate
                }
                Add-Did "$lane - merged $($item.Commits.Count) commit(s) into $BaseBranch"
            } catch {
                $reason = $_.Exception.Message
                Add-Remaining -Lane $lane -Problem "kept its $($item.Commits.Count) commit(s); $reason" `
                    -NextStep "Nothing was lost. Address the reported gate, then re-run so the commits land."
            }
        }
    }
}

Write-Host ""
Write-Host "== 3/4 bring every lane up to the new $BaseBranch ==" -ForegroundColor Green
& git -C $primaryRoot fetch -q origin $BaseBranch
Update-PrimaryCheckout `
    -Problem "local work in progress overlaps the new origin/$BaseBranch" `
    -NextStep "Its files stayed visible and untouched. Reconcile them in $primaryRoot, then re-run."
foreach ($entry in $lanes) {
    if ($entry.worktree -and -not (Test-Path $entry.worktree -PathType Container)) { continue }
    if ($remaining | Where-Object { $_.StartsWith("$($entry.slug)|") }) { continue }
    Write-Host "[level]   $($entry.slug)" -ForegroundColor Cyan
    Update-Lane -Entry $entry | Out-Null
}

foreach ($item in $deferredPublication) {
    $commits = @(Get-LaneCommits -Entry $item.Entry)
    if ($commits.Count -gt 0) {
        Add-Remaining -Lane $item.Entry.slug `
            -Problem "kept $($commits.Count) committed change(s) out of $BaseBranch while its work in progress remains visible" `
            -NextStep "Commit or finish that active iteration, then re-run to publish it."
    }
}

Write-Host ""
Write-Host "== 4/4 verify ==" -ForegroundColor Green
& git -C $primaryRoot fetch -q origin $BaseBranch
$baseHead = (& git -C $primaryRoot rev-parse "origin/$BaseBranch").Trim()
$level = 0
foreach ($entry in $lanes) {
    if ($entry.worktree -and -not (Test-Path $entry.worktree -PathType Container)) { continue }
    $verifyRef = if ($entry.worktree) { "HEAD" } else { $entry.branch }
    $verifyRoot = if ($entry.worktree) { $entry.worktree } else { $primaryRoot }
    & git -C $verifyRoot merge-base --is-ancestor $baseHead $verifyRef 2>$null
    if ($LASTEXITCODE -eq 0) {
        $level++
    } elseif (-not $WhatIfPreference -and -not ($remaining | Where-Object { $_.StartsWith("$($entry.slug)|") })) {
        # A dry run changed nothing, so a lane being behind is the plan, not a fault.
        Add-Remaining -Lane $entry.slug -Problem "does not contain $BaseBranch $($baseHead.Substring(0, 7))" `
            -NextStep "Run this script again; if it repeats, update the lane by hand."
    }
}

Write-Host ""
Write-Host "────────────────────────────────────────────────────────────"
if ($WhatIfPreference) {
    Write-Host "Dry run. Nothing was changed; the lines above are what a real run would do."
    Stop-RunLog
    return
}
Write-Host "$BaseBranch is at $($baseHead.Substring(0, 7)). $level of $($lanes.Count) lane(s) contain it."
if ($did.Count -gt 0) {
    Write-Host ""
    Write-Host "Done this run:" -ForegroundColor Green
    foreach ($item in $did) { Write-Host "  - $item" -ForegroundColor DarkGray }
}
if ($remaining.Count -eq 0) {
    Write-Host ""
    Write-Host "Nothing left to resolve. Every lane is on $BaseBranch." -ForegroundColor Green
    Stop-RunLog
    return
}

Write-Host ""
Write-Host "Not finished ($($remaining.Count)):" -ForegroundColor Yellow
$index = 0
foreach ($item in $remaining) {
    $index++
    $parts = $item -split "\|", 3
    Write-Host ("  {0}. {1} {2}" -f $index, $parts[0], $parts[1]) -ForegroundColor Yellow
    Write-Host ("     -> {0}" -f $parts[2]) -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "Each line says what to do. Some need you; some only need a re-run once" -ForegroundColor DarkGray
Write-Host "that lane is idle. Running this again always resumes from where it is." -ForegroundColor DarkGray
Stop-RunLog
exit 1
