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
    [switch]$Logs
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $FrontendOnly) {
    Write-Host "Starting FastAPI backend on :$ApiPort ..." -ForegroundColor Cyan
    if ($Logs) {
        $env:LOG_LEVEL = "DEBUG"
        Write-Host "  LOG_LEVEL=DEBUG (verbose backend logs)" -ForegroundColor DarkGray
    }
    $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    $uvicornArgs = @("-m", "uvicorn", "tripplanner.api:app", "--port", "$ApiPort")
    if ($Watch) { $uvicornArgs += "--reload" }
    $backend = Start-Process -PassThru -NoNewWindow $py -ArgumentList $uvicornArgs
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

