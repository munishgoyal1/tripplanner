#!/usr/bin/env pwsh

$ErrorActionPreference = "Stop"

Write-Warning "Cloud local Cosmos provisioning was retired. Starting the free local emulator instead."
& "$PSScriptRoot/start-cosmos-emulator.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "Cosmos DB Emulator startup failed."
}
