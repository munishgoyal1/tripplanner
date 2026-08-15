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
    .\scripts\dev\sandbox.ps1 -RunAll
    .\scripts\dev\sandbox.ps1 -Serve lab16-chatdock -IterationSummary "Adjusted the dock and passed focused UI checks."
    .\scripts\dev\sandbox.ps1 -Stop 2
    .\scripts\dev\sandbox.ps1 -Update 2
    .\scripts\dev\sandbox.ps1 -Rename 2 chatdock-v2
    .\scripts\dev\sandbox.ps1 -Merge 2
    .\scripts\dev\sandbox.ps1 -Promote 2
    .\scripts\dev\sandbox.ps1 -Discard 2
    .\scripts\dev\sandbox.ps1 -List

.NOTES
  Every verb except -New takes the number, the full name, or the short name
  without its number prefix.

  -Run holds the terminal; -Serve starts the same stack detached and waits for
  the endpoints to answer, so a sandbox is verifiable the moment it is created.
  -New serves automatically unless you pass -NoServe.

    Link a UX Lab sandbox with -LabId. -Promote records the promoted commit as an
    implemented-review iteration by itself, after starting the stack and confirming
    the endpoints answer, so an iteration loop ends at -Promote with no separate step.
    Pass -IterationSummary to either -Serve or -Promote to choose that wording instead
    of the commit subjects. Verified promotion appends Completed before sandbox cleanup.

    -New and -Update fetch the latest origin/master before branching or merging, so
    each sandbox starts from the current canonical baseline. Pass -NoSync to skip
    that refresh. Sandbox work reaches master only through -Merge or -Promote.

    -Promote is end to end: sync, validate, push, open the PR, merge into the base
    branch, verify that the base branch really contains every commit and that the
    worktree is clean, then discard the sandbox. -Ship is an alias of the same verb.

    -Merge runs the same gates but keeps the sandbox: after the base branch is
    verified to contain the merged commit, the sandbox is resynchronized onto it
    and stays registered and active. Nothing is discarded, no promotion is
    recorded, and UX Lab records are left untouched. Use it to land finished work
    and carry on in the same lane; use -Promote when the lane is finished.
    -Merge fetches the latest base before syncing and again after the pull request
    lands, and runs the sandbox conflict resolver automatically on both syncs, so
    a conflict git can already settle does not stall the merge.

    Promote-Sandbox (the user launcher) defaults to -Merge's keep-alive behavior;
    pass -Discard to it to get -Promote's discard-after-landing behavior instead.
    Call this script's own -Merge / -Promote directly to bypass that default.

    -Rename changes only the name part of a sandbox: its branch, worktree folder,
    and database name follow, while the number keeps its ports. A new name may
    repeat the existing number but cannot change it. The emulator data moves to
    the new database name, so the sandbox keeps the trips it already had. Pass
    -Purpose to update the recorded purpose in the same step; otherwise a reused
    slot keeps showing its prior occupant's purpose in -List.

  Only a sandbox that -Promote has verified is safe to discard; -Discard refuses
  to drop a worktree that still holds uncommitted, unpushed or unmerged work
    unless you pass -Force. Discard removes the local and remote sandbox branches;
    pass -DeleteRemoteBranch:$false only when the remote branch must be retained.

  Sandboxes are always created fresh and discarded after promotion: a fresh one
  costs about 29 seconds, which is not worth a second lifecycle to manage.

    A semantic merge conflict leaves the sandbox merge and any safety stash intact.
    Resolve the files, then run Resolve-SandboxConflicts for that sandbox before retrying.
#>

[CmdletBinding(SupportsShouldProcess = $true, DefaultParameterSetName = "List")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "New")]
    [string]$New,

    [Parameter(Mandatory = $true, ParameterSetName = "Run")]
    [string]$Run,

    [Parameter(Mandatory = $true, ParameterSetName = "RunAll")]
    [switch]$RunAll,

    [Parameter(Mandatory = $true, ParameterSetName = "Serve")]
    [string]$Serve,

    [Parameter(Mandatory = $true, ParameterSetName = "Stop")]
    [string]$Stop,

    [Parameter(Mandatory = $true, ParameterSetName = "Promote")]
    [Alias("Ship")]
    [string]$Promote,

    [Parameter(Mandatory = $true, ParameterSetName = "Merge")]
    [string]$Merge,

    [Parameter(Mandatory = $true, ParameterSetName = "Update")]
    [string]$Update,

    [Parameter(Mandatory = $true, ParameterSetName = "Rename")]
    [string]$Rename,

    [Parameter(Mandatory = $true, ParameterSetName = "Rename", Position = 0)]
    [string]$NewName,

    [Parameter(Mandatory = $true, ParameterSetName = "Discard")]
    [string]$Discard,

    [Parameter(ParameterSetName = "List")]
    [switch]$List,

    [Parameter(ParameterSetName = "New")]
    [Parameter(ParameterSetName = "Update")]
    [Parameter(ParameterSetName = "Promote")]
    [Parameter(ParameterSetName = "Merge")]
    [Parameter(ParameterSetName = "Discard")]
    [string]$BaseBranch = "master",

    [Parameter(ParameterSetName = "New", Position = 0)]
    [Parameter(ParameterSetName = "Rename")]
    [string]$Purpose = "",

    [Parameter(ParameterSetName = "New")]
    [Parameter(ParameterSetName = "Run")]
    [Parameter(ParameterSetName = "Serve")]
    [Parameter(ParameterSetName = "Promote")]
    [string]$LabId = "",

    [Parameter(ParameterSetName = "Serve")]
    [Parameter(ParameterSetName = "Promote")]
    [string]$IterationSummary = "",

    [Parameter(ParameterSetName = "New")]
    [switch]$NoOpen,

    [Parameter(ParameterSetName = "New")]
    [switch]$NoServe,

    [Parameter(ParameterSetName = "New")]
    [Parameter(ParameterSetName = "Update")]
    [Parameter(ParameterSetName = "Promote")]
    [Parameter(ParameterSetName = "Merge")]
    [switch]$NoSync,

    [Parameter(ParameterSetName = "Promote")]
    [Parameter(ParameterSetName = "Merge")]
    [switch]$SkipValidation,

    [Parameter(ParameterSetName = "Discard")]
    [switch]$Force,

    [Parameter(ParameterSetName = "Discard")]
    [switch]$DeleteRemoteBranch = $true
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
. "$PSScriptRoot/lib/node-tools.ps1"
. "$PSScriptRoot/lib/vscode-cli.ps1"
. "$PSScriptRoot/lib/sandbox-registry.ps1"
. "$PSScriptRoot/lib/gh-cli.ps1"

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

