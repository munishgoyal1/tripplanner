#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Create, run, update, promote, ship, and discard isolated trip-planner sandboxes.

  A sandbox is a throwaway feature environment: its own git branch
  (sandbox/<slug>), its own worktree (sbx-<slug>), its own isolated ports, and
  its own Cosmos DB Emulator database (tripplanner-sbx-<slug>). Sandboxes never
  touch the canonical dev stack (ports 8000/5173/5175) or live databases.

.EXAMPLE
    .\scripts\dev\sandbox.ps1 -New route-experiment
    .\scripts\dev\sandbox.ps1 -Run route-experiment
    .\scripts\dev\sandbox.ps1 -Update route-experiment
    .\scripts\dev\sandbox.ps1 -Promote route-experiment
    .\scripts\dev\sandbox.ps1 -Ship route-experiment -Approve
    .\scripts\dev\sandbox.ps1 -Discard route-experiment
    .\scripts\dev\sandbox.ps1 -List
#>

[CmdletBinding(SupportsShouldProcess = $true, DefaultParameterSetName = "List")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "New")]
    [string]$New,

    [Parameter(Mandatory = $true, ParameterSetName = "Run")]
    [string]$Run,

    [Parameter(Mandatory = $true, ParameterSetName = "Promote")]
    [string]$Promote,

    [Parameter(Mandatory = $true, ParameterSetName = "Update")]
    [string]$Update,

    [Parameter(Mandatory = $true, ParameterSetName = "Ship")]
    [string]$Ship,

    [Parameter(Mandatory = $true, ParameterSetName = "Discard")]
    [string]$Discard,

    [Parameter(ParameterSetName = "List")]
    [switch]$List,

    [Parameter(ParameterSetName = "New")]
    [Parameter(ParameterSetName = "Update")]
    [Parameter(ParameterSetName = "Ship")]
    [string]$BaseBranch = "master",

    [Parameter(ParameterSetName = "New")]
    [switch]$NoOpen,

    [Parameter(ParameterSetName = "Ship")]
    [switch]$Approve,

    [Parameter(ParameterSetName = "Ship")]
    [switch]$SkipValidation,

    [Parameter(ParameterSetName = "Ship")]
    [switch]$KeepSandbox,

    [Parameter(ParameterSetName = "Discard")]
    [switch]$Force,

    [Parameter(ParameterSetName = "Discard")]
    [switch]$DeleteRemoteBranch
)

$ErrorActionPreference = "Stop"

# Isolated port slots. Canonical stack uses 8000/5173/5175 and stays untouched.
$ApiBase = 8100
$FrontendBase = 5273
$LabsBase = 5275
$Step = 10
$MaxSlots = 8

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
        throw "Sandbox slug must use lowercase letters, numbers, and hyphens (for example: route-experiment)."
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
    $json = if (-not $Entries -or $Entries.Count -eq 0) {
        "[]"
    } else {
        ConvertTo-Json -InputObject $Entries -Depth 6 -AsArray
    }
    Set-Content -Path $registryPath -Value $json -Encoding UTF8
}

function Get-FreeSlot {
    param([object[]]$Entries)
    $used = @($Entries | ForEach-Object { [int]$_.slot })
    for ($i = 0; $i -lt $MaxSlots; $i++) {
        if ($used -notcontains $i) { return $i }
    }
    throw "All $MaxSlots sandbox port slots are in use. Discard a sandbox before creating another."
}

