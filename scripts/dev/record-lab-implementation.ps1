#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$LabId,

    [string]$Evidence = "",

    [ValidateSet("ready", "implemented-review", "parked", "completed", "discarded")]
    [string]$State = "implemented-review",

    [string]$StorePath
)

$ErrorActionPreference = "Stop"

if ($State -eq "implemented-review" -and -not $Evidence.Trim()) {
    throw "Implementation evidence cannot be blank when recording an implementation."
}

if (-not $StorePath) {
    $repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $StorePath = Join-Path $repoRoot "docs/ux-experiments/LAB_SELECTIONS.json"
}

if (-not (Test-Path -LiteralPath $StorePath)) { throw "Lab selection store not found: $StorePath" }

$lockPath = "$StorePath.lock"
$lock = $null
$deadline = [DateTime]::UtcNow.AddSeconds(10)
while (-not $lock) {
    try {
        $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $lockPayload = @{ pid = $PID; acquiredAt = [DateTime]::UtcNow.ToString("o") } | ConvertTo-Json -Compress
        $lockBytes = [Text.Encoding]::UTF8.GetBytes($lockPayload)
        $lock.Write($lockBytes, 0, $lockBytes.Length)
        $lock.Flush()
    } catch [IO.IOException] {
        $snapshot = if (Test-Path -LiteralPath $lockPath) { Get-Content -LiteralPath $lockPath -Raw -ErrorAction SilentlyContinue } else { "" }
        try {
            $owner = $snapshot | ConvertFrom-Json
            $ageSeconds = ([DateTime]::UtcNow - [DateTime]::Parse($owner.acquiredAt).ToUniversalTime()).TotalSeconds
            $ownerAlive = $null -ne (Get-Process -Id ([int]$owner.pid) -ErrorAction SilentlyContinue)
            $unchanged = $snapshot -eq (Get-Content -LiteralPath $lockPath -Raw -ErrorAction SilentlyContinue)
            if ($ageSeconds -gt 1 -and -not $ownerAlive -and $unchanged) {
                Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
                continue
            }
        } catch {
            # An empty or malformed lock may still belong to a writer acquiring it now.
        }
        if ([DateTime]::UtcNow -ge $deadline) { throw "Timed out waiting for the Lab selection store lock: $lockPath" }
        [Threading.Thread]::Sleep(50)
    }
}

try {
$store = Get-Content -LiteralPath $StorePath -Raw | ConvertFrom-Json -AsHashtable
$lab = $store[$LabId]
if (-not $lab) { throw "Lab '$LabId' does not have a saved handoff." }

$handoffs = @($lab.handoffs)
if (-not $handoffs.Count) { throw "Lab '$LabId' does not have versioned handoff history." }
$handoff = $handoffs | Sort-Object { [int]$_.version } | Select-Object -Last 1
if ($State -eq "completed") {
    $latestImplementation = if (@($lab.implementations).Count) {
        @($lab.implementations) | Sort-Object { [int]$_.version } | Select-Object -Last 1
    } else {
        $lab.implementation
    }
    if ($latestImplementation -and $latestImplementation.handoffVersion) {
        $implementedHandoff = $handoffs | Where-Object {
            [int]$_.version -eq [int]$latestImplementation.handoffVersion
        } | Select-Object -First 1
        if (-not $implementedHandoff) {
            throw "Lab '$LabId' implementation references missing handoff version $($latestImplementation.handoffVersion)."
        }
        $handoff = $implementedHandoff
    }
}
$handoffVersion = (($handoffs | ForEach-Object { [int]$_.version } | Measure-Object -Maximum).Maximum) + 1
$recordedAt = [DateTime]::UtcNow.ToString("o")
$stateRecord = [ordered]@{
    version = $handoffVersion
    selection = [string]$handoff.selection
    selectionLabel = [string]$handoff.selectionLabel
    comment = [string]$handoff.comment
    disposition = $State
    summary = $Evidence.Trim()
    recordedAt = $recordedAt
}
$lab.handoffs = @($handoffs) + @($stateRecord)

if ($State -eq "implemented-review") {
$implementations = if (@($lab.implementations).Count) {
    @($lab.implementations)
} elseif ($lab.implementation) {
    ,([ordered]@{
        version = 1
        handoffVersion = if ($lab.implementation.handoffVersion) { [int]$lab.implementation.handoffVersion } else { 1 }
        selection = [string]$lab.implementation.selection
        selectionLabel = [string]$lab.implementation.selectionLabel
        comment = [string]$lab.implementation.comment
        summary = [string]$lab.implementation.summary
        recordedAt = [string]$lab.implementation.recordedAt
    })
} else {
    @()
}
$existingVersions = @($implementations | ForEach-Object { [int]$_.version })
$version = if ($existingVersions.Count) {
    ($existingVersions | Measure-Object -Maximum).Maximum + 1
} else {
    1
}
$implementation = [ordered]@{
    version = $version
    handoffVersion = $handoffVersion
    selection = [string]$handoff.selection
    selectionLabel = [string]$handoff.selectionLabel
    comment = [string]$handoff.comment
    summary = $Evidence.Trim()
    recordedAt = $recordedAt
}

$lab.implementations = @($implementations) + @($implementation)
$lab.implementation = [ordered]@{
    handoffVersion = $implementation.handoffVersion
    selection = $implementation.selection
    selectionLabel = $implementation.selectionLabel
    comment = $implementation.comment
    summary = $implementation.summary
    recordedAt = $implementation.recordedAt
}
$lab.implementationSummary = $implementation.summary
}
$lab.disposition = $State
$lab.stateChangedAt = $recordedAt
$lab.updatedAt = $recordedAt

$directory = Split-Path -Parent $StorePath
$fileName = [IO.Path]::GetFileNameWithoutExtension($StorePath)
$extension = [IO.Path]::GetExtension($StorePath)
$backupPath = Join-Path $directory "$fileName.previous$extension"
$temporaryPath = "$StorePath.$PID.tmp"
try {
    $store | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $temporaryPath -Encoding utf8NoBOM
    Copy-Item -LiteralPath $StorePath -Destination $backupPath -Force
    Move-Item -LiteralPath $temporaryPath -Destination $StorePath -Force
} finally {
    if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
}

if ($State -eq "implemented-review") {
    Write-Host "Recorded implementation v$version -> state version v$handoffVersion for $LabId."
} else {
    Write-Host "Recorded state '$State' as version v$handoffVersion for $LabId."
}
} finally {
    if ($lock) { $lock.Dispose() }
    if (Test-Path -LiteralPath $lockPath) { Remove-Item -LiteralPath $lockPath -Force }
}