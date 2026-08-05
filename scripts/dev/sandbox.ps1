#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Create, run, update, promote, and discard isolated trip-planner sandboxes.

  A sandbox is a throwaway feature environment: its own git branch
  (sandbox/<slug>), its own worktree (sbx-<slug>), its own isolated ports, and
  its own Cosmos DB Emulator database (tripplanner-sbx-<slug>). Sandboxes never
  touch the canonical dev stack (ports 8000/5173/5175) or live databases.

.EXAMPLE
    .\scripts\dev\sandbox.ps1 -New route-experiment
    .\scripts\dev\sandbox.ps1 -Run route-experiment
    .\scripts\dev\sandbox.ps1 -Serve route-experiment
    .\scripts\dev\sandbox.ps1 -Stop route-experiment
    .\scripts\dev\sandbox.ps1 -Update route-experiment
    .\scripts\dev\sandbox.ps1 -Promote route-experiment
    .\scripts\dev\sandbox.ps1 -Discard route-experiment
    .\scripts\dev\sandbox.ps1 -List

.NOTES
  -Run holds the terminal; -Serve starts the same stack detached and waits for
  the endpoints to answer, so a sandbox is verifiable the moment it is created.
  -New serves automatically unless you pass -NoServe.

  -Promote is end to end: sync, validate, push, open the PR, merge into the base
  branch, and then verify that the base branch really contains every commit and
  that the worktree is clean. It never discards the sandbox, so the work stays
  runnable until you decide otherwise. -Ship is an alias of the same verb.

  Only a sandbox that -Promote has verified is safe to discard; -Discard refuses
  to drop a worktree that still holds uncommitted, unpushed or unmerged work
  unless you pass -Force.

  Sandboxes are always created fresh and discarded after promotion: a fresh one
  costs about 29 seconds, which is not worth a second lifecycle to manage.
#>

[CmdletBinding(SupportsShouldProcess = $true, DefaultParameterSetName = "List")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "New")]
    [string]$New,

    [Parameter(Mandatory = $true, ParameterSetName = "Run")]
    [string]$Run,

    [Parameter(Mandatory = $true, ParameterSetName = "Serve")]
    [string]$Serve,

    [Parameter(Mandatory = $true, ParameterSetName = "Stop")]
    [string]$Stop,

    [Parameter(Mandatory = $true, ParameterSetName = "Promote")]
    [Alias("Ship")]
    [string]$Promote,

    [Parameter(Mandatory = $true, ParameterSetName = "Update")]
    [string]$Update,

    [Parameter(Mandatory = $true, ParameterSetName = "Discard")]
    [string]$Discard,

    [Parameter(ParameterSetName = "List")]
    [switch]$List,

    [Parameter(ParameterSetName = "New")]
    [Parameter(ParameterSetName = "Update")]
    [Parameter(ParameterSetName = "Promote")]
    [Parameter(ParameterSetName = "Discard")]
    [string]$BaseBranch = "master",

    [Parameter(ParameterSetName = "New")]
    [switch]$NoOpen,

    [Parameter(ParameterSetName = "New")]
    [switch]$NoServe,

    [Parameter(ParameterSetName = "Promote")]
    [switch]$SkipValidation,

    [Parameter(ParameterSetName = "Discard")]
    [switch]$Force,

    [Parameter(ParameterSetName = "Discard")]
    [switch]$DeleteRemoteBranch
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
# One transcript per sandbox and verb. A served sandbox holds its -Run transcript
# open for hours, so a single shared "sandbox" name loses every concurrent run to
# a file lock. The slug is sanitised because it reaches the log path before
# Assert-Slug has had a chance to reject it.
$runVerb = $PSCmdlet.ParameterSetName.ToLowerInvariant()
$runSlug = @($New, $Run, $Serve, $Stop, $Promote, $Update, $Discard) |
    Where-Object { $_ } | Select-Object -First 1
$runLogName = if ($runSlug) {
    "sandbox-$($runSlug -replace '[^A-Za-z0-9._-]', '-')-$runVerb"
} else {
    "sandbox-$runVerb"
}
Start-RunLog -Name $runLogName | Out-Null

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
        # Pipe rather than -InputObject: -AsArray wraps an array argument in a second array.
        $Entries | ConvertTo-Json -Depth 6 -AsArray
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