function Get-VenvPython {
    $candidates = @(
        (Join-Path $primaryRoot ".venv\Scripts\python.exe"),
        (Join-Path $scriptRepoRoot ".venv\Scripts\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate -PathType Leaf) { return $candidate }
    }
    return "python"
}

function Invoke-SandboxValidation {
    param([Parameter(Mandatory = $true)][string]$Worktree)

    Write-Host "[check]   pytest" -ForegroundColor Cyan
    $python = Get-VenvPython
    # The shared venv installs tripplanner from the primary checkout, so without
    # PYTHONPATH the suite silently imports the wrong tree and "passes".
    $previousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $Worktree "src"
    Push-Location $Worktree
    try {
        & $python -m pytest tests -q
        if ($LASTEXITCODE -ne 0) { throw "pytest failed; fix it before shipping." }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $previousPythonPath
    }

    $frontend = Join-Path $Worktree "frontend"
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

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$worktreesRoot = "$primaryRoot.worktrees"
$registryPath = Join-Path $worktreesRoot "sandboxes.json"

if ($PSCmdlet.ParameterSetName -eq "List") {
    $entries = Get-Registry
    if ($entries.Count -eq 0) {
        Write-Host "No sandboxes. Create one with: .\scripts\dev\sandbox.ps1 -New <slug>"
        return
    }
    $entries |
        Select-Object slug, slot, apiPort, frontendPort, labsPort, database, branch |
        Format-Table -AutoSize
    return
}

$slug = if ($New) { $New } elseif ($Run) { $Run } elseif ($Promote) { $Promote } `
    elseif ($Update) { $Update } elseif ($Ship) { $Ship } else { $Discard }
Assert-Slug -Name $slug
$branchName = "sandbox/$slug"
$worktreePath = Join-Path $worktreesRoot "sbx-$slug"
$database = "tripplanner-sbx-$slug"

if ($PSCmdlet.ParameterSetName -eq "New") {
    $existing = Get-Registry
    if ($existing | Where-Object { $_.slug -eq $slug }) {
        throw "Sandbox '$slug' already exists. Use -Run $slug or -List."
    }
    & git -C $scriptRepoRoot show-ref --verify --quiet "refs/heads/$branchName"
    if ($LASTEXITCODE -eq 0) {
        throw "Local branch already exists: $branchName."
    }
    if (Test-Path $worktreePath) {
        throw "Path already exists: $worktreePath."
    }
    if (-not $NoOpen -and -not (Get-Command code -ErrorAction SilentlyContinue)) {
        throw "VS Code command 'code' is unavailable. Add it to PATH or pass -NoOpen."
    }

    $slot = Get-FreeSlot -Entries $existing
    $apiPort = $ApiBase + ($slot * $Step)
    $frontendPort = $FrontendBase + ($slot * $Step)
    $labsPort = $LabsBase + ($slot * $Step)

    if (-not $PSCmdlet.ShouldProcess($worktreePath, "Create $branchName from origin/$BaseBranch")) {
        return
    }

    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("fetch", "origin", $BaseBranch)
    New-Item -ItemType Directory -Path $worktreesRoot -Force | Out-Null
    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
        "worktree", "add", "-b", $branchName, $worktreePath, "origin/$BaseBranch"
    )

    $sourceEnv = Join-Path $primaryRoot ".env"
    if (Test-Path $sourceEnv -PathType Leaf) {
        Copy-Item $sourceEnv (Join-Path $worktreePath ".env")
        Write-Host "[copied]  .env from the primary checkout"
    } else {
        Write-Warning "The primary checkout has no .env; create one in the sandbox worktree before running."
    }

    $entry = [pscustomobject]@{
        slug         = $slug
        slot         = $slot
        branch       = $branchName
        worktree     = $worktreePath
        apiPort      = $apiPort
        frontendPort = $frontendPort
        labsPort     = $labsPort
        database     = $database
        createdUtc   = (Get-Date).ToUniversalTime().ToString("o")
    }
    Save-Registry -Entries (@($existing) + $entry)

    Write-Host "[created] $branchName"
    Write-Host "[path]    $worktreePath"
    Write-Host "[ports]   api=$apiPort  frontend=$frontendPort  labs=$labsPort"
    Write-Host "[db]      $database (emulator)"
    Write-Host "[run]     .\scripts\dev\sandbox.ps1 -Run $slug"

    if (-not $NoOpen) {
        & code --new-window $worktreePath
        if ($LASTEXITCODE -ne 0) {
            throw "Sandbox was created, but VS Code could not open $worktreePath."
        }
    }
    return
}

$entry = Get-Registry | Where-Object { $_.slug -eq $slug } | Select-Object -First 1
if (-not $entry) {
    throw "Unknown sandbox '$slug'. Create it with: .\scripts\dev\sandbox.ps1 -New $slug"
}

if ($PSCmdlet.ParameterSetName -eq "Run") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree). Recreate it with -New $slug."
    }

    & "$PSScriptRoot\start-cosmos-emulator.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "Cosmos DB Emulator startup failed."
    }

    $python = Get-VenvPython
    $seedScript = Join-Path $entry.worktree "scripts\dev\sandbox_seed.py"
    if (Test-Path $seedScript -PathType Leaf) {
        & $python $seedScript seed --database $entry.database --if-empty
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Seeding reported an error; the sandbox will start with whatever data exists."
        }
    }

    Write-Host "Sandbox '$slug' -> http://localhost:$($entry.frontendPort)" -ForegroundColor Green
    $devSpa = Join-Path $entry.worktree "scripts\dev\dev-spa.ps1"
    & $devSpa `
        -ApiPort $entry.apiPort `
        -FrontendPort $entry.frontendPort `
        -LabsPort $entry.labsPort `
        -CosmosBackend emulator `
        -CosmosDatabase $entry.database
    return
}

if ($PSCmdlet.ParameterSetName -eq "Update") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree). Recreate it with -New $slug."
    }
    # Reuse the worker sync machinery: rerere-backed healing + resumable pending state.
    . "$PSScriptRoot/lib/sync-common.ps1"

    $wd = $entry.worktree
    $label = "Sandbox '$slug'"
    $actualBranch = (Invoke-Git -WorkingDirectory $wd -Arguments @("branch", "--show-current")).Trim()
    if ($actualBranch -ne $entry.branch) {
        throw "$label must be on $($entry.branch), not $actualBranch."
    }
    $remoteRef = "origin/$BaseBranch"

    if (-not $PSCmdlet.ShouldProcess($entry.branch, "Merge $remoteRef into the sandbox")) {
        return
    }

    $syncLogOwned = Start-SyncLog -Component "sandbox-update"
    try {
        Invoke-Git -WorkingDirectory $wd -Arguments @("fetch", "origin", $BaseBranch) | Out-Null
        Invoke-Git -WorkingDirectory $wd -Arguments @("config", "rerere.enabled", "true") | Out-Null
        Invoke-Git -WorkingDirectory $wd -Arguments @("config", "rerere.autoupdate", "true") | Out-Null
        Invoke-Git -WorkingDirectory $wd -Arguments @("config", "merge.conflictstyle", "zdiff3") | Out-Null

        # Preserve any uncommitted sandbox edits behind a safety stash, restored
        # (or retained on conflict) after the merge.
        $stashCommit = ""
        $changes = Invoke-Git -WorkingDirectory $wd -Arguments @("status", "--porcelain")
        if ($changes) {
            Write-Host "Preserving uncommitted $label changes..." -ForegroundColor Cyan
            Invoke-Git -WorkingDirectory $wd -Arguments @(
                "stash", "push", "--include-untracked", "--message", "sandbox-update temporary $slug changes"
            ) | Out-Null
            $stashCommit = Invoke-Git -WorkingDirectory $wd -Arguments @("rev-parse", "refs/stash")
        }

        try {
            & git -C $wd merge --no-edit $remoteRef
            if ($LASTEXITCODE -ne 0) {
                & git -C $wd rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "Could not merge $remoteRef into $label."
                }
                Complete-MergeConflict -WorkingDirectory $wd -Label $label -Kind "lane" `
                    -Branch $entry.branch -StashCommit $stashCommit
            }
        } finally {
            if ($stashCommit) {
                & git -C $wd rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Warning "$label local changes remain in the safety stash until the merge conflict is resolved."
                } else {
                    Restore-LaneStash -WorkingDirectory $wd -Label $label -StashCommit $stashCommit
                }
            }
        }

        $head = Invoke-Git -WorkingDirectory $wd -Arguments @("rev-parse", "--short", "HEAD")
        Write-Host "[updated] $label is current with $remoteRef at $head." -ForegroundColor Green
        Write-Host "Push when ready: git -C `"$wd`" push origin $($entry.branch)"
    } finally {
        if ($syncLogOwned) { Stop-SyncLog }
    }
    return
}

