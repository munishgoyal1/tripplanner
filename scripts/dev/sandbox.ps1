#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Create, run, update, promote, and discard isolated trip-planner sandboxes.

  A sandbox is a throwaway feature environment. Each one gets the next free
  number, and that number is its port slot: #1 serves 8100/5273/5275, #2 serves
  8110/5283/5285. Its name is `<number>-<short-name>`, which names the branch
  (sandbox/2-lab16-chatdock), the worktree (sbx-2-lab16-chatdock), and the Cosmos
  DB Emulator database (tripplanner-sbx-2-lab16-chatdock). Sandboxes never touch
  the canonical dev stack (ports 8000/5173/5175) or live databases.

.EXAMPLE
    .\scripts\dev\sandbox.ps1 -New lab16-chatdock "Assistant dock rework" -LabId chat-agent-workspace
    .\scripts\dev\sandbox.ps1 -Run 2
    .\scripts\dev\sandbox.ps1 -Serve lab16-chatdock -IterationSummary "Adjusted the dock and passed focused UI checks."
    .\scripts\dev\sandbox.ps1 -Stop 2
    .\scripts\dev\sandbox.ps1 -Update 2
    .\scripts\dev\sandbox.ps1 -Promote 2
    .\scripts\dev\sandbox.ps1 -Discard 2
    .\scripts\dev\sandbox.ps1 -List

.NOTES
  Every verb except -New takes the number, the full name, or the short name
  without its number prefix.

  -Run holds the terminal; -Serve starts the same stack detached and waits for
  the endpoints to answer, so a sandbox is verifiable the moment it is created.
  -New serves automatically unless you pass -NoServe.

    Link a UX Lab sandbox with -LabId. After a healthy served iteration that contains
    a coherent Lab change, pass -IterationSummary to append an implemented-review version.
    Verified promotion appends Completed before sandbox cleanup.

  -New and -Update first integrate every committed worker lane through master
  (the same pass Sync-AllTo-Latest runs) and only then branch from, or merge,
  origin/master — so a sandbox never starts or sits behind work that is already
  committed elsewhere. Pass -NoSync to skip that pass. The reverse direction is
    covered too: Sync-AllTo-Latest updates every registered sandbox at its end and
    pushes the resulting committed sandbox head. This keeps the remote backup and
    future PR current; it never merges sandbox work into master.

    -Promote is end to end: sync, validate, push, open the PR, merge into the base
    branch, verify that the base branch really contains every commit and that the
    worktree is clean, then discard the sandbox. -Ship is an alias of the same verb.

  Only a sandbox that -Promote has verified is safe to discard; -Discard refuses
  to drop a worktree that still holds uncommitted, unpushed or unmerged work
    unless you pass -Force. Discard removes the local and remote sandbox branches;
    pass -DeleteRemoteBranch:$false only when the remote branch must be retained.

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

    [Parameter(ParameterSetName = "New", Position = 0)]
    [string]$Purpose = "",

    [Parameter(ParameterSetName = "New")]
    [Parameter(ParameterSetName = "Run")]
    [Parameter(ParameterSetName = "Serve")]
    [Parameter(ParameterSetName = "Promote")]
    [string]$LabId = "",

    [Parameter(ParameterSetName = "Serve")]
    [string]$IterationSummary = "",

    [Parameter(ParameterSetName = "New")]
    [switch]$NoOpen,

    [Parameter(ParameterSetName = "New")]
    [switch]$NoServe,

    [Parameter(ParameterSetName = "New")]
    [Parameter(ParameterSetName = "Update")]
    [Parameter(ParameterSetName = "Promote")]
    [switch]$NoSync,

    [Parameter(ParameterSetName = "Promote")]
    [switch]$SkipValidation,

    [Parameter(ParameterSetName = "Discard")]
    [switch]$Force,

    [Parameter(ParameterSetName = "Discard")]
    [switch]$DeleteRemoteBranch = $true
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"

# Isolated port slots. Canonical stack uses 8000/5173/5175 and stays untouched.
$ApiBase = 8100
$FrontendBase = 5273
$LabsBase = 5275
$Step = 10
$MaxSlots = 8
$MaxNameLength = 20

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

function Assert-ShortName {
    param([Parameter(Mandatory = $true)][string]$Name)
    if ($Name -notmatch "^[a-z0-9][a-z0-9-]*$") {
        throw "Sandbox name must use lowercase letters, numbers, and hyphens (for example: lab16-chatdock)."
    }
    if ($Name.Length -gt $MaxNameLength) {
        throw "Sandbox name '$Name' is $($Name.Length) characters. Keep it to $MaxNameLength so the worktree, branch, and database names stay readable."
    }
}

