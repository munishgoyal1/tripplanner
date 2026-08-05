#!/usr/bin/env pwsh
<#
.SYNOPSIS
  PARKED: reuse a shipped sandbox worktree instead of creating a fresh one.

  This is deliberately NOT wired into any flow. The main sandbox workflow
  (scripts/dev/sandbox.ps1) always creates from scratch, because measurement
  showed a fresh sandbox costs ~29s (1s worktree + ~28s npm install) — not
  enough to justify parking state, idle slots, and a second lifecycle verb,
  especially with several sandboxes running in parallel.

  Kept only so the capability can be restored without rewriting it. Delete this
  file if the fresh-creation flow proves sufficient.

.EXAMPLE
    .\scripts\parked\sandbox-recycle.ps1 -Recycle route-experiment
    .\scripts\parked\sandbox-recycle.ps1 -Recycle idle-0 -As next-idea
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$Recycle,
    [string]$As,
    [string]$BaseBranch = "master",
    [switch]$Force,
    [switch]$DeleteRemoteBranch,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $output = & git -C $WorkingDirectory @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed in $WorkingDirectory."
    }
    return $output
}

function Assert-Slug {
    param([Parameter(Mandatory = $true)][string]$Name)
    if ($Name -notmatch "^[a-z0-9][a-z0-9-]*$") {
        throw "Sandbox slug must use lowercase letters, numbers, and hyphens."
    }
}

function Get-Registry {
    if (-not (Test-Path $registryPath -PathType Leaf)) { return @() }
    $raw = Get-Content -Raw -Path $registryPath
    if ([string]::IsNullOrWhiteSpace($raw)) { return @() }
    return @($raw | ConvertFrom-Json)
}

function Save-Registry {
    param([object[]]$Entries)
    $sorted = @($Entries | Sort-Object slot)
    if ($sorted.Count -eq 0) {
        Set-Content -Path $registryPath -Value "[]"
        return
    }
    Set-Content -Path $registryPath -Value (ConvertTo-Json -InputObject $sorted -Depth 5)
}

function Get-VenvPython {
    $candidate = Join-Path $primaryRoot ".venv\Scripts\python.exe"
    if (Test-Path $candidate -PathType Leaf) { return $candidate }
    return "python"
}

function Stop-SandboxProcesses {
    param([Parameter(Mandatory = $true)][string]$Worktree)

    $escaped = [regex]::Escape($Worktree)
    $running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $escaped })
    foreach ($process in $running) {
        Write-Host "[stop]    $($process.Name) ($($process.ProcessId))"
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($running.Count -gt 0) { Start-Sleep -Milliseconds 500 }
}

function Remove-PendingMergesFor {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory)

    . "$PSScriptRoot/../dev/lib/sync-common.ps1"
    $target = $WorkingDirectory.TrimEnd("\")
    $remaining = @(Get-PendingMerges | Where-Object { ([string]$_.workingDirectory).TrimEnd("\") -ne $target })
    Save-PendingMerges -Entries $remaining
}

function Reset-Sandbox {
    # Keep the slot, ports, and installed dependencies (all untracked); swap the
    # folder, branch, and database.
    param(
        [Parameter(Mandatory = $true)][object]$Entry,
        [Parameter(Mandatory = $true)][string]$NewSlug,
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(Mandatory = $true)][ValidateSet("active", "idle")][string]$State,
        [switch]$DropRemoteBranch
    )

    $newBranch = "sandbox/$NewSlug"
    $newWorktree = Join-Path $worktreesRoot "sbx-$NewSlug"

    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "origin", $Base) | Out-Null
    Stop-SandboxProcesses -Worktree $Entry.worktree
    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @(
        "worktree", "move", $Entry.worktree, $newWorktree
    ) | Out-Null
    Invoke-Git -WorkingDirectory $newWorktree -Arguments @(
        "checkout", "-B", $newBranch, "origin/$Base"
    ) | Out-Null
    Invoke-Git -WorkingDirectory $newWorktree -Arguments @("reset", "--hard", "origin/$Base") | Out-Null
    Remove-PendingMergesFor -WorkingDirectory $Entry.worktree

    & git -C $primaryRoot branch -D $Entry.branch | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not delete local branch $($Entry.branch); delete it manually if needed."
    }
    if ($DropRemoteBranch) {
        & git -C $primaryRoot push origin --delete $Entry.branch | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not delete remote branch $($Entry.branch)."
        }
    }

    $seedScript = Join-Path $newWorktree "scripts\dev\sandbox_seed.py"
    if ($Entry.database -and (Test-Path $seedScript -PathType Leaf)) {
        & (Get-VenvPython) $seedScript drop --database $Entry.database | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not drop $($Entry.database); drop it manually if the emulator is running."
        }
    }

    $updated = [pscustomobject]@{
        slug         = $NewSlug
        state        = $State
        slot         = $Entry.slot
        branch       = $newBranch
        worktree     = $newWorktree
        apiPort      = $Entry.apiPort
        frontendPort = $Entry.frontendPort
        labsPort     = $Entry.labsPort
        database     = "tripplanner-sbx-$NewSlug"
        createdUtc   = (Get-Date).ToUniversalTime().ToString("o")
    }
    Save-Registry -Entries (@(Get-Registry | Where-Object { $_.slug -ne $Entry.slug }) + $updated)
    return $updated
}

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$worktreesRoot = "$primaryRoot.worktrees"
$registryPath = Join-Path $worktreesRoot "sandboxes.json"