function Get-SandboxOutstandingWork {
    # Everything that would be silently lost if the worktree disappeared right
    # now. Promotion asserts this is empty after the merge; discard refuses while
    # it is not. Both need the same answer, so they ask the same question.
    param(
        [Parameter(Mandatory = $true)][object]$Entry,
        [Parameter(Mandatory = $true)][string]$Base
    )

    $outstanding = @()
    $changes = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("status", "--porcelain")
    if ($changes) {
        $outstanding += "uncommitted changes:`n  $($changes -join "`n  ")"
    }
    Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("fetch", "-q", "origin") | Out-Null
    $remoteRef = "origin/$($Entry.branch)"
    $hasRemote = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @(
        "ls-remote", "--heads", "origin", $Entry.branch
    )
    if ($hasRemote) {
        $unpushed = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @(
            "log", "--oneline", "$remoteRef..HEAD"
        )
        if ($unpushed) {
            $outstanding += "commits not pushed to ${remoteRef}:`n  $($unpushed -join "`n  ")"
        }
    } else {
        $outstanding += "branch $($Entry.branch) was never pushed to origin."
    }
    $unmerged = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @(
        "log", "--oneline", "origin/$Base..HEAD"
    )
    if ($unmerged) {
        $outstanding += "commits not in origin/${Base}:`n  $($unmerged -join "`n  ")"
    }
    return $outstanding
}

function Stop-SandboxProcesses {
    # A live sandbox stack keeps node/esbuild/python binaries locked, which makes
    # `git worktree remove` fail halfway through. Only this sandbox's own processes match.
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

function Test-SandboxEndpoint {
    param([Parameter(Mandatory = $true)][string]$Url)
    try {
        return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-SandboxEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 150
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-SandboxEndpoint -Url $Url) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Start-SandboxStack {
    # -Run holds the terminal it is launched from, which makes a freshly created
    # sandbox unverifiable without a second window. Serving detaches that same
    # runner and waits until the endpoints actually answer.
    param([Parameter(Mandatory = $true)][object]$Entry)

    # Vite binds ::1 only while uvicorn binds 127.0.0.1, so probe by name and let
    # the resolver try both families.
    $apiHealth = "http://localhost:$($Entry.apiPort)/health"
    $frontendUrl = "http://localhost:$($Entry.frontendPort)/"

    if (Test-SandboxEndpoint -Url $apiHealth) {
        Write-Host "[serve]   already listening on :$($Entry.apiPort)" -ForegroundColor DarkGray
    } else {
        $logDir = Join-Path $primaryRoot "logs\sandbox"
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $log = Join-Path $logDir "$($Entry.slug).log"
        Start-Process -FilePath "pwsh" -WindowStyle Hidden `
            -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
            -ArgumentList @(
                "-NoProfile", "-File", (Join-Path $PSScriptRoot "sandbox.ps1"), "-Run", $Entry.slug
            ) | Out-Null
        Write-Host "[serve]   detached runner started; log: $log"
    }

    $apiReady = Wait-SandboxEndpoint -Url $apiHealth
    # A fresh sandbox installs frontend dependencies before Vite binds, so the SPA
    # needs a far longer budget than the API on the first serve.
    $frontendReady = Wait-SandboxEndpoint -Url $frontendUrl -TimeoutSeconds 300

    $apiMark = if ($apiReady) { "ok" } else { "NOT READY" }
    $frontendMark = if ($frontendReady) { "ok" } else { "NOT READY" }
    Write-Host "[api]     http://localhost:$($Entry.apiPort)  ($apiMark)" `
        -ForegroundColor $(if ($apiReady) { "Green" } else { "Yellow" })
    Write-Host "[spa]     http://localhost:$($Entry.frontendPort)  ($frontendMark)" `
        -ForegroundColor $(if ($frontendReady) { "Green" } else { "Yellow" })
    Write-Host "[labs]    http://localhost:$($Entry.labsPort)/catalog.html"
    Write-Host "[stop]    .\scripts\dev\sandbox.ps1 -Stop $($Entry.slug)"

    if (-not ($apiReady -and $frontendReady)) {
        Write-Warning "Sandbox endpoints did not come up. Check the log above, or run -Run $($Entry.slug) in a terminal to watch it start."
    }
    return ($apiReady -and $frontendReady)
}

function Stop-SandboxStack {
    param([Parameter(Mandatory = $true)][object]$Entry)

    foreach ($port in @($Entry.apiPort, $Entry.frontendPort, $Entry.labsPort)) {
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        $processIds = @($listeners.OwningProcess | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
        foreach ($processId in $processIds) {
            Write-Host "[stop]    :$port (PID $processId)"
            & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
        }
    }
    # The detached runner's command line carries the slug, not the worktree path,
    # so Stop-SandboxProcesses alone would leave it behind.
    $pattern = "sandbox\.ps1.+-Run\s+$([regex]::Escape($Entry.slug))(\s|$)"
    $launchers = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $pattern })
    foreach ($launcher in $launchers) {
        Write-Host "[stop]    runner ($($launcher.ProcessId))"
        Stop-Process -Id $launcher.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $Entry.worktree -PathType Container) {
        Stop-SandboxProcesses -Worktree $Entry.worktree
    }
}

