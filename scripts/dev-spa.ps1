# SPA dev runner -- React frontend (Vite) + FastAPI backend together.
#
# The app stack: a standalone React single-page app talking to the FastAPI
# backend (api.py) over HTTP/SSE. This is the only UI; in production FastAPI
# also serves the built SPA from frontend/dist on the same port.
#
# What you get:
#   * FastAPI on :8000 (uvicorn) -- /chat/stream, /trip/view, /trip/select
#   * Vite dev server on :5173; /api is proxied to :8000
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
#   scripts\dev-spa.ps1 -FrontendOnly # just Vite (API already running elsewhere)
#   scripts\dev-spa.ps1 -UseCanaryData # point local backend at the CANARY Cosmos
#                                       # (default: ISOLATED local Cosmos from .env,
#                                       #  so local + canary trip data never mix)
#
# First-time setup:
#   1. Backend: .venv\Scripts\Activate.ps1 ; pip install -e ".[dev]"
#   2. Frontend: cd frontend ; npm install   (once)
#   3. cp frontend\.env.example frontend\.env  (optional; defaults work in dev)

[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$Watch,
    [switch]$Logs,
    [switch]$UseCanaryData
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# By default the local backend uses the ISOLATED local Cosmos configured in
# .env (COSMOS_ENDPOINT=localcosmos...), so local dev never mixes trip/chat data
# with the canary deployment. Pass -UseCanaryData to deliberately share the
# canary store. Clear any stale process-level overrides so .env wins via
# load_dotenv() (which does NOT override existing env vars).
if (-not $UseCanaryData) {
    foreach ($v in 'COSMOS_ENDPOINT', 'COSMOS_KEY', 'COSMOS_DATABASE') {
        Remove-Item "Env:$v" -ErrorAction SilentlyContinue
    }
    Write-Host "Using ISOLATED local Cosmos from .env (pass -UseCanaryData to share canary store)." -ForegroundColor DarkGray
}

if (-not $FrontendOnly -and $UseCanaryData) {
    try {
        if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
            throw "Azure CLI (az) not found"
        }

        $canaryRg = "rg-tripplanner-canary"
        $cosmosName = az resource list -g $canaryRg --resource-type Microsoft.DocumentDB/databaseAccounts --query "[0].name" -o tsv
        if (-not [string]::IsNullOrWhiteSpace($cosmosName)) {
            $cosmosEndpoint = az cosmosdb show -g $canaryRg -n $cosmosName --query documentEndpoint -o tsv
            $cosmosKey = az cosmosdb keys list -g $canaryRg -n $cosmosName --query primaryMasterKey -o tsv
            if (-not [string]::IsNullOrWhiteSpace($cosmosEndpoint) -and -not [string]::IsNullOrWhiteSpace($cosmosKey)) {
                $env:COSMOS_ENDPOINT = $cosmosEndpoint
                $env:COSMOS_KEY = $cosmosKey
                if ([string]::IsNullOrWhiteSpace($env:COSMOS_DATABASE)) {
                    $env:COSMOS_DATABASE = "tripplanner"
                }
                Write-Host "Using canary Cosmos for local backend state ($cosmosName)." -ForegroundColor DarkGray
            }
        }
    }
    catch {
        Write-Host "Could not auto-wire canary Cosmos ($($_.Exception.Message)); continuing with local storage." -ForegroundColor Yellow
    }
}

if (-not $FrontendOnly) {
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
    Write-Host "Starting Vite dev server on :5173 ..." -ForegroundColor Cyan
    Push-Location frontend
    try {
        $env:VITE_API_TARGET = "http://localhost:$ApiPort"
        $env:VITE_HMR = if ($Watch) { "1" } else { "0" }
        npm run dev
    }
    finally {
        Pop-Location
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

