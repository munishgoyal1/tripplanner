#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$LabId,

    [Parameter(Mandatory)]
    [string]$Evidence,

    [string]$StorePath
)

$ErrorActionPreference = "Stop"

if (-not $Evidence.Trim()) { throw "Implementation evidence cannot be blank." }

if (-not $StorePath) {
    $localDataRoot = if ($env:LOCALAPPDATA) {
        $env:LOCALAPPDATA
    } elseif ($env:HOME) {
        Join-Path $env:HOME ".tripplanner"
    } else {
        throw "Cannot resolve the platform's local data directory."
    }
    $StorePath = Join-Path $localDataRoot "Tripplanner/ux-labs/selections.json"
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
if ($lab.disposition -ne "ready") {
    throw "Lab '$LabId' must be In progress with a ready handoff before implementation can be recorded."
}
if ($lab.disposition -eq "implemented-review") {
    throw "Lab '$LabId' is already implemented and awaiting review. Save a new handoff before recording another implementation."
}

$handoff = $handoffs | Sort-Object { [int]$_.version } | Select-Object -Last 1
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
$recordedAt = [DateTime]::UtcNow.ToString("o")
$implementation = [ordered]@{
    version = $version
    handoffVersion = [int]$handoff.version
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
$lab.disposition = "implemented-review"
$lab.stateChangedAt = $recordedAt
$lab.updatedAt = $recordedAt

$directory = Split-Path -Parent $StorePath
$backupPath = Join-Path $directory "selections.previous.json"
$temporaryPath = "$StorePath.$PID.tmp"
Copy-Item -LiteralPath $StorePath -Destination $backupPath -Force
try {
    $store | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $temporaryPath -Encoding utf8NoBOM
    Move-Item -LiteralPath $temporaryPath -Destination $StorePath -Force
} finally {
    if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
}

Write-Host "Recorded implementation v$version -> handoff v$($handoff.version) for $LabId."
} finally {
    if ($lock) { $lock.Dispose() }
    if (Test-Path -LiteralPath $lockPath) { Remove-Item -LiteralPath $lockPath -Force }
}