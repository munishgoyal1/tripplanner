#!/usr/bin/env pwsh
param(
    [int]$ReadyTimeoutSeconds = 120,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "cosmos-emulator.compose.yml"
$readyUrl = "http://localhost:8080/ready"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required for the Cosmos DB Emulator. Install/start Docker Desktop and retry."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is installed but not running. Start Docker Desktop and retry."
}

if (-not $NoStart) {
    docker compose -f $composeFile up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Cosmos DB Emulator container failed to start."
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
do {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $readyUrl -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            Write-Host "Cosmos DB Emulator is ready at https://localhost:8081." -ForegroundColor Green
            exit 0
        }
    }
    catch {
        if ($NoStart) {
            throw "Cosmos DB Emulator is not ready at $readyUrl."
        }
    }
    Start-Sleep -Seconds 2
} while ([DateTime]::UtcNow -lt $deadline)

throw "Cosmos DB Emulator did not become ready within $ReadyTimeoutSeconds seconds."