$slug = $Recycle
Assert-Slug -Name $slug

$registry = Get-Registry
$source = $registry | Where-Object { $_.slug -eq $slug } | Select-Object -First 1
if ($As) {
    Assert-Slug -Name $As
    if (-not $source) { throw "Unknown sandbox '$slug'." }
    $targetSlug = $As
    $targetState = "active"
} elseif ($source) {
    # Park it: the next feature's name is usually unknown at shipping time.
    $targetSlug = "idle-$($source.slot)"
    $targetState = "idle"
} else {
    $idle = @($registry | Where-Object { $_.state -eq "idle" })
    if ($idle.Count -eq 0) { throw "No sandbox '$slug' and none parked." }
    if ($idle.Count -gt 1) {
        throw "Several parked sandboxes ($($idle.slug -join ', ')). Pick one with -Recycle <parked-slug> -As $slug"
    }
    $source = $idle[0]
    $targetSlug = $slug
    $targetState = "active"
}

if ($targetSlug -ne $source.slug) {
    if ($registry | Where-Object { $_.slug -eq $targetSlug }) {
        throw "Sandbox '$targetSlug' already exists."
    }
    & git -C $scriptRepoRoot show-ref --verify --quiet "refs/heads/sandbox/$targetSlug"
    if ($LASTEXITCODE -eq 0) { throw "Local branch already exists: sandbox/$targetSlug." }
    if (Test-Path (Join-Path $worktreesRoot "sbx-$targetSlug")) {
        throw "Path already exists: $(Join-Path $worktreesRoot "sbx-$targetSlug")."
    }
}
if (-not (Test-Path $source.worktree -PathType Container)) {
    throw "Sandbox worktree is missing: $($source.worktree)."
}
$currentPath = (Get-Location).Path.TrimEnd("\")
$resolved = (Resolve-Path $source.worktree).Path.TrimEnd("\")
if ($currentPath -eq $resolved -or $currentPath.StartsWith("$resolved\")) {
    throw "Run this from the primary checkout, not from inside the sandbox worktree."
}
$changes = Invoke-Git -WorkingDirectory $source.worktree -Arguments @("status", "--porcelain")
if ($changes -and -not $Force) {
    throw "Sandbox '$($source.slug)' has uncommitted changes. Commit/push them, or pass -Force."
}

$action = if ($targetState -eq "idle") { "Park" } else { "Recycle into '$targetSlug'" }
if (-not $PSCmdlet.ShouldProcess($source.worktree, "$action on origin/$BaseBranch")) { return }

$recycled = Reset-Sandbox -Entry $source -NewSlug $targetSlug -Base $BaseBranch `
    -State $targetState -DropRemoteBranch:$DeleteRemoteBranch

if ($targetState -eq "idle") {
    Write-Host "[parked]  '$($source.slug)' is now idle as '$targetSlug', reset to origin/$BaseBranch"
    Write-Host "[claim]   .\scripts\parked\sandbox-recycle.ps1 -Recycle <new-slug>"
    return
}

Write-Host "[recycled] $($source.branch) -> $($recycled.branch) (fresh from origin/$BaseBranch)"
Write-Host "[path]     $($recycled.worktree)"
Write-Host "[ports]    api=$($recycled.apiPort)  frontend=$($recycled.frontendPort)  labs=$($recycled.labsPort)"

if (-not $NoOpen -and (Get-Command code -ErrorAction SilentlyContinue)) {
    & code --new-window $recycled.worktree
}