function Get-SandboxNumber {
    # The number is the port slot: #1 serves 8100/5273/5275, #2 serves 8110/5283/5285.
    param([Parameter(Mandatory = $true)][object]$Entry)
    return ([int]$Entry.slot) + 1
}

function Get-ShortName {
    param([Parameter(Mandatory = $true)][string]$Name)
    return ($Name -replace "^\d+-", "")
}

function Get-SandboxLauncherPath {
    param([Parameter(Mandatory = $true)][string]$Name)
    if ($IsMacOS) {
        return "./scripts/mac/sandbox/$Name.command"
    }
    return ".\scripts\sandbox\$Name.cmd"
}

function Resolve-SandboxEntry {
    # "2", "2-lab16-chatdock", and "lab16-chatdock" all reach the same sandbox,
    # so nobody has to remember which number a name was given.
    param([Parameter(Mandatory = $true)][string]$Reference)

    $entries = @(Get-Registry)
    if ($entries.Count -eq 0) {
        $launcher = Get-SandboxLauncherPath -Name "New-Sandbox"
        throw "No sandboxes are registered. Create one with: $launcher <name> `"<purpose>`""
    }
    $match = @($entries | Where-Object { $_.slug -eq $Reference })
    if ($match.Count -eq 0 -and $Reference -match "^\d+$") {
        $match = @($entries | Where-Object { (Get-SandboxNumber -Entry $_) -eq [int]$Reference })
    }
    if ($match.Count -eq 0) {
        $match = @($entries | Where-Object { (Get-ShortName -Name $_.slug) -eq (Get-ShortName -Name $Reference) })
    }
    if ($match.Count -eq 1) { return $match[0] }
    if ($match.Count -gt 1) {
        throw "'$Reference' matches more than one sandbox: $(($match | ForEach-Object { $_.slug }) -join ', '). Use the number instead."
    }
    $known = ($entries | ForEach-Object { "#$(Get-SandboxNumber -Entry $_) $($_.slug)" }) -join ", "
    throw "Unknown sandbox '$Reference'. Registered: $known."
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
    throw "All $MaxSlots sandbox numbers are in use. Discard a sandbox before creating another."
}

function Get-VenvPython {
    $pythonRelativePath = if ($IsWindows) { ".venv\Scripts\python.exe" } else { ".venv/bin/python" }
    $candidates = @(
        (Join-Path $primaryRoot $pythonRelativePath),
        (Join-Path $scriptRepoRoot $pythonRelativePath)
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
    $unmerged = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @(
        "log", "--oneline", "origin/$Base..HEAD"
    )
    if ($unmerged) {
        $outstanding += "commits not in origin/${Base}:`n  $($unmerged -join "`n  ")"
    }
    return $outstanding
}

function Save-SandboxPromotion {
    param(
        [Parameter(Mandatory = $true)][object]$Entry,
        [Parameter(Mandatory = $true)][string]$Base,
        [string]$PrNumber = ""
    )

    $entries = @(Get-Registry)
    $saved = $entries | Where-Object { $_.slug -eq $Entry.slug } | Select-Object -First 1
    if (-not $saved) { throw "Sandbox '$($Entry.slug)' disappeared from the registry." }
    $commit = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("rev-parse", "HEAD")
    $saved | Add-Member -NotePropertyName promotedUtc -NotePropertyValue `
        (Get-Date).ToUniversalTime().ToString("o") -Force
    $saved | Add-Member -NotePropertyName promotedBase -NotePropertyValue $Base -Force
    $saved | Add-Member -NotePropertyName promotedCommit -NotePropertyValue $commit -Force
    if ($PrNumber) {
        $saved | Add-Member -NotePropertyName promotionPrNumber -NotePropertyValue ([int]$PrNumber) -Force
    }
    Save-Registry -Entries $entries
}

function Save-SandboxLabId {
    param(
        [Parameter(Mandatory = $true)][object]$Entry,
        [Parameter(Mandatory = $true)][string]$LinkedLabId,
        [switch]$RecordCurrentCommit
    )

    $entries = @(Get-Registry)
    $saved = $entries | Where-Object { $_.slug -eq $Entry.slug } | Select-Object -First 1
    if (-not $saved) { throw "Sandbox '$($Entry.slug)' disappeared from the registry." }
    if ($saved.labId -and $saved.labId -ne $LinkedLabId.Trim()) {
        throw "Sandbox '$($Entry.slug)' is already linked to Lab '$($saved.labId)', not '$($LinkedLabId.Trim())'."
    }
    $saved | Add-Member -NotePropertyName labId -NotePropertyValue $LinkedLabId.Trim() -Force
    if (-not $saved.labBaselineCommit) {
        $revision = if ($RecordCurrentCommit) { "HEAD^" } else { "HEAD" }
        $commit = Invoke-Git -WorkingDirectory $saved.worktree -Arguments @("rev-parse", $revision)
        $saved | Add-Member -NotePropertyName labBaselineCommit -NotePropertyValue $commit -Force
    }
    Save-Registry -Entries $entries
    return $saved
}

function Save-SandboxLabIteration {
    param(
        [Parameter(Mandatory = $true)][object]$Entry,
        [Parameter(Mandatory = $true)][string]$Commit
    )

    $entries = @(Get-Registry)
    $saved = $entries | Where-Object { $_.slug -eq $Entry.slug } | Select-Object -First 1
    if (-not $saved) { throw "Sandbox '$($Entry.slug)' disappeared from the registry." }
    $saved | Add-Member -NotePropertyName lastLabIterationCommit -NotePropertyValue $Commit -Force
    $saved | Add-Member -NotePropertyName lastLabIterationUtc -NotePropertyValue `
        (Get-Date).ToUniversalTime().ToString("o") -Force
    Save-Registry -Entries $entries
}

