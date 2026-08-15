#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Two-way synchronize sandboxes with master, behind a typed gate.

.DESCRIPTION
  Merges each sandbox into master and then brings every sandbox back up to the
  resulting master, so all worktrees end on the same commit.

  With no argument, or the literal "all", this covers every registered
  sandbox. Pass a sandbox number, full slug, or short name to merge only that
  one; the closing refresh still levels every sandbox so no lane is left
  behind.

  This is the only script that pushes sandbox work to master in bulk, so it is
  deliberately rare and gated: it prints exactly what would land, then requires
  the phrase APPROVE_SANDBOX_TO_MASTER. Use it only when the sandboxes involved
  are known to be feature-clean. For the routine one-way refresh use
  sync-sbxs-from-master.ps1 instead.

  Each sandbox is merged through sandbox.ps1 -Merge, so it keeps that verb's
  gates: latest base, automatic conflict recovery, validation, pull request,
  a verified merge, and the sandbox left active afterwards.

.EXAMPLE
  ./scripts/dev/twoway-sync-master-sbx.ps1 -WhatIf
  ./scripts/dev/twoway-sync-master-sbx.ps1
  ./scripts/dev/twoway-sync-master-sbx.ps1 all
  ./scripts/dev/twoway-sync-master-sbx.ps1 2
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Position = 0)]
    [string]$Sandbox = "",
    [string]$BaseBranch = "master"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
. "$PSScriptRoot/lib/sandbox-registry.ps1"

$approvalPhrase = "APPROVE_SANDBOX_TO_MASTER"

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = & git -C $scriptRepoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) {
    throw "Could not resolve the primary Tripplanner checkout."
}
$primaryRoot = Split-Path -Parent $commonGitDir.Trim()
$branch = (& git -C $primaryRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $BaseBranch) {
    throw "The primary checkout must be on $BaseBranch before a two-way synchronization."
}

Start-RunLog -Name "twoway-sync-master-sbx" | Out-Null

Write-Host "[sync]    fetching origin/$BaseBranch" -ForegroundColor Cyan
& git -C $primaryRoot fetch -q origin $BaseBranch
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin/$BaseBranch." }
& git -C $primaryRoot merge --ff-only "origin/$BaseBranch"
if ($LASTEXITCODE -ne 0) {
    throw "Could not fast-forward the primary checkout. Commit or stash local changes first."
}

$registered = @(Get-SandboxRegistry -PrimaryRoot $primaryRoot)
if ($registered.Count -eq 0) {
    Write-Host "[ready]   No sandboxes are registered." -ForegroundColor Green
    Stop-RunLog
    return
}

# The literal "all" is the explicit spelling of the same default every other
# sandbox launcher now accepts; omitting -Sandbox keeps working too.
$isAllSandboxes = -not $Sandbox -or $Sandbox.Trim().ToLowerInvariant() -eq "all"
$targets = if ($isAllSandboxes) {
    $registered
} else {
    @(Select-SandboxEntry -Entries $registered -Reference $Sandbox)
}

# Preflight before anything is offered for approval: a sandbox holding
# uncommitted work cannot be judged from its commits alone.
$blocked = [System.Collections.Generic.List[string]]::new()
$plan = [System.Collections.Generic.List[object]]::new()
foreach ($entry in $targets) {
    $label = "#$(Get-SandboxEntryNumber -Entry $entry) $($entry.slug)"
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        $blocked.Add("${label}: worktree is missing")
        continue
    }
    $dirty = & git -C $entry.worktree status --porcelain
    if ($dirty) {
        $blocked.Add("${label}: has uncommitted changes")
        continue
    }
    $unmerged = @(& git -C $entry.worktree diff --name-only --diff-filter=U)
    if ($unmerged.Count -gt 0) {
        $blocked.Add("${label}: has unresolved conflicts: $($unmerged -join ', ')")
        continue
    }
    $commits = @(& git -C $entry.worktree log --oneline "origin/$BaseBranch..HEAD")
    $plan.Add([pscustomobject]@{
        Entry = $entry
        Label = $label
        Commits = $commits
    })
}

