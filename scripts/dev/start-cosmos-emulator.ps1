#!/usr/bin/env pwsh
param(
    [int]$ReadyTimeoutSeconds = 120,
    [int]$DockerReadyTimeoutSeconds = 120,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "cosmos-emulator.compose.yml"
$emulatorImage = "mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-latest"
$readyUrl = "http://localhost:8080/ready"

function Invoke-DockerCommand {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    $output = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        if ($output) {
            $output | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        }
        throw $FailureMessage
    }
    return @($output)
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required for the Cosmos DB Emulator. Install Docker Desktop and retry."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerDesktopCandidates = if ($IsWindows) {
        @(
            (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
            (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
        )
    } elseif ($IsMacOS) {
        @("/Applications/Docker.app")
    } else {
        @()
    }
    $dockerDesktop = $dockerDesktopCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $dockerDesktop) {
        throw "Docker is installed but its daemon is not running, and Docker Desktop could not be found. Start Docker manually and retry."
    }

    $dockerDesktopProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($dockerDesktopProcess) {
        Write-Host "Docker Desktop is open. Waiting for its daemon ..." -ForegroundColor Yellow
    } else {
        Write-Host "Docker is not running. Starting Docker Desktop ..." -ForegroundColor Yellow
        if ($IsMacOS) {
            Start-Process -FilePath "open" -ArgumentList @("-a", "Docker")
        } else {
            Start-Process -FilePath $dockerDesktop
        }
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
    docker image inspect $emulatorImage *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "First run: downloading the Cosmos DB Emulator image. This is large and can take several minutes." -ForegroundColor Yellow
        Invoke-DockerCommand -Arguments @("pull", "--quiet", $emulatorImage) `
            -FailureMessage "Cosmos DB Emulator image download failed." | Out-Null
        Write-Host "Cosmos DB Emulator image downloaded." -ForegroundColor Green
    }
    Write-Host "Starting Cosmos DB Emulator container ..." -ForegroundColor Cyan
    Invoke-DockerCommand -Arguments @("compose", "-f", $composeFile, "up", "-d", "--no-build") `
        -FailureMessage "Cosmos DB Emulator container failed to start." | Out-Null
}

$deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
$stalePidRepairAfter = [DateTime]::UtcNow.AddSeconds(10)
$stalePidRepairAttempted = $false
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

    if (-not $stalePidRepairAttempted -and [DateTime]::UtcNow -ge $stalePidRepairAfter) {
        $repairResult = docker exec tripplanner-cosmos sh -lc 'if ! pgrep -x postgres >/dev/null 2>&1 && { [ -f /data/db/postmaster.pid ] || [ -e /socket/.s.PGSQL.9712 ] || [ -e /socket/.s.PGSQL.9712.lock ]; }; then rm -f /data/db/postmaster.pid /socket/.s.PGSQL.9712 /socket/.s.PGSQL.9712.lock && echo repaired; fi' 2>$null
        if ($LASTEXITCODE -eq 0 -and $repairResult -contains "repaired") {
            $stalePidRepairAttempted = $true
            Write-Host "Recovering Cosmos DB Emulator from stale PostgreSQL runtime locks ..." -ForegroundColor Yellow
            docker restart tripplanner-cosmos *> $null
            if ($LASTEXITCODE -ne 0) {
                throw "Cosmos DB Emulator failed to restart after stale-lock recovery."
            }
            $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
        }
    }
    Start-Sleep -Seconds 2
} while ([DateTime]::UtcNow -lt $deadline)

throw "Cosmos DB Emulator did not become ready within $ReadyTimeoutSeconds seconds."