function Write-SandboxLabVersion {
    param(
        [Parameter(Mandatory = $true)][object]$Entry,
        [Parameter(Mandatory = $true)][string]$State,
        [Parameter(Mandatory = $true)][string]$Summary
    )

    if (-not $Entry.labId) { return }
    if ([string]::IsNullOrWhiteSpace($Summary)) {
        throw "A concrete Lab iteration summary is required before recording sandbox '$($Entry.slug)'."
    }
    $status = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("status", "--porcelain")
    if ($status) {
        throw "Sandbox '$($Entry.slug)' has uncommitted changes. Commit the coherent Lab iteration before recording it."
    }
    $commit = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("rev-parse", "HEAD")
    $previousCommit = if ($Entry.lastLabIterationCommit) {
        $Entry.lastLabIterationCommit
    } else {
        $Entry.labBaselineCommit
    }
    if ($State -eq "implemented-review") {
        if (-not $previousCommit) {
            throw "Sandbox '$($Entry.slug)' has no Lab baseline. Link it explicitly with -LabId before recording an iteration."
        }
        if ($previousCommit -eq $commit) {
            throw "Sandbox '$($Entry.slug)' has no new committed change since it was linked or its last recorded Lab iteration."
        }
        & git -C $Entry.worktree merge-base --is-ancestor $previousCommit $commit
        if ($LASTEXITCODE -ne 0) {
            throw "Sandbox '$($Entry.slug)' HEAD is not descended from its Lab baseline or last recorded iteration."
        }
    }
    $evidence = "$($Summary.Trim())`nSandbox: $($Entry.slug); commit: $($commit.Substring(0, 12))"
    & "$PSScriptRoot\record-lab-implementation.ps1" -LabId $Entry.labId -State $State -Evidence $evidence
    if ($State -eq "implemented-review") {
        Save-SandboxLabIteration -Entry $Entry -Commit $commit
        $Entry | Add-Member -NotePropertyName lastLabIterationCommit -NotePropertyValue $commit -Force
    }
    Write-Host "[lab]     $($Entry.labId) -> $State" -ForegroundColor Green
}

