#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$workerScript = Join-Path $PSScriptRoot "merge-worker.ps1"

Write-Host "Preflighting Worker 1 and Worker 2..." -ForegroundColor Cyan
foreach ($workerNumber in 1, 2) {
    & $workerScript -WorkerNumber $workerNumber -ValidateOnly
}

if ($ValidateOnly) {
    Write-Host "Ready: both workers can be integrated sequentially."
    return
}

foreach ($workerNumber in 1, 2) {
    Write-Host "Integrating Worker $workerNumber..." -ForegroundColor Cyan
    & $workerScript -WorkerNumber $workerNumber
}

Write-Host "Done: Worker 1 and Worker 2 are integrated into master." -ForegroundColor Green