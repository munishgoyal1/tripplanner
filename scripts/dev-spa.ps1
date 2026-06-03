# SPA dev runner -- React frontend (Vite) + FastAPI backend together.
#
# This is the "Option C" stack: a standalone React single-page app talking to
# the FastAPI backend (api.py) over HTTP/SSE. It runs ALONGSIDE the Chainlit
# stack (scripts\dev.ps1) -- both are clients of the same agent backend, so you
# can compare them side by side during the migration.
#
# What you get:
#   * FastAPI on :8000 (uvicorn --reload) -- /chat/stream, /trip/view, /trip/select
#   * Vite dev server on :5173 with hot reload; /api is proxied to :8000
#
# Usage:
#   scripts\dev-spa.ps1               # start both (backend + frontend)
#   scripts\dev-spa.ps1 -BackendOnly  # just the API (e.g. frontend already running)
#   scripts\dev-spa.ps1 -FrontendOnly # just Vite (API already running elsewhere)
#
# First-time setup:
#   1. Backend: .venv\Scripts\Activate.ps1 ; pip install -e ".[dev,web]"
#   2. Frontend: cd frontend ; npm install   (once)
#   3. cp frontend\.env.example frontend\.env  (optional; defaults work in dev)

[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $FrontendOnly) {
    Write-Host "Starting FastAPI backend on :$ApiPort ..." -ForegroundColor Cyan
    $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    $backend = Start-Process -PassThru -NoNewWindow $py `
        -ArgumentList "-m", "uvicorn", "multiagent.api:app", "--reload", "--port", "$ApiPort"
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