function Assert-SandboxLabReadyForPromotion {
    param(
        [Parameter(Mandatory = $true)][object]$Entry,
        [string]$Base = "",
        [switch]$AllowContainedIteration
    )

    if (-not $Entry.labId) { return }
    if (-not $Entry.lastLabIterationCommit) {
        throw "Linked sandbox '$($Entry.slug)' has no recorded healthy Lab iteration. Serve it with -IterationSummary before promotion."
    }
    $commit = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("rev-parse", "HEAD")
    if ($Entry.lastLabIterationCommit -ne $commit) {
        if ($AllowContainedIteration -and $Base) {
            & git -C $Entry.worktree merge-base --is-ancestor `
                $Entry.lastLabIterationCommit "origin/$Base"
            if ($LASTEXITCODE -eq 0) { return }
        }
        throw "Linked sandbox '$($Entry.slug)' HEAD changed after its last recorded Lab iteration. Serve and record the current commit before promotion."
    }
}

function Get-SandboxPromotionLabel {
    param([Parameter(Mandatory = $true)][object]$Entry)

    if ($Entry.promotedUtc) {
        $pr = if ($Entry.promotionPrNumber) { " via PR #$($Entry.promotionPrNumber)" } else { "" }
        $cleanup = if ($Entry.cleanupIssues) { " (cleanup incomplete)" } else { "" }
        return "promoted$pr$cleanup"
    }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { return "unknown (gh unavailable)" }
    $base = if ($Entry.promotedBase) { [string]$Entry.promotedBase } else { "master" }
    $mergedPr = (& gh pr list --repo (Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
            "config", "--get", "remote.origin.url"
        )) --head $Entry.branch --base $base --state merged --limit 1 --json number --jq ".[0].number" |
        Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { return "unknown (GitHub query failed)" }
    if ($mergedPr) { return "promoted via PR #$mergedPr (legacy)" }
    return "not promoted"
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
    $labsUrl = "http://localhost:$($Entry.labsPort)/catalog.html"

    if (Test-SandboxEndpoint -Url $apiHealth) {
        Write-Host "[serve]   already listening on :$($Entry.apiPort)" -ForegroundColor DarkGray
    } else {
        $logDir = Join-Path $primaryRoot "logs\sandbox"
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $log = Join-Path $logDir "$($Entry.slug).log"
        # The runner already redirects both streams here, so it must not also hold
        # the shared -Run transcript open for the hours it serves.
        $env:TRIPPLANNER_RUN_LOG = "0"
        try {
            Start-Process -FilePath "pwsh" -WindowStyle Hidden `
                -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
                -ArgumentList @(
                    "-NoProfile", "-File", (Join-Path $PSScriptRoot "sandbox.ps1"), "-Run", $Entry.slug
                ) | Out-Null
        } finally {
            Remove-Item Env:\TRIPPLANNER_RUN_LOG -ErrorAction SilentlyContinue
        }
        Write-Host "[serve]   detached runner started; log: $log"
    }

    $apiReady = Wait-SandboxEndpoint -Url $apiHealth
    # A fresh sandbox installs frontend dependencies before Vite binds, so the SPA
    # needs a far longer budget than the API on the first serve.
    $frontendReady = Wait-SandboxEndpoint -Url $frontendUrl -TimeoutSeconds 300
    $labsReady = Wait-SandboxEndpoint -Url $labsUrl

    $apiMark = if ($apiReady) { "ok" } else { "NOT READY" }
    $frontendMark = if ($frontendReady) { "ok" } else { "NOT READY" }
    $labsMark = if ($labsReady) { "ok" } else { "NOT READY" }
    Write-Host "[api]     http://localhost:$($Entry.apiPort)  ($apiMark)" `
        -ForegroundColor $(if ($apiReady) { "Green" } else { "Yellow" })
    Write-Host "[spa]     http://localhost:$($Entry.frontendPort)  ($frontendMark)" `
        -ForegroundColor $(if ($frontendReady) { "Green" } else { "Yellow" })
    Write-Host "[labs]    $labsUrl  ($labsMark)" `
        -ForegroundColor $(if ($labsReady) { "Green" } else { "Yellow" })
    Write-Host "[stop]    .\scripts\dev\sandbox.ps1 -Stop $($Entry.slug)"

    if (-not ($apiReady -and $frontendReady -and $labsReady)) {
        Write-Warning "Sandbox endpoints did not come up. Check the log above, or run -Run $($Entry.slug) in a terminal to watch it start."
    }
    return ($apiReady -and $frontendReady -and $labsReady)
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

function Sync-LanesThroughMaster {
    # A sandbox is only "latest" if master already holds what the worker lanes
    # committed; branching from origin/master alone leaves it behind whatever has
    # not been integrated yet. The env guard breaks the cycle when the reverse
    # direction runs — all-worktrees-sync updates sandboxes at its end.
    param([string]$Reason)

    if ($NoSync) {
        Write-Host "[sync]    skipped (-NoSync); master may be behind the worker lanes." -ForegroundColor Yellow
        return
    }
    if ($env:TRIPPLANNER_SANDBOX_NO_SYNC -eq "1") { return }

    Write-Host "[sync]    integrating every committed lane through master ($Reason)" -ForegroundColor Cyan
    $env:TRIPPLANNER_SANDBOX_NO_SYNC = "1"
    try {
        & "$PSScriptRoot\all-worktrees-sync.ps1"
    } finally {
        Remove-Item Env:\TRIPPLANNER_SANDBOX_NO_SYNC -ErrorAction SilentlyContinue
    }
}

function Remove-SandboxLeftovers {
    # npm workspaces link @tripplanner/client into frontend/node_modules, and
    # `git worktree remove` leaves that reparse point plus its parents on disk.
    # Unlink before deleting: nothing may recurse through a junction.
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    Get-ChildItem -LiteralPath $Path -Force -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint) } |
        ForEach-Object { & cmd /c rmdir "$($_.FullName)" }

    $lastError = $null
    foreach ($attempt in 1..12) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        } catch {
            $lastError = $_.Exception.Message
        }
        if (-not (Test-Path -LiteralPath $Path)) { return $true }
        if ($attempt -lt 12) { Start-Sleep -Milliseconds 250 }
    }

    $detail = if ($lastError) { " Last error: $lastError" } else { "" }
    Write-Warning "$Path still exists after 12 deletion attempts.$detail Close anything using it and retry discard."
    return $false
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

function Get-UnregisteredSandboxes {
    # A hand-made worktree or branch is invisible to every verb here, so it
    # silently loses promotion, iteration history, and slot allocation.
    $registered = @(Get-Registry)
    $knownPaths = @($registered | ForEach-Object { ([string]$_.worktree).Replace("\", "/").TrimEnd("/").ToLowerInvariant() })
    $knownBranches = @($registered | ForEach-Object { [string]$_.branch })
    $strays = @()

    $worktreeLines = @(Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("worktree", "list", "--porcelain"))
    foreach ($line in $worktreeLines) {
        if ($line -notmatch "^worktree (.+)$") { continue }
        $path = $Matches[1].Replace("\", "/").TrimEnd("/")
        if ((Split-Path -Leaf $path) -notlike "sbx-*") { continue }
        if ($knownPaths -contains $path.ToLowerInvariant()) { continue }
        $strays += [pscustomobject]@{ Kind = "worktree"; Name = $path }
    }

    $branches = @(Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
        "for-each-ref", "--format=%(refname:short)", "refs/heads/sandbox"
    ))
    foreach ($branch in $branches) {
        if (-not $branch -or $knownBranches -contains $branch) { continue }
        $strays += [pscustomobject]@{ Kind = "branch"; Name = $branch }
    }
    return $strays
}

function Write-UnregisteredSandboxWarning {
    param([object[]]$Strays)
    if (-not $Strays -or $Strays.Count -eq 0) { return }
    Write-Host ""
    Write-Host "Not created by this tool, so no verb here can reach them:" -ForegroundColor Yellow
    foreach ($stray in $Strays) {
        Write-Host ("    {0,-8}  {1}" -f $stray.Kind, $stray.Name) -ForegroundColor Yellow
    }
    Write-Host "    They hold no slot, so their ports may collide with the dev stack or a real sandbox." -ForegroundColor DarkGray
    Write-Host ("    Move the work onto a proper sandbox: {0} <name> `"<purpose>`"" -f (Get-SandboxLauncherPath -Name "New-Sandbox")) -ForegroundColor DarkGray
    if ($Strays | Where-Object { $_.Kind -eq "worktree" }) {
        Write-Host "    Then drop a stray worktree with: git worktree remove <path>" -ForegroundColor DarkGray
    }
    if ($Strays | Where-Object { $_.Kind -eq "branch" }) {
        Write-Host "    Then drop a stray branch with: git branch -D <branch>" -ForegroundColor DarkGray
    }
}

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
    "rev-parse", "--path-format=absolute", "--git-common-dir"
)
$primaryRoot = Split-Path -Parent $commonGitDir
$worktreesRoot = "$primaryRoot.worktrees"
$registryPath = Join-Path $worktreesRoot "sandboxes.json"