if ($PSCmdlet.ParameterSetName -eq "Promote") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree)."
    }
    $changes = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("status", "--porcelain")
    if ($changes) {
        throw "Sandbox has uncommitted changes. Commit them before promoting."
    }
    if ($PSCmdlet.ShouldProcess($entry.branch, "Fetch origin/$BaseBranch and push branch for review")) {
        Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("fetch", "origin", $BaseBranch)
        Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("push", "-u", "origin", $entry.branch)
        Write-Host "[pushed]  $($entry.branch)"
        Write-Host "Open a pull request to merge into $BaseBranch (never auto-merged):"
        Write-Host "  gh pr create --base $BaseBranch --head $($entry.branch) --fill"
        Write-Host "Run validation (pytest / npm run build) before merging."
    }
    return
}

if ($PSCmdlet.ParameterSetName -eq "Ship") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree)."
    }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI 'gh' is required by -Ship. Install it, or use -Promote and merge the PR yourself."
    }
    $changes = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("status", "--porcelain")
    if ($changes) {
        throw "Sandbox has uncommitted changes. Commit them before shipping."
    }
    $action = if ($Approve) {
        "Sync, validate, merge into $BaseBranch, and discard the sandbox"
    } else {
        "Sync, validate, and open a pull request into $BaseBranch"
    }
    if (-not $PSCmdlet.ShouldProcess($entry.branch, $action)) { return }

    Write-Host "== 1/5 sync with origin/$BaseBranch ==" -ForegroundColor Green
    & $PSCommandPath -Update $slug -BaseBranch $BaseBranch -Confirm:$false
    $conflicts = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @(
        "diff", "--name-only", "--diff-filter=U"
    )
    if ($conflicts) {
        throw "Resolve and commit these conflicts, then re-run -Ship ${slug}:`n$($conflicts -join "`n")"
    }

    Write-Host "== 2/5 validate ==" -ForegroundColor Green
    if ($SkipValidation) {
        Write-Warning "Validation skipped (-SkipValidation)."
    } else {
        Invoke-SandboxValidation -Worktree $entry.worktree
    }

    Write-Host "== 3/5 push $($entry.branch) ==" -ForegroundColor Green
    Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("push", "-u", "origin", $entry.branch)

    Write-Host "== 4/5 pull request ==" -ForegroundColor Green
    Push-Location $entry.worktree
    try {
        $prNumber = (& gh pr list --head $entry.branch --base $BaseBranch --state open --json number --jq ".[0].number" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "gh pr list failed." }
        if (-not $prNumber) {
            & gh pr create --base $BaseBranch --head $entry.branch --fill
            if ($LASTEXITCODE -ne 0) { throw "gh pr create failed." }
            $prNumber = (& gh pr list --head $entry.branch --base $BaseBranch --state open --json number --jq ".[0].number" | Out-String).Trim()
        }
        if (-not $prNumber) { throw "Could not determine the pull request number for $($entry.branch)." }
        Write-Host "[pr]      #$prNumber -> $BaseBranch"

        if (-not $Approve) {
            Write-Host "Review the PR, then merge and clean up with:" -ForegroundColor Yellow
            Write-Host "  .\scripts\dev\sandbox.ps1 -Ship $slug -Approve"
            return
        }

        Write-Host "== 5/5 merge and discard ==" -ForegroundColor Green
        & gh pr merge $prNumber --merge
        if ($LASTEXITCODE -ne 0) { throw "gh pr merge failed for #$prNumber; merge it manually." }
        Write-Host "[merged]  #$prNumber into $BaseBranch"
    } finally {
        Pop-Location
    }

    if ($KeepSandbox) {
        Write-Host "[kept]    sandbox '$slug' (-KeepSandbox)"
        return
    }
    # Discard refuses to run from inside the worktree it is about to remove.
    Push-Location $primaryRoot
    try {
        & $PSCommandPath -Discard $slug -Force -DeleteRemoteBranch -Confirm:$false
    } catch {
        # A running sandbox stack or an open editor window keeps the files locked.
        Write-Warning "Merged into $BaseBranch, but the sandbox could not be removed: $($_.Exception.Message)"
        Write-Host "Stop 'Run-Sandbox $slug', close the sandbox window, then run:" -ForegroundColor Yellow
        Write-Host "  .\scripts\sandbox\Discard-Sandbox.cmd $slug -Force -DeleteRemoteBranch"
        return
    } finally {
        Pop-Location
    }
    Write-Host "Sync your other lanes so they pick up $BaseBranch." -ForegroundColor Cyan
    return
}

if ($PSCmdlet.ParameterSetName -eq "Discard") {
    $currentPath = (Get-Location).Path.TrimEnd("\")
    if (Test-Path $entry.worktree) {
        $resolved = (Resolve-Path $entry.worktree).Path.TrimEnd("\")
        if ($currentPath -eq $resolved -or $currentPath.StartsWith("$resolved\")) {
            throw "Run -Discard from the primary checkout, not from inside the sandbox worktree."
        }
        $changes = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("status", "--porcelain")
        if ($changes -and -not $Force) {
            throw "Sandbox has uncommitted changes. Commit/push them, or pass -Force to discard anyway."
        }
    }

    if (-not $PSCmdlet.ShouldProcess($slug, "Remove sandbox worktree, branch, and emulator database")) {
        return
    }

    if (Test-Path $entry.worktree) {
        $removeArgs = @("worktree", "remove", $entry.worktree)
        if ($Force) { $removeArgs += "--force" }
        Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments $removeArgs
    } else {
        Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("worktree", "prune")
    }

    & git -C $scriptRepoRoot branch -D $entry.branch
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not delete local branch $($entry.branch); delete it manually if needed."
    }

    $python = Get-VenvPython
    $seedScript = Join-Path $scriptRepoRoot "scripts\dev\sandbox_seed.py"
    if (Test-Path $seedScript -PathType Leaf) {
        & $python $seedScript drop --database $entry.database
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not drop $($entry.database); drop it manually if the emulator is running."
        }
    }

    if ($DeleteRemoteBranch) {
        & git -C $scriptRepoRoot push origin --delete $entry.branch
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not delete remote branch $($entry.branch)."
        }
    }

    $remaining = Get-Registry | Where-Object { $_.slug -ne $slug }
    Save-Registry -Entries @($remaining)
    Write-Host "[discarded] sandbox '$slug'"
    return
}
