#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$ValidateOnly,

    [switch]$ResolveConflicts
)

$ErrorActionPreference = "Stop"
$syncWorker = Join-Path $PSScriptRoot "sync-worker.ps1"

Write-Host "Preflighting Agent 1 and Agent 2..." -ForegroundColor Cyan
& $syncWorker -WorkerNumber 1 -ValidateOnly
& $syncWorker -WorkerNumber 2 -ValidateOnly

if ($ValidateOnly) {
    Write-Host "Ready: both agents can be integrated sequentially."
    return
}

Write-Host "Integrating Agent 1..." -ForegroundColor Cyan
& $syncWorker -WorkerNumber 1 -ResolveConflicts:$ResolveConflicts
Write-Host "Integrating Agent 2..." -ForegroundColor Cyan
& $syncWorker -WorkerNumber 2 -ResolveConflicts:$ResolveConflicts

Write-Host "Synchronizing both workers to the final master..." -ForegroundColor Cyan
& $syncWorker -WorkerNumber 1 -SyncOnly
& $syncWorker -WorkerNumber 2 -SyncOnly

Write-Host "Done: master, Agent 1, and Agent 2 are synchronized." -ForegroundColor Green