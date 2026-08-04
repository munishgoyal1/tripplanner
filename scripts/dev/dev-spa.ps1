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
# If a previous dev run left any configured port occupied, the script force-
# stops the listening process tree and verifies the port is free before restart.
#
# Hot reload is OFF by default (matches the no-auto-reload preference):
#   * Frontend changes  -> refresh the browser (Ctrl+R) to pick them up.
#   * Backend changes   -> Ctrl+C and rerun this script.
#   Pass -Watch to enable live reload for both (uvicorn --reload + Vite HMR).
#
# Usage:
#   scripts\dev\dev-spa.ps1               # start both, no hot reload
#   scripts\dev\dev-spa.ps1 -Watch        # enable live reload for both
#   scripts\dev\dev-spa.ps1 -Logs         # verbose backend logs
#   scripts\dev\dev-spa.ps1 -BackendOnly  # just the API
#   scripts\dev\dev-spa.ps1 -FrontendOnly # main SPA + Labs
#   scripts\dev\dev-spa.ps1 -NoLabs       # skip the UX Labs server
#   scripts\dev\dev-spa.ps1 -CosmosBackend azure # Azure local database
#   scripts\dev\dev-spa.ps1 -UseCanaryData # hosted canary data
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
    [switch]$UseCanaryData,
    # Emulator-only: run against a custom isolated database (e.g. a sandbox DB)
    # instead of the default tripplanner-local. Live database names are refused.
    [string]$CosmosDatabase
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
Start-RunLog -Name "dev-spa" | Out-Null
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sharedRepoRoot = $repoRoot
if (Get-Command git -ErrorAction SilentlyContinue) {
    $gitCommonDir = (& git -C $repoRoot rev-parse --path-format=absolute --git-common-dir 2>$null |
        Select-Object -First 1)
    if ($LASTEXITCODE -eq 0 -and
        -not [string]::IsNullOrWhiteSpace($gitCommonDir) -and
        (Split-Path -Leaf $gitCommonDir) -eq ".git") {
        $sharedRepoRoot = Split-Path -Parent $gitCommonDir
    }
}
Set-Location $repoRoot

$activePorts = @()
if (-not $FrontendOnly) { $activePorts += $ApiPort }
if (-not $BackendOnly) {
    $activePorts += $FrontendPort
    if (-not $NoLabs) { $activePorts += $LabsPort }
}
if (($activePorts | Sort-Object -Unique).Count -ne $activePorts.Count) {
    throw "ApiPort, FrontendPort, and LabsPort must be different when their services are enabled."
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
if ($PSBoundParameters.ContainsKey("CosmosDatabase") -and $configuredCosmosBackend -ne "emulator") {
    throw "-CosmosDatabase is only supported with -CosmosBackend emulator."
}

function Clear-ListeningPort {
    param(
        [int]$Port,
        [string]$Service
    )

    $listeners = @()
    try {
        $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        $listeners = @()
    }

    if ($listeners.Count -eq 0) {
        return
    }

    $processIds = @($listeners.OwningProcess | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
    Write-Host "Clearing $Service port :$Port (PID $($processIds -join ', ')) ..." -ForegroundColor Yellow
    foreach ($processId in $processIds) {
        & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            throw "Could not stop PID $processId on $Service port $Port."
        }
        Wait-Process -Id $processId -Timeout 5 -ErrorAction SilentlyContinue
    }

    $remaining = @()
    try {
        $remaining = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        $remaining = @()
    }

    if ($remaining.Count -gt 0) {
        $remainingIds = @($remaining.OwningProcess | Sort-Object -Unique) -join ", "
        throw "$Service port $Port is still occupied by PID $remainingIds after forced cleanup."
    }
}

if (-not $FrontendOnly) {
    Clear-ListeningPort -Port $ApiPort -Service "FastAPI"
}
if (-not $BackendOnly) {
    Clear-ListeningPort -Port $FrontendPort -Service "SPA"
    if (-not $NoLabs) {
        Clear-ListeningPort -Port $LabsPort -Service "UX Labs"
    }
}

if (-not $FrontendOnly -and -not $UseCanaryData -and $configuredCosmosBackend -eq "emulator") {
    & "$PSScriptRoot\start-cosmos-emulator.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "Cosmos DB Emulator startup failed."
    }

    $emulatorDatabase = "tripplanner-local"
    if (-not [string]::IsNullOrWhiteSpace($CosmosDatabase)) {
        if ($CosmosDatabase.Trim().ToLowerInvariant() -in @("tripplanner-canary", "tripplanner-prod")) {
            throw "-CosmosDatabase must not be a live canary or production database."
        }
        $emulatorDatabase = $CosmosDatabase.Trim()
    }
    $env:COSMOS_ENDPOINT = "https://localhost:8081"
    $env:COSMOS_KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
    $env:COSMOS_DATABASE = $emulatorDatabase
    $env:COSMOS_EMULATOR = "1"
    Write-Host "Using isolated local Cosmos DB Emulator (database $emulatorDatabase)." -ForegroundColor DarkGray
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
    Write-Host "Starting FastAPI backend on :$ApiPort ..." -ForegroundColor Cyan
    if ([string]::IsNullOrWhiteSpace($env:APP_LOG_PATH)) {
        $env:APP_LOG_PATH = Join-Path $sharedRepoRoot "logs\diagnostics\local-app.jsonl"
    }
    Write-Host "  Diagnostics: $env:APP_LOG_PATH" -ForegroundColor DarkGray
    if ($Logs) {
        $env:LOG_LEVEL = "DEBUG"
        Write-Host "  LOG_LEVEL=DEBUG (verbose backend logs)" -ForegroundColor DarkGray
    }
    $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = Join-Path $sharedRepoRoot ".venv\Scripts\python.exe" }
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
        # Stable guest identity for emulator dev; the sandbox seed re-owns the
        # owner's data under this id (keep in sync with sandbox_seed.py).
        if ($configuredCosmosBackend -eq "emulator") {
            $env:VITE_DEV_GUEST_ID = "web-00000000-0000-4000-8000-000000000001"
        }
        npm run dev
    }
    finally {
        Pop-Location
        if ($labs) {
            try {
                Clear-ListeningPort -Port $LabsPort -Service "UX Labs"
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
