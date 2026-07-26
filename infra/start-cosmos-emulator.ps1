#!/usr/bin/env pwsh
param(
    [int]$ReadyTimeoutSeconds = 120,
    [int]$DockerReadyTimeoutSeconds = 120,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "cosmos-emulator.compose.yml"
$readyUrl = "http://localhost:8080/ready"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required for the Cosmos DB Emulator. Install Docker Desktop and retry."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $dockerDesktop) {
        throw "Docker is installed but its daemon is not running, and Docker Desktop could not be found. Start Docker manually and retry."
    }

    $dockerDesktopProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($dockerDesktopProcess) {
        Write-Host "Docker Desktop is open. Waiting for its daemon ..." -ForegroundColor Yellow
    } else {
        Write-Host "Docker is not running. Starting Docker Desktop ..." -ForegroundColor Yellow
        Start-Process -FilePath $dockerDesktop
    }
    $dockerDeadline = [DateTime]::UtcNow.AddSeconds($DockerReadyTimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Docker Desktop is ready." -ForegroundColor Green
            break
        }
    } while ([DateTime]::UtcNow -lt $dockerDeadline)

    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop did not become ready within $DockerReadyTimeoutSeconds seconds. Check Docker Desktop for a startup error."
    }
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