# One transcript per sandbox and verb. The reference is resolved first so that
# -Run 2 and -Run 2-lab16-chatdock write to the same log instead of two.
$runVerb = $PSCmdlet.ParameterSetName.ToLowerInvariant()
$reference = @($New, $Run, $Serve, $Stop, $Promote, $Update, $Discard) |
    Where-Object { $_ } | Select-Object -First 1
$runLogSlug = $reference
if ($reference -and $runVerb -ne "new") {
    try { $runLogSlug = (Resolve-SandboxEntry -Reference $reference).slug } catch { }
}
$runLogName = if ($runLogSlug) {
    "sandbox-$($runLogSlug -replace '[^A-Za-z0-9._-]', '-')-$runVerb"
} else {
    "sandbox-$runVerb"
}
Start-RunLog -Name $runLogName | Out-Null

if ($PSCmdlet.ParameterSetName -eq "List") {
    $entries = @(Get-Registry)
    $strays = @(Get-UnregisteredSandboxes)
    if ($entries.Count -eq 0) {
        $launcher = Get-SandboxLauncherPath -Name "New-Sandbox"
        Write-Host "No sandboxes. Create one with: $launcher <name> `"<purpose>`""
        Write-UnregisteredSandboxWarning -Strays $strays
        return
    }
    foreach ($item in ($entries | Sort-Object { [int]$_.slot })) {
        $number = Get-SandboxNumber -Entry $item
        $serving = Test-SandboxEndpoint -Url "http://localhost:$($item.apiPort)/health"
        $state = if ($serving) { "serving" } else { "stopped" }
        $age = ""
        if ($item.createdUtc) {
            $span = (Get-Date).ToUniversalTime() - [datetime]::Parse($item.createdUtc).ToUniversalTime()
            $age = if ($span.TotalDays -ge 1) { "{0:N0}d old" -f $span.TotalDays } else { "{0:N0}h old" -f $span.TotalHours }
        }
        $purpose = if ([string]::IsNullOrWhiteSpace($item.purpose)) { "(no purpose recorded)" } else { $item.purpose }
        Write-Host ""
        Write-Host ("#{0}  {1}" -f $number, $item.slug) -ForegroundColor Cyan -NoNewline
        Write-Host ("   {0}  {1}" -f $state, $age) -ForegroundColor $(if ($serving) { "Green" } else { "DarkGray" })
        Write-Host ("    purpose   {0}" -f $purpose)
        if ($item.labId) { Write-Host ("    lab       {0}" -f $item.labId) }
        Write-Host ("    promotion {0}" -f (Get-SandboxPromotionLabel -Entry $item))
        Write-Host ("    app       http://localhost:{0}" -f $item.frontendPort) `
            -ForegroundColor $(if ($serving) { "Green" } else { "Gray" })
        Write-Host ("    api       http://localhost:{0}/health" -f $item.apiPort)
        Write-Host ("    labs      http://localhost:{0}/catalog.html" -f $item.labsPort)
        Write-Host ("    branch    {0}" -f $item.branch)
        Write-Host ("    worktree  {0}" -f $item.worktree)
        Write-Host ("    database  {0}" -f $item.database)
    }
    Write-UnregisteredSandboxWarning -Strays $strays
    Write-Host ""
    Write-Host "Any verb takes the number, the full name, or the short name:" -ForegroundColor DarkGray
    Write-Host "  $(Get-SandboxLauncherPath -Name 'Serve-Sandbox') <n>     $(Get-SandboxLauncherPath -Name 'Stop-Sandbox') <n>" -ForegroundColor DarkGray
    Write-Host "  $(Get-SandboxLauncherPath -Name 'Update-Sandbox') <n>    $(Get-SandboxLauncherPath -Name 'Promote-Sandbox') <n>" -ForegroundColor DarkGray
    return
}

