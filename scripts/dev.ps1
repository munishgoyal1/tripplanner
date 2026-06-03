# Local dev runner -- Chainlit chat UI with hot reload.
#
# What this gives you (vs. CI deploy):
#   * ~3 sec restart on any .py change (Chainlit watches src/ recursively).
#   * No Docker build, no GHCR push, no Bicep, no waiting on CI.
#   * Same code path as production -- only persistence backend differs
#     (local JSON in ~/.multiagent by default, or Cosmos if COSMOS_ENDPOINT set).
#
# Usage:
#   scripts\dev.ps1                # default: local JSON storage, port 8000
#   scripts\dev.ps1 -Port 8080     # custom port
#   scripts\dev.ps1 -UseCosmos     # talk to production Cosmos (read/write live data!)
#   scripts\dev.ps1 -WithAuth      # enable OAuth + guest cookie locally
#
# First-time setup:
#   1. Copy .env.example to .env and fill in keys (or already done -- your .env exists).
#   2. .venv\Scripts\Activate.ps1  (only needed once per shell)
#   3. pip install -e ".[dev,web]"  (only needed once)

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$UseCosmos,
    [switch]$WithAuth,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

# Resolve repo root regardless of where script is invoked from.
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path .env)) {
    Write-Error ".env not found. Copy .env.example to .env and fill in your keys first."
    exit 1
}

# Load .env into the current process so things like CHAINLIT_AUTH_SECRET and the
# OAUTH_* values are visible to PowerShell *before* we decide to generate an
# ephemeral fallback. (Chainlit also re-reads .env, this just keeps our checks honest.)
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
        $name  = $Matches[1]
        $value = $Matches[2].Trim('"').Trim("'")
        Set-Item -Path "Env:$name" -Value $value
    }
}

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error ".venv not found. Run:  python -m venv .venv ; .venv\Scripts\python.exe -m pip install -e `".[dev,web]`""
    exit 1
}

# Pull production secrets ONLY if explicitly requested, so we never accidentally
# write to live Cosmos when iterating.
if ($UseCosmos) {
    Write-Host "-> Pulling Cosmos endpoint + key from the live Container App..." -ForegroundColor Cyan
    $appName = "multiagent-app-rb4t6btfs5x5m"
    $rg = "rg-multiagent-trip-planner"
    $envJson = az containerapp show -n $appName -g $rg --query "properties.template.containers[0].env" -o json | ConvertFrom-Json
    $secretsJson = az containerapp secret list -n $appName -g $rg -o json | ConvertFrom-Json

    $cosmosEndpoint = ($envJson | Where-Object { $_.name -eq "COSMOS_ENDPOINT" }).value
    $cosmosKey = ($secretsJson | Where-Object { $_.name -eq "cosmos-key" }).value

    if (-not $cosmosEndpoint -or -not $cosmosKey) {
        Write-Warning "Could not fetch Cosmos credentials. Falling back to local JSON storage."
    } else {
        $env:COSMOS_ENDPOINT = $cosmosEndpoint
        $env:COSMOS_KEY = $cosmosKey
        Write-Host "  Cosmos endpoint: $cosmosEndpoint" -ForegroundColor DarkGray
        Write-Warning "You are reading/writing PRODUCTION Cosmos data. Use a test user identity!"
    }
} else {
    # Make sure local run uses local JSON even if shell has Cosmos vars set.
    $env:COSMOS_ENDPOINT = ""
    $env:COSMOS_KEY = ""
}

if ($WithAuth) {
    if (-not $env:CHAINLIT_AUTH_SECRET) {
        $env:CHAINLIT_AUTH_SECRET = & $python -c "import secrets; print(secrets.token_urlsafe(32))"
        Write-Host "-> Generated ephemeral CHAINLIT_AUTH_SECRET (not in .env)" -ForegroundColor Cyan
        Write-Host "   JWTs will be invalidated on every restart. Add CHAINLIT_AUTH_SECRET to .env for stable sessions." -ForegroundColor DarkYellow
    } else {
        Write-Host "-> Using CHAINLIT_AUTH_SECRET from .env (sessions survive restarts)" -ForegroundColor Cyan
    }
    if ($env:OAUTH_GOOGLE_CLIENT_ID -and $env:OAUTH_GOOGLE_CLIENT_SECRET) {
        Write-Host "-> Google OAuth provider configured" -ForegroundColor Cyan
    } else {
        Write-Host "  Note: OAuth requires separate dev OAuth apps with localhost redirect URIs." -ForegroundColor DarkGray
        Write-Host "        See docs/setup-oauth.md -> 'Local development with OAuth' section." -ForegroundColor DarkGray
    }
} else {
    # Force-disable auth for the cleanest local loop.
    $env:CHAINLIT_AUTH_SECRET = ""
}

$chainlitArgs = @(
    "-m", "chainlit", "run", "src/multiagent/web/app.py",
    "--port", "$Port",
    "-w"
)
if ($NoBrowser) { $chainlitArgs += "--headless" }

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  Trip Planner -- local dev (hot reload)" -ForegroundColor Green
Write-Host "  http://localhost:$Port" -ForegroundColor Green
Write-Host "  Storage: $(if ($UseCosmos) { 'Cosmos (PROD)' } else { '~/.multiagent/ (local JSON)' })" -ForegroundColor Green
Write-Host "  Auth:    $(if ($WithAuth) { 'enabled' } else { 'disabled (guest-only)' })" -ForegroundColor Green
Write-Host "  Edit any .py file in src/ -> page reloads in ~3s" -ForegroundColor Green
Write-Host "  Ctrl+C to stop" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""

& $python @chainlitArgs
