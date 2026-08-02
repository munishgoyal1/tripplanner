#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(1, 2)]
    [int]$WorkerNumber,

    [switch]$ValidateOnly,

    [switch]$ResolveConflicts
)

$ErrorActionPreference = "Stop"
$syncWorker = Join-Path $PSScriptRoot "sync-worker.ps1"
$workerNumbers = if ($PSBoundParameters.ContainsKey("WorkerNumber")) {
    @($WorkerNumber)
} else {
    @(1, 2)
}
$workerLabel = if ($workerNumbers.Count -eq 1) {
    "Agent $($workerNumbers[0])"
} else {
    "Agent 1 and Agent 2"
}

Write-Host "Preflighting $workerLabel..." -ForegroundColor Cyan
foreach ($number in $workerNumbers) {
    & $syncWorker -WorkerNumber $number -ValidateOnly
}

if ($ValidateOnly) {
    Write-Host "Ready: $workerLabel can be integrated."
    return
}

foreach ($number in $workerNumbers) {
    Write-Host "Integrating Agent $number..." -ForegroundColor Cyan
    & $syncWorker -WorkerNumber $number -ResolveConflicts:$ResolveConflicts
}

if ($workerNumbers.Count -gt 1) {
    Write-Host "Synchronizing selected workers to the final master..." -ForegroundColor Cyan
    foreach ($number in $workerNumbers) {
        & $syncWorker -WorkerNumber $number -SyncOnly
    }
}

Write-Host "Done: master and $workerLabel are synchronized." -ForegroundColor Green