if ($PSCmdlet.ParameterSetName -eq "New") {
    # A caller who types the number back gets the number they are actually given.
    $shortName = (Get-ShortName -Name $New).ToLowerInvariant()
    Assert-ShortName -Name $shortName
    $existing = @(Get-Registry)
    $clash = @($existing | Where-Object { (Get-ShortName -Name $_.slug) -eq $shortName })
    if ($clash.Count -gt 0) {
        throw "Sandbox '$($clash[0].slug)' already covers '$shortName'. Use -List to see it."
    }
    $slot = Get-FreeSlot -Entries $existing
    $number = $slot + 1
    $slug = "$number-$shortName"
    $branchName = "sandbox/$slug"
    $worktreePath = Join-Path $worktreesRoot "sbx-$slug"
    $database = "tripplanner-sbx-$slug"

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
    $apiPort = $ApiBase + ($slot * $Step)
    $frontendPort = $FrontendBase + ($slot * $Step)
    $labsPort = $LabsBase + ($slot * $Step)

    if (-not $PSCmdlet.ShouldProcess($worktreePath, "Create $branchName from origin/$BaseBranch")) {
        return
    }

    Sync-LanesThroughMaster -Reason "new sandbox '$slug'"
    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("fetch", "origin", $BaseBranch)
    New-Item -ItemType Directory -Path $worktreesRoot -Force | Out-Null
    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
        "worktree", "add", "-b", $branchName, $worktreePath, "origin/$BaseBranch"
    )
    $createdCommit = Invoke-Git -WorkingDirectory $worktreePath -Arguments @("rev-parse", "HEAD")

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
        purpose      = $Purpose.Trim()
        labId        = $LabId.Trim()
        branch       = $branchName
        worktree     = $worktreePath
        apiPort      = $apiPort
        frontendPort = $frontendPort
        labsPort     = $labsPort
        database     = $database
        createdUtc   = (Get-Date).ToUniversalTime().ToString("o")
        labBaselineCommit = if ($LabId.Trim()) { $createdCommit } else { "" }
    }
    Save-Registry -Entries (@($existing) + $entry)

    Write-Host "[created] #$number $slug on $branchName"
    if ($entry.purpose) { Write-Host "[purpose] $($entry.purpose)" }
    if ($entry.labId) {
        Write-Host "[lab]     $($entry.labId)"
        Write-Host "[chat]    Resolve ambiguous handoff details in this sandbox worker chat before editing."
    }
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
        Write-Host "[run]     $(Get-SandboxLauncherPath -Name 'Serve-Sandbox') $number"
    } else {
        if (-not (Start-SandboxStack -Entry $entry)) {
            throw "Sandbox '$slug' was created, but one or more endpoints did not become ready."
        }
    }
    return
}

