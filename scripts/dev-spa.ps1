# SPA dev runner -- React frontend (Vite) + FastAPI backend together.
#
# The app stack: a standalone React single-page app talking to the FastAPI
# backend (api.py) over HTTP/SSE. This is the only UI; in production FastAPI
# also serves the built SPA from frontend/dist on the same port.
#
# What you get:
#   * FastAPI on :8000 (uvicorn) -- /chat/stream, /trip/view, /trip/select
#   * Vite dev server on :5173; /api is proxied to :8000
#   * UX Labs Vite server on :5175; catalog at /catalog.html
#
# If a previous dev run left Vite holding :5173/:5175 or uvicorn holding :8000,
# the script stops that stale tripplanner process before starting a new one. It
# refuses to terminate an unrelated process using any configured port.
#
# Hot reload is OFF by default (matches the no-auto-reload preference):
#   * Frontend changes  -> refresh the browser (Ctrl+R) to pick them up.
#   * Backend changes   -> Ctrl+C and rerun this script.
#   Pass -Watch to enable live reload for both (uvicorn --reload + Vite HMR).
#
# Usage:
#   scripts\dev-spa.ps1               # start both (backend + frontend), no hot reload
#   scripts\dev-spa.ps1 -Watch        # enable live reload for both
#   scripts\dev-spa.ps1 -Logs         # verbose backend logs (LOG_LEVEL=DEBUG)
#   scripts\dev-spa.ps1 -BackendOnly  # just the API (e.g. frontend already running)
#   scripts\dev-spa.ps1 -FrontendOnly # main SPA + Labs (API already running elsewhere)
#   scripts\dev-spa.ps1 -NoLabs       # skip the UX Labs server
#   scripts\dev-spa.ps1 -CosmosBackend azure # explicit Azure local database
#   scripts\dev-spa.ps1 -UseCanaryData # explicitly use hosted canary data
#
# Cosmos backend precedence: -CosmosBackend, COSMOS_DEV_BACKEND environment,
# .env COSMOS_DEV_BACKEND, then the default "emulator". Azure mode explicitly
# uses the isolated tripplanner-local database in the shared data account. In
# emulator mode, Docker Desktop is launched automatically when it is installed
# but not running.
#
# First-time setup:
#   1. Backend: .venv\Scripts\Activate.ps1 ; pip install -e ".[dev]"
#   2. Frontend: cd frontend ; npm install   (once)
#   3. cp frontend\.env.example frontend\.env  (optional; defaults work in dev)

[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$LabsPort = 5175,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$NoLabs,
    [switch]$Watch,
    [switch]$Logs,
    [ValidateSet("azure", "emulator")]
    [string]$CosmosBackend,
    [switch]$UseCanaryData
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $BackendOnly -and -not $NoLabs -and $FrontendPort -eq $LabsPort) {
    throw "FrontendPort and LabsPort must be different."
}

function Get-DotEnvValue {
    param(
        [string]$Name
    )

    $envPath = Join-Path $repoRoot ".env"
    if (-not (Test-Path $envPath)) {
        return $null
    }
    $match = Get-Content $envPath | Where-Object {
        $_ -match "^\s*$([regex]::Escape($Name))\s*="
    } | Select-Object -Last 1
    if (-not $match) {
        return $null
    }
    return (($match -split "=", 2)[1].Trim()).Trim('"').Trim("'")
}

$configuredCosmosBackend = if ($PSBoundParameters.ContainsKey("CosmosBackend")) {
    $CosmosBackend
} elseif (-not [string]::IsNullOrWhiteSpace($env:COSMOS_DEV_BACKEND)) {
    $env:COSMOS_DEV_BACKEND.Trim().ToLowerInvariant()
} else {
    $dotEnvBackend = Get-DotEnvValue -Name "COSMOS_DEV_BACKEND"
    if ([string]::IsNullOrWhiteSpace($dotEnvBackend)) { "emulator" } else { $dotEnvBackend.Trim().ToLowerInvariant() }
}
if ($configuredCosmosBackend -notin @("azure", "emulator")) {
    throw "COSMOS_DEV_BACKEND must be 'azure' or 'emulator'; got '$configuredCosmosBackend'."
}
if ($UseCanaryData -and $PSBoundParameters.ContainsKey("CosmosBackend") -and $CosmosBackend -eq "emulator") {
    throw "-UseCanaryData cannot be combined with -CosmosBackend emulator."
}