function Remove-PendingMergesFor {
    # An interrupted -Update records a resumable merge; a discarded sandbox must not
    # leave one behind, or every later sync fails against the missing worktree.
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory)

    . "$PSScriptRoot/lib/sync-common.ps1"
    $target = $WorkingDirectory.TrimEnd("\")
    $remaining = @(Get-PendingMerges | Where-Object { ([string]$_.workingDirectory).TrimEnd("\") -ne $target })
    Save-PendingList -Entries $remaining
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
        Select-Object slug, slot,
            @{ Name = "serving"; Expression = {
                if (Test-SandboxEndpoint -Url "http://localhost:$($_.apiPort)/health") { "yes" } else { "no" }
            } },
            apiPort, frontendPort, labsPort, database, branch |
        Format-Table -AutoSize
    return
}

$slug = if ($New) { $New } elseif ($Run) { $Run } elseif ($Serve) { $Serve } `
    elseif ($Stop) { $Stop } elseif ($Promote) { $Promote } `
    elseif ($Update) { $Update } else { $Discard }
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

    if (-not $NoOpen) {
        & code --new-window $worktreePath
        if ($LASTEXITCODE -ne 0) {
            throw "Sandbox was created, but VS Code could not open $worktreePath."
        }
    }

    if ($NoServe) {
        Write-Host "[run]     .\scripts\dev\sandbox.ps1 -Serve $slug"
    } else {
        Start-SandboxStack -Entry $entry | Out-Null
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

if ($PSCmdlet.ParameterSetName -eq "Serve") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree). Recreate it with -New $slug."
    }
    $ready = Start-SandboxStack -Entry $entry
    if (-not $ready) { exit 1 }
    return
}

if ($PSCmdlet.ParameterSetName -eq "Stop") {
    Stop-SandboxStack -Entry $entry
    Write-Host "[stopped] sandbox '$slug'"
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
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI 'gh' is required by -Promote. Install it, or open and merge the PR yourself."
    }
    $changes = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("status", "--porcelain")
    if ($changes) {
        throw "Sandbox has uncommitted changes. Commit them before promoting."
    }
    $action = "Sync, validate, merge into $BaseBranch, and keep the sandbox"
    if (-not $PSCmdlet.ShouldProcess($entry.branch, $action)) { return }

    Write-Host "== 1/6 sync with origin/$BaseBranch ==" -ForegroundColor Green
    & $PSCommandPath -Update $slug -BaseBranch $BaseBranch -Confirm:$false
    $conflicts = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @(
        "diff", "--name-only", "--diff-filter=U"
    )
    if ($conflicts) {
        throw "Resolve and commit these conflicts, then re-run -Promote ${slug}:`n$($conflicts -join "`n")"
    }

    Write-Host "== 2/6 validate ==" -ForegroundColor Green
    if ($SkipValidation) {
        Write-Warning "Validation skipped (-SkipValidation)."
    } else {
        Invoke-SandboxValidation -Worktree $entry.worktree
    }

    Write-Host "== 3/6 push $($entry.branch) ==" -ForegroundColor Green
    Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("push", "-u", "origin", $entry.branch)

    Write-Host "== 4/6 pull request ==" -ForegroundColor Green
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

        Write-Host "== 5/6 merge ==" -ForegroundColor Green
        & gh pr merge $prNumber --merge
        if ($LASTEXITCODE -ne 0) { throw "gh pr merge failed for #$prNumber; merge it manually." }
        Write-Host "[merged]  #$prNumber into $BaseBranch"
    } finally {
        Pop-Location
    }

    # A merge that gh reports as done is not proof: branch protection can queue
    # it, and validation takes long enough for the worktree to be dirtied while
    # it runs. Promotion is only complete once the base branch demonstrably
    # contains everything and nothing is left behind here.
    Write-Host "== 6/6 verify ==" -ForegroundColor Green
    $outstanding = Get-SandboxOutstandingWork -Entry $entry -Base $BaseBranch
    if ($outstanding) {
        throw "#$prNumber merged but sandbox '$slug' is not clean, so it is NOT safe to discard:`n$($outstanding -join "`n")"
    }
    Write-Host "[verified] origin/$BaseBranch contains every commit and the worktree is clean."

    # Discarding is a separate, deliberate step: the merged sandbox stays runnable
    # until its owner says otherwise.
    Write-Host "[kept]    sandbox '$slug' is still running; discard it when you are done:" -ForegroundColor Yellow
    Write-Host "  .\scripts\sandbox\Discard-Sandbox.cmd $slug"
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
        $outstanding = Get-SandboxOutstandingWork -Entry $entry -Base $BaseBranch
        if ($outstanding -and -not $Force) {
            throw "Sandbox '$slug' still holds work that origin/$BaseBranch does not have. Promote it first, or pass -Force to discard anyway:`n$($outstanding -join "`n")"
        }
        if ($outstanding) {
            Write-Warning "Discarding sandbox '$slug' with outstanding work (-Force):`n$($outstanding -join "`n")"
        }
    }

    if (-not $PSCmdlet.ShouldProcess($slug, "Remove sandbox worktree, branch, and emulator database")) {
        return
    }

    if (Test-Path $entry.worktree) {
        Stop-SandboxStack -Entry $entry
        $removeArgs = @("worktree", "remove", $entry.worktree)
        if ($Force) { $removeArgs += "--force" }
        try {
            Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments $removeArgs
        } catch {
            # git may unregister the worktree yet fail to delete locked files; finish the
            # rest of the teardown so the registry never disagrees with reality.
            Write-Warning "Could not fully delete $($entry.worktree): $($_.Exception.Message)"
            Write-Warning "Close any window or terminal using that folder, then delete it manually."
            & git -C $scriptRepoRoot worktree prune
        }
    } else {
        Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("worktree", "prune")
    }

    Remove-PendingMergesFor -WorkingDirectory $entry.worktree

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