$entry = Resolve-SandboxEntry -Reference $reference
$LabId = $LabId.Trim()
if ($LabId) {
    if ($WhatIfPreference) {
        $entry | Add-Member -NotePropertyName labId -NotePropertyValue $LabId -Force
    } else {
        $recordCurrentCommit = $PSCmdlet.ParameterSetName -eq "Serve" -and $IterationSummary.Trim()
        $entry = Save-SandboxLabId -Entry $entry -LinkedLabId $LabId `
            -RecordCurrentCommit:$recordCurrentCommit
    }
}
$slug = $entry.slug
$shortName = Get-ShortName -Name $slug

if ($PSCmdlet.ParameterSetName -eq "Run") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree). Recreate it with -New $shortName."
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
        throw "Sandbox worktree is missing: $($entry.worktree). Recreate it with -New $shortName."
    }
    $ready = Start-SandboxStack -Entry $entry
    if (-not $ready) { exit 1 }
    if ($IterationSummary.Trim()) {
        if (-not $entry.labId) {
            throw "Link sandbox '$slug' with -LabId before recording an iteration summary."
        }
        Write-SandboxLabVersion -Entry $entry -State "implemented-review" -Summary $IterationSummary
    }
    return
}

if ($PSCmdlet.ParameterSetName -eq "Stop") {
    Stop-SandboxStack -Entry $entry
    Write-Host "[stopped] sandbox '$slug'"
    return
}

if ($PSCmdlet.ParameterSetName -eq "Update") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree). Recreate it with -New $shortName."
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
        Sync-LanesThroughMaster -Reason "update sandbox '$slug'"
        Invoke-Git -WorkingDirectory $wd -Arguments @("fetch", "origin") | Out-Null
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
            $sandboxRemoteRef = "origin/$($entry.branch)"
            & git -C $wd rev-parse --verify --quiet $sandboxRemoteRef | Out-Null
            if ($LASTEXITCODE -eq 0) {
                & git -C $wd merge --no-edit $sandboxRemoteRef
                if ($LASTEXITCODE -ne 0) {
                    & git -C $wd rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
                    if ($LASTEXITCODE -ne 0) {
                        throw "Could not merge $sandboxRemoteRef into $label."
                    }
                    Complete-MergeConflict -WorkingDirectory $wd -Label $label -Kind "lane" `
                        -Branch $entry.branch -StashCommit $stashCommit
                }
            } elseif ($LASTEXITCODE -ne 1) {
                throw "Could not inspect $sandboxRemoteRef."
            }

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

        Invoke-Git -WorkingDirectory $wd -Arguments @(
            "push", "-u", "origin", "HEAD:refs/heads/$($entry.branch)"
        ) | Out-Null
        $head = Invoke-Git -WorkingDirectory $wd -Arguments @("rev-parse", "--short", "HEAD")
        Write-Host "[updated] $label and origin/$($entry.branch) are current with $remoteRef at $head." -ForegroundColor Green
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
    $action = "Sync, validate, merge into $BaseBranch, verify, and discard the sandbox"
    if (-not $PSCmdlet.ShouldProcess($entry.branch, $action)) { return }

    Write-Host "== 1/6 sync with origin/$BaseBranch ==" -ForegroundColor Green
    & $PSCommandPath -Update $slug -BaseBranch $BaseBranch -NoSync:$NoSync -Confirm:$false
    $conflicts = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @(
        "diff", "--name-only", "--diff-filter=U"
    )
    if ($conflicts) {
        throw "Resolve and commit these conflicts, then re-run -Promote ${slug}:`n$($conflicts -join "`n")"
    }
    Assert-SandboxLabReadyForPromotion -Entry $entry
    $unmerged = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @(
        "log", "--oneline", "origin/$BaseBranch..HEAD"
    )
    if (-not $unmerged) {
        Assert-SandboxLabReadyForPromotion -Entry $entry -Base $BaseBranch -AllowContainedIteration
        Write-Host "== 2/3 push $($entry.branch) ==" -ForegroundColor Green
        Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("push", "-u", "origin", $entry.branch)
        Write-Host "== 3/3 verify ==" -ForegroundColor Green
        $outstanding = Get-SandboxOutstandingWork -Entry $entry -Base $BaseBranch
        if ($outstanding) {
            throw "Sandbox '$slug' is already in origin/$BaseBranch but is not safe to discard:`n$($outstanding -join "`n")"
        }
        Assert-SandboxLabReadyForPromotion -Entry $entry -Base $BaseBranch -AllowContainedIteration
        Write-SandboxLabVersion -Entry $entry -State "completed" `
            -Summary "Promoted to $BaseBranch after verification."
        Save-SandboxPromotion -Entry $entry -Base $BaseBranch
        Write-Host "[verified] origin/$BaseBranch already contains every commit and the worktree is clean." -ForegroundColor Green
        Push-Location $scriptRepoRoot
        try {
            & $PSCommandPath -Discard $slug -BaseBranch $BaseBranch -Confirm:$false
        } finally {
            Pop-Location
        }
        return
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
    Assert-SandboxLabReadyForPromotion -Entry $entry
    Write-SandboxLabVersion -Entry $entry -State "completed" `
        -Summary "Promoted to $BaseBranch via PR #$prNumber after validation and verification."
    Save-SandboxPromotion -Entry $entry -Base $BaseBranch -PrNumber $prNumber
    Write-Host "[verified] origin/$BaseBranch contains every commit and the worktree is clean."
    Push-Location $scriptRepoRoot
    try {
        & $PSCommandPath -Discard $slug -BaseBranch $BaseBranch -Confirm:$false
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
        $outstanding = Get-SandboxOutstandingWork -Entry $entry -Base $BaseBranch
        if ($outstanding -and -not $Force) {
            throw "Sandbox '$slug' still holds work that origin/$BaseBranch does not have. Promote it first, or pass -Force to discard anyway:`n$($outstanding -join "`n")"
        }
        if ($outstanding) {
            Write-Warning "Discarding sandbox '$slug' with outstanding work (-Force):`n$($outstanding -join "`n")"
        }
    }

    $remoteAction = if ($DeleteRemoteBranch) { ", local and remote branches," } else { ", local branch," }
    if (-not $PSCmdlet.ShouldProcess($slug, "Remove sandbox worktree$remoteAction and emulator database")) {
        return
    }

    $cleanupIssues = @()
    try {
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
        if (-not (Remove-SandboxLeftovers -Path $entry.worktree)) {
            $cleanupIssues += "worktree directory still exists: $($entry.worktree)"
        }
    } else {
        Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("worktree", "prune")
    }

    Remove-PendingMergesFor -WorkingDirectory $entry.worktree

    $localBranch = & git -C $scriptRepoRoot branch --list $entry.branch
    if ($LASTEXITCODE -ne 0) {
        $cleanupIssues += "could not query local branch $($entry.branch)"
    } elseif ($localBranch) {
        & git -C $scriptRepoRoot branch -D $entry.branch
        if ($LASTEXITCODE -ne 0) {
            $cleanupIssues += "could not delete local branch $($entry.branch)"
        }
    }

    $python = Get-VenvPython
    $seedScript = Join-Path $scriptRepoRoot "scripts\dev\sandbox_seed.py"
    if (Test-Path $seedScript -PathType Leaf) {
        & $python $seedScript drop --database $entry.database
        if ($LASTEXITCODE -ne 0) {
            $cleanupIssues += "could not drop database $($entry.database)"
        }
    }

    if ($DeleteRemoteBranch) {
        $remoteBranch = Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
            "ls-remote", "--heads", "origin", $entry.branch
        )
        if ($remoteBranch) {
            & git -C $scriptRepoRoot push origin --delete $entry.branch
            if ($LASTEXITCODE -ne 0) {
                $cleanupIssues += "could not delete remote branch $($entry.branch)"
            }
        }
    }
    } catch {
        $cleanupIssues += $_.Exception.Message
    }

    if ($cleanupIssues) {
        $entries = @(Get-Registry)
        $saved = $entries | Where-Object { $_.slug -eq $slug } | Select-Object -First 1
        if ($saved) {
            $saved | Add-Member -NotePropertyName cleanupAttemptUtc -NotePropertyValue `
                (Get-Date).ToUniversalTime().ToString("o") -Force
            $saved | Add-Member -NotePropertyName cleanupIssues -NotePropertyValue $cleanupIssues -Force
            Save-Registry -Entries $entries
        }
        throw "Sandbox '$slug' was promoted but cleanup is incomplete; it remains listed for retry:`n  $($cleanupIssues -join "`n  ")"
    }

    $remaining = Get-Registry | Where-Object { $_.slug -ne $slug }
    Save-Registry -Entries @($remaining)
    Write-Host "[discarded] sandbox '$slug'"
    return
}