function Stop-StaleTripplannerBackend {
    param(
        [int]$Port
    )

    $listener = $null
    try {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    } catch {
        $listener = $null
    }

    if (-not $listener) {
        return
    }

    $proc = $null
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    } catch {
        $proc = $null
    }

    $procName = if ($proc) { $proc.Name } else { "PID $($listener.OwningProcess)" }
    $commandLine = if ($proc -and $proc.CommandLine) { $proc.CommandLine } else { "" }
    $isTripplannerBackend = $commandLine -match 'tripplanner\.api:app' -or $commandLine -match 'uvicorn\s+tripplanner\.api:app'

    if (-not $isTripplannerBackend) {
        throw "Port $Port is already in use by $procName. Stop that process or use -ApiPort <port>."
    }

    Write-Host "Stopping stale tripplanner backend on :$Port ..." -ForegroundColor Yellow
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop

    $remaining = $null
    try {
        $remaining = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    } catch {
        $remaining = $null
    }

    if ($remaining) {
        throw "Stopped PID $($listener.OwningProcess), but port $Port is still busy. Try closing the leftover process manually."
    }
}

function Stop-StaleTripplannerFrontend {
    param(
        [int]$Port
    )

    $listener = $null
    try {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    } catch {
        $listener = $null
    }

    if (-not $listener) {
        return
    }

    $proc = $null
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    } catch {
        $proc = $null
    }

    $procName = if ($proc) { $proc.Name } else { "PID $($listener.OwningProcess)" }
    $commandLine = if ($proc -and $proc.CommandLine) { $proc.CommandLine } else { "" }
    $frontendPath = [regex]::Escape((Join-Path $repoRoot "frontend"))
    $isTripplannerFrontend = $procName -ieq "node.exe" `
        -and $commandLine -match '(?i)[\\/]vite[\\/]bin[\\/]vite\.js' `
        -and $commandLine -match "(?i)$frontendPath"

    if (-not $isTripplannerFrontend) {
        throw "Port $Port is already in use by $procName. Stop that process or use -FrontendPort <port>."
    }

    Write-Host "Stopping stale tripplanner frontend on :$Port ..." -ForegroundColor Yellow
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
    Wait-Process -Id $listener.OwningProcess -Timeout 5 -ErrorAction SilentlyContinue

    $remaining = $null
    try {
        $remaining = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    } catch {
        $remaining = $null
    }

    if ($remaining) {
        throw "Stopped PID $($listener.OwningProcess), but port $Port is still busy. Try closing the leftover process manually."
    }
}

if (-not $BackendOnly) {
    Stop-StaleTripplannerFrontend -Port $FrontendPort
    if (-not $NoLabs) {
        Stop-StaleTripplannerFrontend -Port $LabsPort
    }
}

if (-not $FrontendOnly -and -not $UseCanaryData -and $configuredCosmosBackend -eq "emulator") {
    & "$repoRoot\infra\start-cosmos-emulator.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "Cosmos DB Emulator startup failed."
    }

    $env:COSMOS_ENDPOINT = "https://localhost:8081"
    $env:COSMOS_KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
    $env:COSMOS_DATABASE = "tripplanner-local"
    $env:COSMOS_EMULATOR = "1"
    Write-Host "Using isolated local Cosmos DB Emulator." -ForegroundColor DarkGray
}

