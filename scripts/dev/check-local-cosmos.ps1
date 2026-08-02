#!/usr/bin/env pwsh

$ErrorActionPreference = "Stop"

& "$PSScriptRoot/start-cosmos-emulator.ps1" -NoStart
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Output "COSMOS_ENDPOINT=https://localhost:8081"
Write-Output "COSMOS_DATABASE=tripplanner-local"
Write-Output "COSMOS_EMULATOR=1"
