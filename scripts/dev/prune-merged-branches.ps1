#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Delete local branches already merged into master, verified to lose no commits.

.DESCRIPTION
  Periodic branch-clutter cleanup: finished gpt-<task>, bugfix, and other
  one-off branches pile up once their pull requests land. This finds local
  branches whose every commit is already an ancestor of origin/master (or
  master when origin cannot be reached) and removes them with `git branch -d`,
  which itself refuses to delete anything Git cannot prove is merged. That
  makes the ancestor check and the delete command a double guarantee against
  losing a commit.

  Branches attached to any worktree (the primary checkout, registered
  sandboxes, multiagent worktrees, or a temporary sync worktree) are always
  skipped: Git cannot delete a checked-out branch, and removing its worktree is
  a separate, lane-owning decision this script does not make. Branches that
  still have commits master does not are reported and left alone.

  Supports -WhatIf/-Confirm to preview before deleting anything.

.PARAMETER IncludeRemote
  After a local branch is safely deleted, also delete origin's matching branch
  if one still exists. Off by default because it changes a shared remote.

.EXAMPLE
  ./scripts/dev/prune-merged-branches.ps1 -WhatIf
  ./scripts/dev/prune-merged-branches.ps1
  ./scripts/dev/prune-merged-branches.ps1 -IncludeRemote
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$BaseBranch = "master",
    [switch]$NoFetch,
    [switch]$IncludeRemote
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sandbox-registry.ps1"

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$primaryRoot = Get-PrimaryRepositoryRoot -RepositoryRoot $scriptRepoRoot

if (-not $NoFetch) {
    & git -C $primaryRoot fetch origin --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "git fetch origin failed; comparing against the local $BaseBranch instead."
    }
}

$baseRef = "origin/$BaseBranch"
& git -C $primaryRoot rev-parse --quiet --verify $baseRef 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { $baseRef = $BaseBranch }
& git -C $primaryRoot rev-parse --quiet --verify $baseRef 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not resolve '$baseRef' to compare branches against." }

# A branch checked out in any worktree cannot be deleted by Git and is always skipped.
$attachedBranches = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($line in @(& git -C $primaryRoot worktree list --porcelain)) {
    if ($line.StartsWith("branch refs/heads/")) {
        $attachedBranches.Add($line.Substring(18)) | Out-Null
    }
}
# Registered sandboxes are owned by the sandbox tooling even if briefly missing a worktree.
foreach ($entry in (Get-SandboxRegistry -PrimaryRoot $primaryRoot)) {
    $attachedBranches.Add($entry.branch) | Out-Null
}

$localBranches = @(& git -C $primaryRoot for-each-ref --format="%(refname:short)" refs/heads)
if ($LASTEXITCODE -ne 0) { throw "Could not enumerate local branches." }
$currentBranch = (& git -C $primaryRoot branch --show-current).Trim()

$merged = [System.Collections.Generic.List[string]]::new()
$skippedAttached = [System.Collections.Generic.List[string]]::new()
$skippedUnmerged = [System.Collections.Generic.List[string]]::new()

foreach ($branch in $localBranches) {
    if ($branch -eq $BaseBranch -or $branch -eq $currentBranch) { continue }
    if ($attachedBranches.Contains($branch)) {
        $skippedAttached.Add($branch)
        continue
    }
    & git -C $primaryRoot merge-base --is-ancestor $branch $baseRef 2>$null
    if ($LASTEXITCODE -eq 0) {
        $merged.Add($branch)
    } else {
        $skippedUnmerged.Add($branch)
    }
}

if ($skippedAttached.Count -gt 0) {
    Write-Host "Skipped (checked out in a worktree or a registered sandbox):"
    foreach ($b in $skippedAttached) { Write-Host "  $b" }
}
if ($skippedUnmerged.Count -gt 0) {
    Write-Host "Skipped (not fully merged into $baseRef; would lose commits):"
    foreach ($b in $skippedUnmerged) { Write-Host "  $b" }
}

if ($merged.Count -eq 0) {
    Write-Host "No merged, unattached local branches to prune."
    exit 0
}

Write-Host "Merged into $baseRef with no unique commits:"
foreach ($b in $merged) { Write-Host "  $b" }

$deletedCount = 0
foreach ($branch in $merged) {
    if (-not $PSCmdlet.ShouldProcess($branch, "Delete local branch (git branch -d)")) { continue }
    & git -C $primaryRoot branch -d $branch 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not delete '$branch' safely; left it in place."
        continue
    }
    $deletedCount++
    Write-Host "Deleted local branch $branch"

    if ($IncludeRemote) {
        & git -C $primaryRoot ls-remote --exit-code --heads origin $branch 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            if ($PSCmdlet.ShouldProcess("origin/$branch", "Delete remote branch")) {
                & git -C $primaryRoot push origin --delete $branch
                if ($LASTEXITCODE -eq 0) { Write-Host "Deleted origin/$branch" }
                else { Write-Warning "Could not delete origin/$branch" }
            }
        }
    }
}

if (-not $WhatIfPreference) {
    Write-Host "Deleted $deletedCount of $($merged.Count) merged branch(es)."
}