if (-not $FrontendOnly -and ($UseCanaryData -or $configuredCosmosBackend -eq "azure")) {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw "Azure CLI (az) not found; use -CosmosBackend emulator or install/sign in to Azure CLI."
    }

    $cosmosRg = if ($env:COSMOS_RESOURCE_GROUP) { $env:COSMOS_RESOURCE_GROUP } else { "rg-tripplanner-data" }
    $cosmosName = if ($env:COSMOS_ACCOUNT_NAME) { $env:COSMOS_ACCOUNT_NAME } else {
        $accounts = @(az resource list -g $cosmosRg --resource-type Microsoft.DocumentDB/databaseAccounts --query "[].name" -o tsv)
        if ($accounts.Count -ne 1) {
            throw "Expected exactly one Cosmos account in $cosmosRg; found $($accounts.Count). Set COSMOS_ACCOUNT_NAME explicitly."
        }
        $accounts[0]
    }
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($cosmosName)) {
        throw "No shared Cosmos account found in $cosmosRg; refusing ambiguous Azure Cosmos startup."
    }
    $cosmosEndpoint = az cosmosdb show -g $cosmosRg -n $cosmosName --query documentEndpoint -o tsv
    $cosmosKey = az cosmosdb keys list -g $cosmosRg -n $cosmosName --query primaryMasterKey -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($cosmosEndpoint) -or [string]::IsNullOrWhiteSpace($cosmosKey)) {
        throw "Could not resolve Azure Cosmos credentials; refusing ambiguous startup."
    }
    $cosmosDatabase = if ($UseCanaryData) { "tripplanner-canary" } else { "tripplanner-local" }
    az cosmosdb sql database show -g $cosmosRg -a $cosmosName -n $cosmosDatabase -o none
    if ($LASTEXITCODE -ne 0) {
        throw "Required database $cosmosDatabase does not exist. Deploy infra/data-stack.bicep first, or use -CosmosBackend emulator."
    }
    $env:COSMOS_ENDPOINT = $cosmosEndpoint
    $env:COSMOS_KEY = $cosmosKey
    $env:COSMOS_DATABASE = $cosmosDatabase
    Remove-Item Env:COSMOS_EMULATOR -ErrorAction SilentlyContinue
    Write-Host "Using Azure Cosmos database $cosmosDatabase ($cosmosName)." -ForegroundColor DarkGray
}

if (-not $FrontendOnly) {
    Stop-StaleTripplannerBackend -Port $ApiPort
    Write-Host "Starting FastAPI backend on :$ApiPort ..." -ForegroundColor Cyan
    if ($Logs) {
        $env:LOG_LEVEL = "DEBUG"
        Write-Host "  LOG_LEVEL=DEBUG (verbose backend logs)" -ForegroundColor DarkGray
    }
    $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    # src-layout project: make imports work even if pip install -e . was not run.
    $uvicornArgs = @("-m", "uvicorn", "tripplanner.api:app", "--app-dir", "src", "--port", "$ApiPort")
    if ($Watch) { $uvicornArgs += "--reload" }
    $backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory $repoRoot $py -ArgumentList $uvicornArgs
}

if (-not $BackendOnly) {
    if (-not (Test-Path "frontend\node_modules")) {
        Write-Host "Installing frontend dependencies (first run)..." -ForegroundColor Yellow
        Push-Location frontend
        npm install
        Pop-Location
    }
    $labs = $null
    if (-not $NoLabs) {
        Write-Host "Starting UX Labs on :$LabsPort ..." -ForegroundColor Cyan
        $env:VITE_LABS_PORT = "$LabsPort"
        $env:VITE_HMR = if ($Watch) { "1" } else { "0" }
        $labs = Start-Process -PassThru -NoNewWindow -WorkingDirectory (Join-Path $repoRoot "frontend") `
            -FilePath "npm.cmd" -ArgumentList @("run", "dev:ux-lab")
        Write-Host "  Labs: http://127.0.0.1:$LabsPort/catalog.html" -ForegroundColor Green
    }

    Write-Host "Starting Vite dev server on :$FrontendPort ..." -ForegroundColor Cyan
    Push-Location frontend
    try {
        $env:VITE_API_TARGET = "http://localhost:$ApiPort"
        $env:VITE_PORT = "$FrontendPort"
        $env:VITE_HMR = if ($Watch) { "1" } else { "0" }
        npm run dev
    }
    finally {
        Pop-Location
        if ($labs) {
            try {
                Stop-StaleTripplannerFrontend -Port $LabsPort
            } catch {
                Write-Warning "Could not stop the UX Labs server cleanly: $($_.Exception.Message)"
            }
            if (-not $labs.HasExited) {
                Stop-Process -Id $labs.Id -ErrorAction SilentlyContinue
            }
        }
        if ($backend -and -not $backend.HasExited) {
            Write-Host "Stopping backend..." -ForegroundColor Cyan
            Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
        }
    }
}
elseif ($backend) {
    Write-Host "Backend running (PID $($backend.Id)). Press Ctrl+C to stop." -ForegroundColor Green
    Wait-Process -Id $backend.Id
}