if ($blocked.Count -gt 0) {
    throw "Two-way synchronization needs every sandbox to be committed and conflict-free:`n$($blocked -join "`n")"
}

$withWork = @($plan | Where-Object { $_.Commits.Count -gt 0 })

$scope = if ($isAllSandboxes) { "every registered sandbox" } else { "sandbox '$($targets[0].slug)'" }
Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  TWO-WAY SANDBOX SYNCHRONIZATION                          ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝"
Write-Host ""
Write-Host "Scope: $scope."
Write-Host "Each sandbox below will be merged into $BaseBranch, then all sandboxes"
Write-Host "will be brought back up to the resulting $BaseBranch."
Write-Host ""
foreach ($item in $plan) {
    if ($item.Commits.Count -eq 0) {
        Write-Host ("  {0} — already in {1}" -f $item.Label, $BaseBranch) -ForegroundColor DarkGray
        continue
    }
    Write-Host ("  {0} — {1} commit(s) to merge:" -f $item.Label, $item.Commits.Count) -ForegroundColor Yellow
    foreach ($commit in $item.Commits) { Write-Host "      $commit" -ForegroundColor DarkGray }
}
Write-Host ""

if ($withWork.Count -eq 0) {
    Write-Host "[current] No sandbox has work for $BaseBranch; refreshing sandboxes only." -ForegroundColor Green
    & (Join-Path $PSScriptRoot "sync-sbxs-from-master.ps1") -Confirm:$false
    Stop-RunLog
    return
}

$action = "Merge $($withWork.Count) sandbox(es) into $BaseBranch and resynchronize every sandbox"
if (-not $PSCmdlet.ShouldProcess($BaseBranch, $action)) {
    Stop-RunLog
    return
}

Write-Host "This publishes sandbox work to $BaseBranch. Only proceed when every" -ForegroundColor Yellow
Write-Host "sandbox above is feature-clean." -ForegroundColor Yellow
Write-Host ""
$approval = Read-Host "Type $approvalPhrase to continue"
if ($approval -ne $approvalPhrase) {
    Write-Host ""
    Write-Host "[denied]  Approval not given; nothing was merged." -ForegroundColor Red
    Stop-RunLog
    exit 1
}
Write-Host ""
Write-Host "[approved] Proceeding." -ForegroundColor Green

$sandboxScript = Join-Path $PSScriptRoot "sandbox.ps1"
$merged = [System.Collections.Generic.List[string]]::new()
foreach ($item in $withWork) {
    Write-Host ""
    Write-Host "== merging $($item.Label) into $BaseBranch ==" -ForegroundColor Green
    # Stop at the first failure: later merges would build on a base this one
    # was supposed to establish.
    & $sandboxScript -Merge $item.Entry.slug -BaseBranch $BaseBranch -Confirm:$false
    if ($LASTEXITCODE -ne 0) {
        throw "Merging $($item.Label) failed after $($merged.Count) sandbox(es) landed: $($merged -join ', '). Fix it, then re-run."
    }
    $merged.Add($item.Entry.slug)
}

Write-Host ""
Write-Host "== bringing every sandbox up to $BaseBranch ==" -ForegroundColor Green
& (Join-Path $PSScriptRoot "sync-sbxs-from-master.ps1") -Confirm:$false
if ($LASTEXITCODE -ne 0) {
    throw "Sandbox work reached $BaseBranch, but the final refresh failed. Re-run Sync-Sbxs-FromMaster."
}

& git -C $primaryRoot fetch -q origin $BaseBranch
$baseHead = (& git -C $primaryRoot rev-parse "origin/$BaseBranch").Trim()
# The closing refresh levels every lane, so verify every lane, not just the
# sandboxes this run merged.
foreach ($entry in $registered) {
    if (-not (Test-Path $entry.worktree -PathType Container)) { continue }
    & git -C $entry.worktree merge-base --is-ancestor $baseHead HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "Sandbox '$($entry.slug)' does not contain $BaseBranch $($baseHead.Substring(0, 7)) after synchronization."
    }
}

Write-Host ""
Write-Host "[verified] $BaseBranch is at $($baseHead.Substring(0, 7)) and every sandbox contains it." -ForegroundColor Green
Write-Host "[merged]   $($merged -join ', ')" -ForegroundColor Green
Stop-RunLog