function Test-SandboxWorktree {
    # A half-finished discard can leave the folder behind with its .git gone, so
    # existing on disk is not the same as still being a worktree git can drive.
    param([Parameter(Mandatory = $true)][object]$Entry)
    if (-not $Entry.worktree -or -not (Test-Path $Entry.worktree)) { return $false }
    & git -C $Entry.worktree rev-parse --git-dir 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Get-SandboxLauncherPath {
    param([Parameter(Mandatory = $true)][string]$Name)
    if ($IsMacOS) {
        return "./scripts/mac/user/sandbox/$Name.command"
    }
    return ".\scripts\user\sandbox\$Name.cmd"
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
    return Select-SandboxEntry -Entries $entries -Reference $Reference
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
    Use-CompatibleNode
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

function Commit-SandboxDebugStoreArtifacts {
    param([Parameter(Mandatory = $true)][object]$Entry)

    $status = @(Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @(
        "status", "--porcelain=v1", "--untracked-files=all", "--", "debug-store"
    ))
    $jsonPaths = @($status | ForEach-Object {
        if ($_.Length -lt 4) { return }
        $path = $_.Substring(3).Trim()
        if ($path -match '\.json$') { $path }
    } | Where-Object { $_ })
    if ($jsonPaths.Count -eq 0) { return $false }

    Invoke-Git -WorkingDirectory $Entry.worktree -Arguments (@("add", "--") + $jsonPaths) | Out-Null
    Invoke-Git -WorkingDirectory $Entry.worktree -Arguments (
        @("commit", "-m", "Capture debug-store trip archives", "--") + $jsonPaths
    ) | Out-Null
    Write-Host "[debug]   committed $($jsonPaths.Count) generated debug-store JSON archive(s)" -ForegroundColor DarkGray
    return $true
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
    # The recorder defaults its store to the lane that launched this script, which wrote
    # sandbox records into whichever worktree happened to invoke it. An iteration belongs
    # to the sandbox branch so it travels with the PR; a completed record outlives the
    # sandbox, so it belongs to the primary checkout.
    $storeRoot = if ($State -eq "implemented-review") { $Entry.worktree } else { $primaryRoot }
    $store = "docs/ux-experiments/LAB_SELECTIONS.json"
    & "$PSScriptRoot\record-lab-implementation.ps1" -LabId $Entry.labId -State $State `
        -Evidence $evidence -StorePath (Join-Path $storeRoot $store)
    # The recorder only writes the store. Leaving that write uncommitted made the next
    # promote fail its own clean-worktree gate, so it is committed with the record.
    if ($storeRoot -eq $Entry.worktree) {
        $storeChanged = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @(
            "status", "--porcelain", "--", $store
        )
        if ($storeChanged) {
            Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("add", "--", $store) | Out-Null
            Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @(
                "commit", "-m", "Record $($Entry.labId) lab $State for $($Entry.slug)", "--", $store
            ) | Out-Null
            Write-Host "[lab]     committed the lab record" -ForegroundColor DarkGray
        }
    }
    if ($State -eq "implemented-review") {
        Save-SandboxLabIteration -Entry $Entry -Commit $commit
        $Entry | Add-Member -NotePropertyName lastLabIterationCommit -NotePropertyValue $commit -Force
    }
    Write-Host "[lab]     $($Entry.labId) -> $State" -ForegroundColor Green
}

function Register-SandboxLabIteration {
    # Promotion needs proof that the promoted commit ran healthily. Recording used to
    # happen only inside a separate -Serve call, so the ordinary run, test, commit loop
    # always arrived at -Promote with nothing recorded. Promotion now records it here,
    # against the same health check -Serve uses, instead of failing on a missing step.
    param(
        [Parameter(Mandatory = $true)][object]$Entry,
        [Parameter(Mandatory = $true)][string]$Base,
        [string]$Summary = ""
    )

    if (-not $Entry.labId) { return }
    try {
        Assert-SandboxLabReadyForPromotion -Entry $Entry -Base $Base -AllowContainedIteration
        return
    } catch {
        Write-Host "[lab]     no recorded iteration for this commit; recording it now" -ForegroundColor Cyan
    }

    $changes = Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("status", "--porcelain")
    if ($changes) {
        throw "Sandbox '$($Entry.slug)' has uncommitted changes. Commit them before promoting."
    }
    if (-not (Start-SandboxStack -Entry $Entry)) {
        throw "Sandbox '$($Entry.slug)' endpoints are not healthy, so this commit cannot be recorded as a verified Lab iteration. Fix the stack and re-run promotion."
    }

    $text = $Summary.Trim()
    if (-not $text) {
        $previous = if ($Entry.lastLabIterationCommit) {
            $Entry.lastLabIterationCommit
        } else {
            $Entry.labBaselineCommit
        }
        $subjects = @()
        if ($previous) {
            $subjects = @(Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @(
                "log", "--first-parent", "--format=%s", "$previous..HEAD"
            ) | Where-Object { $_ -and $_ -notmatch "^Merge " } | Select-Object -First 3)
        }
        $text = if ($subjects) {
            $subjects -join "; "
        } else {
            "Sandbox iteration verified healthy before promotion."
        }
    }
    Write-SandboxLabVersion -Entry $Entry -State "implemented-review" -Summary $text
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
            # -Promote synchronizes the sandbox before it checks eligibility. That
            # may add a metadata-only Lab record commit or a local merge whose
            # other parent is origin/master. Neither is new Lab work. Product
            # commits remain rejected until another served iteration records them.
            & git -C $Entry.worktree merge-base --is-ancestor `
                $Entry.lastLabIterationCommit $commit
            if ($LASTEXITCODE -eq 0) {
                $syncOnly = $true
                $revisions = @(
                    (& git -C $Entry.worktree rev-list --first-parent `
                        "$($Entry.lastLabIterationCommit)..$commit").Trim().Split(
                        [Environment]::NewLine,
                        [System.StringSplitOptions]::RemoveEmptyEntries
                    )
                )
                foreach ($revision in $revisions) {
                    $parents = @(
                        (& git -C $Entry.worktree show -s --format=%P $revision).Trim().Split(
                            " ",
                            [System.StringSplitOptions]::RemoveEmptyEntries
                        )
                    )
                    $changedPaths = @(
                        & git -C $Entry.worktree diff-tree --no-commit-id --name-only -r $revision
                    )
                    $labRecordOnly = $changedPaths.Count -gt 0 -and @(
                        $changedPaths | Where-Object {
                            $_ -ne "docs/ux-experiments/LAB_SELECTIONS.json"
                        }
                    ).Count -eq 0
                    if ($parents.Count -eq 1 -and $labRecordOnly) {
                        # Recording an implemented-review version changes the tracked
                        # Lab store after the reviewed product commit. Its follow-up
                        # metadata commit belongs to that iteration, not a new one.
                        continue
                    }
                    if ($parents.Count -lt 2) {
                        $syncOnly = $false
                        break
                    }
                    $baseMerged = $false
                    foreach ($parent in $parents | Select-Object -Skip 1) {
                        & git -C $Entry.worktree merge-base --is-ancestor $parent "origin/$Base"
                        if ($LASTEXITCODE -eq 0) {
                            $baseMerged = $true
                            break
                        }
                    }
                    if (-not $baseMerged) {
                        $syncOnly = $false
                        break
                    }
                }
                if ($syncOnly) { return }
            }
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
    $ghCli = Resolve-GhCli
    if (-not $ghCli) { return "unknown (gh unavailable)" }
    $base = if ($Entry.promotedBase) { [string]$Entry.promotedBase } else { "master" }
    $mergedPr = (& $ghCli pr list --repo (Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @(
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
    $processIds = @(Get-ProcessIdsByCommandPattern -Pattern $escaped)
    foreach ($processId in $processIds) {
        Write-Host "[stop]    worktree process ($processId)"
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    if ($processIds.Count -gt 0) { Start-Sleep -Milliseconds 500 }
}

function Get-ListeningProcessIds {
    param([Parameter(Mandatory = $true)][int]$Port)

    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        try {
            return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
                ForEach-Object { $_.OwningProcess } |
                Where-Object { $_ -gt 0 } |
                Sort-Object -Unique)
        } catch {
            return @()
        }
    }
    if (-not $IsWindows -and (Get-Command lsof -ErrorAction SilentlyContinue)) {
        return @(& lsof -nP -tiTCP:$Port -sTCP:LISTEN 2>$null |
            Where-Object { $_ -match "^\d+$" } |
            ForEach-Object { [int]$_ } |
            Sort-Object -Unique)
    }
    return @()
}

function Stop-ProcessTree {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    if ($IsWindows) {
        & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
    } else {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
    try {
        Wait-Process -Id $ProcessId -Timeout 5 -ErrorAction SilentlyContinue
    } catch {
        # The process may have exited before Wait-Process attached.
    }
}

function Get-ProcessIdsByCommandPattern {
    param([Parameter(Mandatory = $true)][string]$Pattern)

    if ($IsWindows -and (Get-Command Get-CimInstance -ErrorAction SilentlyContinue)) {
        return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -match $Pattern } |
            ForEach-Object { [int]$_.ProcessId } |
            Sort-Object -Unique)
    }
    if (-not $IsWindows) {
        return @(& ps -axo pid=,command= |
            Where-Object { $_ -match $Pattern } |
            ForEach-Object { if ($_ -match "^\s*(\d+)") { [int]$Matches[1] } } |
            Where-Object { $_ -and $_ -ne $PID } |
            Sort-Object -Unique)
    }
    return @()
}

function ConvertTo-ComparablePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return $Path.Replace("\", "/").TrimEnd("/")
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
            $startArgs = @{
                FilePath = "pwsh"
                RedirectStandardOutput = $log
                RedirectStandardError = "$log.err"
                ArgumentList = @(
                    "-NoProfile", "-File", (Join-Path $PSScriptRoot "sandbox.ps1"), "-Run", $Entry.slug
                )
            }
            if ($IsWindows) { $startArgs.WindowStyle = "Hidden" }
            Start-Process @startArgs | Out-Null
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
        $processIds = @(Get-ListeningProcessIds -Port $port)
        foreach ($processId in $processIds) {
            Write-Host "[stop]    :$port (PID $processId)"
            Stop-ProcessTree -ProcessId $processId
        }
        $remainingIds = @(Get-ListeningProcessIds -Port $port)
        if ($remainingIds.Count -gt 0) {
            throw "Sandbox port $port is still occupied by PID $($remainingIds -join ', ') after forced cleanup."
        }
    }
    # The detached runner's command line carries the slug, not the worktree path,
    # so Stop-SandboxProcesses alone would leave it behind.
    $pattern = "sandbox\.ps1.+-Run\s+$([regex]::Escape($Entry.slug))(\s|$)"
    $launcherIds = @(Get-ProcessIdsByCommandPattern -Pattern $pattern)
    foreach ($launcherId in $launcherIds) {
        Write-Host "[stop]    runner ($launcherId)"
        Stop-ProcessTree -ProcessId $launcherId
    }
    if (Test-Path $Entry.worktree -PathType Container) {
        Stop-SandboxProcesses -Worktree $Entry.worktree
    }
}

function Sync-MasterBaseline {
    # Sandboxes are the only active isolated development lane. Fetching the
    # canonical baseline avoids hidden integration work before a sandbox starts.
    param([string]$Reason)

    if ($NoSync) {
        Write-Host "[sync]    skipped (-NoSync); origin/master may have advanced." -ForegroundColor Yellow
        return
    }

    Write-Host "[sync]    fetching origin/master ($Reason)" -ForegroundColor Cyan
    & git -C $primaryRoot fetch -q origin master
    if ($LASTEXITCODE -ne 0) {
        throw "Could not fetch origin/master."
    }
}

function Sync-PrimaryCheckout {
    param(
        [Parameter(Mandatory = $true)][string]$Base,
        [switch]$RequireExact
    )

    $changes = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("status", "--porcelain")
    if ($changes) {
        throw "Primary checkout has uncommitted changes. Commit or stash them before promotion."
    }
    Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("fetch", "-q", "origin", $Base) | Out-Null
    $localHead = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("rev-parse", "HEAD")
    $remoteHead = Invoke-Git -WorkingDirectory $primaryRoot -Arguments @("rev-parse", "origin/$Base")
    if ($RequireExact -and $localHead -ne $remoteHead) {
        throw "Primary checkout must match origin/$Base before promotion (local $localHead, remote $remoteHead)."
    }
    & git -C $primaryRoot merge --ff-only "origin/$Base"
    if ($LASTEXITCODE -ne 0) {
        throw "Primary checkout is not a clean fast-forward from origin/$Base. Reconcile it before promotion."
    }
}

function Complete-SandboxMergeConflict {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Label,
        [string]$StashCommit = ""
    )

    & git -C $WorkingDirectory rerere 2>&1 | Out-Host
    $unmerged = @(& git -C $WorkingDirectory diff --name-only --diff-filter=U)
    if ($unmerged.Count -eq 0) {
        & git -C $WorkingDirectory commit --no-edit
        if ($LASTEXITCODE -ne 0) { throw "Could not finish the recorded merge for $Label." }
        return
    }

    if ($StashCommit) {
        $stateDir = Join-Path $primaryRoot "logs/sandbox"
        New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
        [pscustomobject]@{
            worktree = $WorkingDirectory
            stashCommit = $StashCommit
        } | ConvertTo-Json | Set-Content -Path (Join-Path $stateDir "pending-conflict-$((Split-Path -Leaf $WorkingDirectory)).json")
    }
    $stashHint = if ($StashCommit) { " Its safety stash is retained until recovery completes." } else { "" }
    throw "SANDBOX_CONFLICT_PENDING: $Label has conflicts: $($unmerged -join ', '). Resolve them in $WorkingDirectory, then run Resolve-SandboxConflicts for this sandbox.$stashHint"
}

function Get-SandboxUnmergedFiles {
    param([Parameter(Mandatory = $true)][string]$WorkingDirectory)
    return @(& git -C $WorkingDirectory diff --name-only --diff-filter=U)
}

function Invoke-SandboxUpdateWithRecovery {
    # Same recovery the sync launcher performs: run the resolver when a conflict
    # is actually pending, then retry once. Retrying on anything else would
    # replay a failure that was never a conflict.
    param(
        [Parameter(Mandatory = $true)][string]$Slug,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(Mandatory = $true)][string]$Verb,
        [switch]$SkipBaseFetch
    )

    try {
        & $PSCommandPath -Update $Slug -BaseBranch $Base -NoSync:$SkipBaseFetch -Confirm:$false
        if (@(Get-SandboxUnmergedFiles -WorkingDirectory $WorkingDirectory).Count -eq 0) { return }
        $firstError = "update left conflicts pending"
    } catch {
        $firstError = $_.Exception.Message
        if (@(Get-SandboxUnmergedFiles -WorkingDirectory $WorkingDirectory).Count -eq 0) { throw }
    }

    Write-Host "[resolve] sandbox '$Slug' has conflicts; running the resolver" -ForegroundColor Yellow
    try {
        & (Join-Path $PSScriptRoot "resolve-sandbox-conflicts.ps1") -Sandbox $Slug -Confirm:$false
    } catch {
        throw "$firstError`nResolve these conflicts, then re-run $Verb ${Slug}: $($_.Exception.Message)"
    }
    $conflicts = @(Get-SandboxUnmergedFiles -WorkingDirectory $WorkingDirectory)
    if ($conflicts.Count -gt 0) {
        throw "Resolve and commit these conflicts, then re-run $Verb ${Slug}:`n$($conflicts -join "`n")"
    }

    & $PSCommandPath -Update $Slug -BaseBranch $Base -NoSync -Confirm:$false
    $conflicts = @(Get-SandboxUnmergedFiles -WorkingDirectory $WorkingDirectory)
    if ($conflicts.Count -gt 0) {
        throw "Recovered the first conflict, but resynchronizing '$Slug' conflicted again:`n$($conflicts -join "`n")"
    }
    Write-Host "[resolve] sandbox '$Slug' recovered" -ForegroundColor Green
}

function Save-SandboxConflictState {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [string]$StashCommit = ""
    )
    $stateDir = Join-Path $primaryRoot "logs/sandbox"
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    [pscustomobject]@{
        worktree = $WorkingDirectory
        stashCommit = $StashCommit
    } | ConvertTo-Json | Set-Content -Path (Join-Path $stateDir "pending-conflict-$((Split-Path -Leaf $WorkingDirectory)).json")
}

function Restore-SandboxStash {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$StashCommit
    )

    $currentStash = & git -C $WorkingDirectory rev-parse --quiet --verify refs/stash 2>$null
    if ($LASTEXITCODE -ne 0 -or $currentStash -ne $StashCommit) {
        Write-Warning "$Label safety stash is not the newest stash; leaving it untouched."
        return
    }
    & git -C $WorkingDirectory stash pop --index "stash@{0}"
    if ($LASTEXITCODE -ne 0) {
        Save-SandboxConflictState -WorkingDirectory $WorkingDirectory -StashCommit $StashCommit
        Write-Warning "$Label local changes conflict with the updated base; resolve them before continuing."
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
        ForEach-Object {
            if ($IsWindows) {
                & cmd /c rmdir "$($_.FullName)"
            } else {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            }
        }

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
$reference = @($New, $Run, $Serve, $Stop, $Promote, $Merge, $Update, $Rename, $Discard) |
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
            # ConvertFrom-Json already turns an ISO-looking createdUtc string into a
            # [datetime]; re-parsing its current-culture ToString() (e.g. "08/13/2026")
            # both mangled the age and threw outright once the day-of-month exceeded 12.
            $createdUtc = if ($item.createdUtc -is [datetime]) {
                $item.createdUtc
            } else {
                [datetime]::Parse($item.createdUtc, [System.Globalization.CultureInfo]::InvariantCulture)
            }
            $span = (Get-Date).ToUniversalTime() - $createdUtc.ToUniversalTime()
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
    Write-Host "  $(Get-SandboxLauncherPath -Name 'Merge-Sandbox') <n>     (merge to master, keep the sandbox)" -ForegroundColor DarkGray
    Write-Host "  $(Get-SandboxLauncherPath -Name 'Rename-Sandbox') <n> <new-name>" -ForegroundColor DarkGray
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
    $vsCodeCli = if ($NoOpen) { $null } else { Resolve-VsCodeCli }
    if (-not $NoOpen -and -not $vsCodeCli) {
        throw "The VS Code command 'code' was not found. Install VS Code, or pass -NoOpen."
    }
    $apiPort = $ApiBase + ($slot * $Step)
    $frontendPort = $FrontendBase + ($slot * $Step)
    $labsPort = $LabsBase + ($slot * $Step)

    if (-not $PSCmdlet.ShouldProcess($worktreePath, "Create $branchName from origin/$BaseBranch")) {
        return
    }

    Sync-MasterBaseline -Reason "new sandbox '$slug'"
    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("fetch", "-q", "origin", $BaseBranch)
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
        Write-Host "[chat]    Resolve ambiguous handoff details in this sandbox chat before editing."
    }
    Write-Host "[path]    $worktreePath"
    Write-Host "[ports]   api=$apiPort  frontend=$frontendPort  labs=$labsPort"
    Write-Host "[db]      $database (emulator)"

    if (-not $NoOpen) {
        & $vsCodeCli --new-window $worktreePath
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

if ($PSCmdlet.ParameterSetName -eq "RunAll") {
    $entries = @(Get-Registry | Sort-Object { [int]$_.slot })
    if ($entries.Count -eq 0) {
        throw "No sandboxes are registered."
    }

    $pwsh = (Get-Command pwsh -ErrorAction Stop).Source
    $runLogRoot = Join-Path $primaryRoot "logs/sandbox/run-all"
    New-Item -ItemType Directory -Path $runLogRoot -Force | Out-Null
    Write-Host "Starting $($entries.Count) sandbox(es) in the background..." -ForegroundColor Cyan

    foreach ($entry in $entries) {
        $number = Get-SandboxNumber -Entry $entry
        if (-not (Test-SandboxWorktree -Entry $entry)) {
            Write-Warning "Skipping #$number $($entry.slug): worktree is missing or invalid."
            continue
        }
        $logBase = Join-Path $runLogRoot $entry.slug
        $child = Start-Process -FilePath $pwsh -WorkingDirectory $entry.worktree -PassThru `
            -RedirectStandardOutput "$logBase.out.log" -RedirectStandardError "$logBase.err.log" `
            -ArgumentList @("-NoProfile", "-File", $PSCommandPath, "-Run", "$number")
        Write-Host ("[started] #{0} {1} (pid {2}) -> http://localhost:{3}" -f `
                $number, $entry.slug, $child.Id, $entry.frontendPort) -ForegroundColor Green
    }
    Write-Host "Each sandbox writes output to $runLogRoot" -ForegroundColor DarkGray
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
    if (-not (Test-SandboxWorktree -Entry $entry)) {
        $launcher = Get-SandboxLauncherPath -Name "Discard-Sandbox"
        throw "$($entry.worktree) exists but is no longer a git worktree, so a half-finished discard left it behind. Finish it with: $launcher $(Get-SandboxNumber -Entry $entry)"
    }
    $wd = $entry.worktree
    $label = "Sandbox '$slug'"
    $actualBranch = (Invoke-Git -WorkingDirectory $wd -Arguments @("branch", "--show-current")).Trim()
    if ($actualBranch -ne $entry.branch) {
        throw "$label must be on $($entry.branch), not $actualBranch."
    }
    $remoteRef = "origin/$BaseBranch"

    $unmerged = @(Get-SandboxUnmergedFiles -WorkingDirectory $wd)
    if ($unmerged.Count -gt 0) {
        throw "SANDBOX_CONFLICT_PENDING: $label already has unresolved files: $($unmerged -join ', '). Resolve them, then run Resolve-SandboxConflicts before retrying Sync All."
    }

    if (-not $PSCmdlet.ShouldProcess($entry.branch, "Merge $remoteRef into the sandbox")) {
        return
    }

    try {
        Sync-MasterBaseline -Reason "update sandbox '$slug'"
        Invoke-Git -WorkingDirectory $wd -Arguments @("fetch", "-q", "origin") | Out-Null
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
                    Complete-SandboxMergeConflict -WorkingDirectory $wd -Label $label -StashCommit $stashCommit
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
                Complete-SandboxMergeConflict -WorkingDirectory $wd -Label $label -StashCommit $stashCommit
            }
        } finally {
            if ($stashCommit) {
                & git -C $wd rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Warning "$label local changes remain in the safety stash until the merge conflict is resolved."
                } else {
                    Restore-SandboxStash -WorkingDirectory $wd -Label $label -StashCommit $stashCommit
                }
            }
        }

        Invoke-Git -WorkingDirectory $wd -Arguments @(
            "push", "-q", "-u", "origin", "HEAD:refs/heads/$($entry.branch)"
        ) | Out-Null
        $head = Invoke-Git -WorkingDirectory $wd -Arguments @("rev-parse", "--short", "HEAD")
        Write-Host "[updated] $label and origin/$($entry.branch) are current with $remoteRef at $head." -ForegroundColor Green
    } finally { }
    return
}

if ($PSCmdlet.ParameterSetName -eq "Rename") {
    $number = Get-SandboxNumber -Entry $entry
    # The number is the port slot, not a label, so a caller may repeat it but
    # never reassign it.
    if ($NewName -match "^(\d+)-") {
        if ([int]$matches[1] -ne $number) {
            throw "Sandbox '$slug' is #$number. Renaming cannot move it to #$($matches[1]) because the number owns its ports and database; discard and recreate instead."
        }
    }
    $newShortName = (Get-ShortName -Name $NewName).ToLowerInvariant()
    Assert-ShortName -Name $newShortName

    $newSlug = "$number-$newShortName"
    if ($newSlug -eq $entry.slug) {
        if ($Purpose) {
            $entries = @(Get-Registry)
            foreach ($item in $entries) {
                if ($item.slug -eq $entry.slug) { $item.purpose = $Purpose }
            }
            Save-Registry -Entries $entries
            Write-Host "[purpose] $($entry.slug) -> $Purpose" -ForegroundColor Green
        } else {
            Write-Host "[current] Sandbox '$($entry.slug)' already has that name." -ForegroundColor Green
        }
        return
    }
    $clash = @(Get-Registry | Where-Object {
        $_.slug -ne $entry.slug -and (Get-ShortName -Name $_.slug) -eq $newShortName
    })
    if ($clash.Count -gt 0) {
        throw "Sandbox '$($clash[0].slug)' already covers '$newShortName'."
    }

    if (-not (Test-SandboxWorktree -Entry $entry)) {
        throw "Sandbox worktree is missing or is no longer a git worktree: $($entry.worktree)."
    }
    if (Test-SandboxEndpoint -Url "http://localhost:$($entry.apiPort)/health") {
        throw "Sandbox '$slug' is serving. Stop it first: $(Get-SandboxLauncherPath -Name 'Stop-Sandbox') $number."
    }
    $unmerged = @(Get-SandboxUnmergedFiles -WorkingDirectory $entry.worktree)
    if ($unmerged.Count -gt 0) {
        throw "Sandbox '$slug' has unresolved conflicts; finish the merge before renaming:`n$($unmerged -join "`n")"
    }

    $newBranch = "sandbox/$newSlug"
    $newWorktree = Join-Path $worktreesRoot "sbx-$newSlug"
    $newDatabase = "tripplanner-sbx-$newSlug"
    & git -C $scriptRepoRoot show-ref --verify --quiet "refs/heads/$newBranch"
    if ($LASTEXITCODE -eq 0) { throw "Local branch already exists: $newBranch." }
    if (Test-Path $newWorktree) { throw "Path already exists: $newWorktree." }

    $action = "Rename to $newSlug (branch, worktree, and database name)"
    if (-not $PSCmdlet.ShouldProcess($entry.slug, $action)) { return }

    $oldBranch = $entry.branch
    $oldWorktree = $entry.worktree
    $oldDatabase = $entry.database

    Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("worktree", "move", $oldWorktree, $newWorktree) | Out-Null
    Invoke-Git -WorkingDirectory $newWorktree -Arguments @("branch", "-m", $oldBranch, $newBranch) | Out-Null

    $entries = @(Get-Registry)
    foreach ($item in $entries) {
        if ($item.slug -eq $entry.slug) {
            $item.slug = $newSlug
            $item.branch = $newBranch
            $item.worktree = $newWorktree
            $item.database = $newDatabase
            # A renamed slot otherwise keeps its prior occupant's purpose text,
            # which reads as a stale, misleading answer to "what is this for?".
            if ($Purpose) { $item.purpose = $Purpose }
        }
    }
    Save-Registry -Entries $entries

    # Publish the new branch before removing the old one, so the work is never
    # only local.
    & git -C $newWorktree push -u origin "HEAD:refs/heads/$newBranch"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Renamed locally, but publishing $newBranch failed. Push it before the next sync."
    } else {
        & git -C $newWorktree rev-parse --verify --quiet "origin/$oldBranch" | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & git -C $newWorktree push origin --delete $oldBranch
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Renamed and published, but the old remote branch $oldBranch remains. Delete it manually."
            }
        }
    }

    Write-Host "[renamed] $($entry.slug) -> $newSlug" -ForegroundColor Green
    Write-Host "[branch]  $newBranch"
    Write-Host "[worktree] $newWorktree"
    Write-Host "[db]      $newDatabase (emulator)"

    # A rename must change the name and nothing else, so the sandbox's data
    # travels with it instead of being left behind under the old name.
    $python = Get-VenvPython
    $seedScript = Join-Path $scriptRepoRoot "scripts/dev/sandbox_seed.py"
    if (Test-Path $seedScript -PathType Leaf) {
        & $python $seedScript move --source $oldDatabase --target $newDatabase
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Renamed, but the emulator data is still in $oldDatabase. Start the Cosmos emulator and run:"
            Write-Warning "  $python $seedScript move --source $oldDatabase --target $newDatabase"
        }
    }
    Write-Host "Reopen any editor window that still points at the old path." -ForegroundColor Cyan
    return
}

if ($PSCmdlet.ParameterSetName -eq "Merge") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree)."
    }
    $gh = Get-RequiredGhCli -Verb "-Merge"
    Commit-SandboxDebugStoreArtifacts -Entry $entry | Out-Null
    $changes = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("status", "--porcelain")
    if ($changes) {
        throw "Sandbox has uncommitted changes. Commit them before merging."
    }
    $action = "Merge into $BaseBranch, then resynchronize the sandbox and keep it"
    if (-not $PSCmdlet.ShouldProcess($entry.branch, $action)) { return }

    Write-Host "== 1/6 fetch latest $BaseBranch and sync the sandbox ==" -ForegroundColor Green
    Sync-PrimaryCheckout -Base $BaseBranch -RequireExact
    Invoke-SandboxUpdateWithRecovery -Slug $slug -WorkingDirectory $entry.worktree `
        -Base $BaseBranch -Verb "-Merge" -SkipBaseFetch:$NoSync

    # The commit the base branch must contain afterwards. Captured before the
    # merge so the post-merge resync cannot be mistaken for the merged work.
    $mergedHead = (Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("rev-parse", "HEAD")).Trim()
    $unmerged = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @(
        "log", "--oneline", "origin/$BaseBranch..HEAD"
    )
    if (-not $unmerged) {
        Write-Host "[current] origin/$BaseBranch already contains every sandbox commit; nothing to merge." -ForegroundColor Green
        Write-Host "[kept]    Sandbox '$slug' stays active on $($entry.branch)." -ForegroundColor Green
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
        $prNumber = (& $gh pr list --head $entry.branch --base $BaseBranch --state open --json number --jq ".[0].number" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "gh pr list failed." }
        if (-not $prNumber) {
            & $gh pr create --base $BaseBranch --head $entry.branch --fill
            if ($LASTEXITCODE -ne 0) { throw "gh pr create failed." }
            $prNumber = (& $gh pr list --head $entry.branch --base $BaseBranch --state open --json number --jq ".[0].number" | Out-String).Trim()
        }
        if (-not $prNumber) { throw "Could not determine the pull request number for $($entry.branch)." }
        Write-Host "[pr]      #$prNumber -> $BaseBranch"

        Write-Host "== 5/6 merge ==" -ForegroundColor Green
        # Never --delete-branch here: the sandbox keeps working on this branch.
        & $gh pr merge $prNumber --merge
        if ($LASTEXITCODE -ne 0) { throw "gh pr merge failed for #$prNumber; merge it manually." }
        Write-Host "[merged]  #$prNumber into $BaseBranch"
    } finally {
        Pop-Location
    }

    Sync-PrimaryCheckout -Base $BaseBranch

    Write-Host "== 6/6 verify and resynchronize ==" -ForegroundColor Green
    Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("fetch", "-q", "origin") | Out-Null
    & git -C $entry.worktree merge-base --is-ancestor $mergedHead "origin/$BaseBranch"
    if ($LASTEXITCODE -ne 0) {
        throw "#$prNumber reported merged, but origin/$BaseBranch does not contain $($mergedHead.Substring(0, 7)). Nothing was discarded; investigate before retrying."
    }

    # A repository that auto-deletes merged branches would strand the sandbox,
    # so restore the branch before handing it back.
    & git -C $entry.worktree rev-parse --verify --quiet "origin/$($entry.branch)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[restore] remote branch was deleted on merge; republishing it." -ForegroundColor Yellow
        Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("push", "-u", "origin", $entry.branch)
    }

    # The base moved when the PR merged, so refresh and resynchronize onto it.
    Invoke-SandboxUpdateWithRecovery -Slug $slug -WorkingDirectory $entry.worktree `
        -Base $BaseBranch -Verb "-Merge"

    Write-Host "[verified] origin/$BaseBranch contains $($mergedHead.Substring(0, 7))."
    Write-Host "[kept]     Sandbox '$slug' stays active on $($entry.branch) and is current with $BaseBranch." -ForegroundColor Green
    Write-Host "Sync your other lanes so they pick up $BaseBranch." -ForegroundColor Cyan
    return
}
if ($PSCmdlet.ParameterSetName -eq "Promote") {
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        throw "Sandbox worktree is missing: $($entry.worktree)."
    }
    $gh = Get-RequiredGhCli -Verb "-Promote"
    Commit-SandboxDebugStoreArtifacts -Entry $entry | Out-Null
    $changes = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @("status", "--porcelain")
    if ($changes) {
        throw "Sandbox has uncommitted changes. Commit them before promoting."
    }
    $action = "Sync, validate, merge into $BaseBranch, verify, and discard the sandbox"
    if (-not $PSCmdlet.ShouldProcess($entry.branch, $action)) { return }

    Write-Host "== 1/6 sync with origin/$BaseBranch ==" -ForegroundColor Green
    Sync-PrimaryCheckout -Base $BaseBranch -RequireExact
    & $PSCommandPath -Update $slug -BaseBranch $BaseBranch -NoSync:$NoSync -Confirm:$false
    $conflicts = Invoke-Git -WorkingDirectory $entry.worktree -Arguments @(
        "diff", "--name-only", "--diff-filter=U"
    )
    if ($conflicts) {
        throw "Resolve and commit these conflicts, then re-run -Promote ${slug}:`n$($conflicts -join "`n")"
    }
    Register-SandboxLabIteration -Entry $entry -Base $BaseBranch -Summary $IterationSummary
    Assert-SandboxLabReadyForPromotion -Entry $entry -Base $BaseBranch -AllowContainedIteration
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
        $prNumber = (& $gh pr list --head $entry.branch --base $BaseBranch --state open --json number --jq ".[0].number" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "gh pr list failed." }
        if (-not $prNumber) {
            & $gh pr create --base $BaseBranch --head $entry.branch --fill
            if ($LASTEXITCODE -ne 0) { throw "gh pr create failed." }
            $prNumber = (& $gh pr list --head $entry.branch --base $BaseBranch --state open --json number --jq ".[0].number" | Out-String).Trim()
        }
        if (-not $prNumber) { throw "Could not determine the pull request number for $($entry.branch)." }
        Write-Host "[pr]      #$prNumber -> $BaseBranch"

        Write-Host "== 5/6 merge ==" -ForegroundColor Green
        & $gh pr merge $prNumber --merge
        if ($LASTEXITCODE -ne 0) { throw "gh pr merge failed for #$prNumber; merge it manually." }
        Write-Host "[merged]  #$prNumber into $BaseBranch"
    } finally {
        Pop-Location
    }

    # GitHub advances the remote base branch, not the local primary checkout.
    # Refresh it before any promotion bookkeeping can create a commit on stale master.
    Sync-PrimaryCheckout -Base $BaseBranch

    # A merge that gh reports as done is not proof: branch protection can queue
    # it, and validation takes long enough for the worktree to be dirtied while
    # it runs. Promotion is only complete once the base branch demonstrably
    # contains everything and nothing is left behind here.
    Write-Host "== 6/6 verify ==" -ForegroundColor Green
    $outstanding = Get-SandboxOutstandingWork -Entry $entry -Base $BaseBranch
    if ($outstanding) {
        throw "#$prNumber merged but sandbox '$slug' is not clean, so it is NOT safe to discard:`n$($outstanding -join "`n")"
    }
    Assert-SandboxLabReadyForPromotion -Entry $entry -Base $BaseBranch -AllowContainedIteration
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
    $currentPath = ConvertTo-ComparablePath -Path (Get-Location).Path
    $liveWorktree = Test-SandboxWorktree -Entry $entry
    if (Test-Path $entry.worktree) {
        $resolved = ConvertTo-ComparablePath -Path (Resolve-Path $entry.worktree).Path
        if ($currentPath -eq $resolved -or $currentPath.StartsWith("$resolved/")) {
            throw "Run -Discard from the primary checkout, not from inside the sandbox worktree."
        }
    }
    if ($liveWorktree) {
        $outstanding = Get-SandboxOutstandingWork -Entry $entry -Base $BaseBranch
        if ($outstanding -and -not $Force) {
            throw "Sandbox '$slug' still holds work that origin/$BaseBranch does not have. Promote it first, or pass -Force to discard anyway:`n$($outstanding -join "`n")"
        }
        if ($outstanding) {
            Write-Warning "Discarding sandbox '$slug' with outstanding work (-Force):`n$($outstanding -join "`n")"
        }
    } elseif (Test-Path $entry.worktree) {
        Write-Warning "$($entry.worktree) is no longer a git worktree; finishing the teardown that was left half done."
    }

    $remoteAction = if ($DeleteRemoteBranch) { ", local and remote branches," } else { ", local branch," }
    if (-not $PSCmdlet.ShouldProcess($slug, "Remove sandbox worktree$remoteAction and emulator database")) {
        return
    }

    $cleanupIssues = @()
    $leftoverPath = ""
    try {
    if (Test-Path $entry.worktree) {
        # Its own servers run from inside the folder, so they must go first whether
        # or not git still recognises it as a worktree.
        Stop-SandboxStack -Entry $entry
    }
    if ($liveWorktree) {
        $removeArgs = @("worktree", "remove", $entry.worktree)
        if ($Force) { $removeArgs += "--force" }
        try {
            Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments $removeArgs
        } catch {
            # git may unregister the worktree yet fail to delete locked files; finish the
            # rest of the teardown so the registry never disagrees with reality.
            Write-Warning "Could not fully delete $($entry.worktree): $($_.Exception.Message)"
            & git -C $scriptRepoRoot worktree prune
        }
        if (-not (Remove-SandboxLeftovers -Path $entry.worktree)) { $leftoverPath = $entry.worktree }
    } else {
        Invoke-Git -WorkingDirectory $scriptRepoRoot -Arguments @("worktree", "prune")
        if ((Test-Path $entry.worktree) -and -not (Remove-SandboxLeftovers -Path $entry.worktree)) {
            $leftoverPath = $entry.worktree
        }
    }

    $pendingConflictPath = Join-Path $primaryRoot "logs/sandbox/pending-conflict-$((Split-Path -Leaf $entry.worktree)).json"
    if (Test-Path -LiteralPath $pendingConflictPath) {
        Remove-Item -LiteralPath $pendingConflictPath -Force
    }

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
    if ($leftoverPath) {
        # The slot is what matters; a folder held open by a stale terminal or editor
        # is cosmetic, and keeping the sandbox listed for that would strand the slot.
        Write-Warning "$leftoverPath is still held open by another process. Everything else is cleaned up; close any window or terminal using that folder and delete it."
    }
    return
}
