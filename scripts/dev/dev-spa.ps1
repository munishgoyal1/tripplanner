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
    # Audit inspector. Derived from LabsPort by default so every sandbox slot gets
    # a free port without another entry in sandboxes.json.
    [int]$InspectorPort = 0,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$NoLabs,
    [switch]$NoInspector,
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
. "$PSScriptRoot/lib/node-tools.ps1"
# Sandboxes run this script concurrently on their own ports; keying the transcript
# by API port keeps a second stack from losing its log to the first one's lock.
$devSpaLogName = if ($ApiPort -eq 8000) { "dev-spa" } else { "dev-spa-$ApiPort" }
Start-RunLog -Name $devSpaLogName | Out-Null
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
if ($InspectorPort -le 0) { $InspectorPort = $LabsPort + 2 }
if (-not $FrontendOnly) { $activePorts += $ApiPort }
if (-not $BackendOnly) {
    $activePorts += $FrontendPort
    if (-not $NoLabs) { $activePorts += $LabsPort }
    if (-not $NoInspector) { $activePorts += $InspectorPort }
}
if (($activePorts | Sort-Object -Unique).Count -ne $activePorts.Count) {
    throw "ApiPort, FrontendPort, LabsPort, and InspectorPort must be different when their services are enabled."
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
    $processIds = @()
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        try {
            $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
            $processIds = @($listeners.OwningProcess | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
        } catch {
            $listeners = @()
        }
    }
    if ($processIds.Count -eq 0 -and -not $IsWindows -and (Get-Command lsof -ErrorAction SilentlyContinue)) {
        $processIds = @(& lsof -nP -tiTCP:$Port -sTCP:LISTEN 2>$null |
            Where-Object { $_ -match "^\d+$" } |
            ForEach-Object { [int]$_ } |
            Sort-Object -Unique)
    }

    if ($processIds.Count -eq 0) {
        return
    }

    Write-Host "Clearing $Service port :$Port (PID $($processIds -join ', ')) ..." -ForegroundColor Yellow
    foreach ($processId in $processIds) {
        if ($IsWindows) {
            & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
        } else {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
        try {
            Wait-Process -Id $processId -Timeout 5 -ErrorAction SilentlyContinue
        } catch {
            # The process may have exited before Wait-Process attached.
        }
    }

    $remaining = @()
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        try {
            $remaining = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        } catch {
            $remaining = @()
        }
    }

    if ($remaining.Count -gt 0) {
        $remainingIds = @($remaining.OwningProcess | Sort-Object -Unique) -join ", "
        throw "$Service port $Port is still occupied by PID $remainingIds after forced cleanup."
    }
    if (-not $IsWindows -and (Get-Command lsof -ErrorAction SilentlyContinue)) {
        $remainingIds = @(& lsof -nP -tiTCP:$Port -sTCP:LISTEN 2>$null |
            Where-Object { $_ -match "^\d+$" } |
            Sort-Object -Unique)
        if ($remainingIds.Count -gt 0) {
            throw "$Service port $Port is still occupied by PID $($remainingIds -join ', ') after forced cleanup."
        }
    }
}

function Wait-BackendReady {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $healthUrl = "http://127.0.0.1:$Port/health"
    $lastHealthError = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "FastAPI backend exited with code $($Process.ExitCode) before becoming ready."
        }
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
            if ($health.status -eq "ok") {
                Write-Host "  Backend ready: $healthUrl" -ForegroundColor Green
                return
            }
        } catch {
            $lastHealthError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 200
    }
    $detail = if ($lastHealthError) { " Last error: $lastHealthError" } else { "" }
    throw "FastAPI backend did not become ready at $healthUrl within $TimeoutSeconds seconds.$detail"
}

function Test-FrontendDependenciesCurrent {
    param(
        [Parameter(Mandatory = $true)][string]$FrontendRoot
    )

    $nodeModules = Join-Path $FrontendRoot "node_modules"
    $viteExecutable = if ($IsWindows) { "vite.cmd" } else { "vite" }
    $viteBin = Join-Path (Join-Path $nodeModules ".bin") $viteExecutable
    $installStamp = Join-Path $nodeModules ".tripplanner-install-stamp"
    if (-not (Test-Path $nodeModules) -or -not (Test-Path $viteBin) -or -not (Test-Path $installStamp)) {
        return $false
    }

    return (Get-Content -Raw -Path $installStamp).Trim() -eq (Get-FrontendDependencyFingerprint -FrontendRoot $FrontendRoot).Trim()
}

function Get-FrontendDependencyFingerprint {
    param(
        [Parameter(Mandatory = $true)][string]$FrontendRoot
    )

    $packageFiles = @(
        (Join-Path $FrontendRoot "package.json"),
        (Join-Path $FrontendRoot "package-lock.json")
    ) | Where-Object { Test-Path $_ }
    if (-not $packageFiles) {
        return ""
    }

    return (($packageFiles | ForEach-Object {
        $hash = Get-FileHash -Algorithm SHA256 -Path $_
        "$([System.IO.Path]::GetFileName($_))=$($hash.Hash)"
    }) -join "`n")
}

function Install-FrontendDependencies {
    param(
        [Parameter(Mandatory = $true)][string]$FrontendRoot,
        [Parameter(Mandatory = $true)][string]$NpmCommand
    )

    Write-Host "Installing frontend dependencies ..." -ForegroundColor Yellow
    Push-Location $FrontendRoot
    try {
        & $NpmCommand install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed in $FrontendRoot."
        }
        $nodeModules = Join-Path $FrontendRoot "node_modules"
        $installStamp = Join-Path $nodeModules ".tripplanner-install-stamp"
        Get-FrontendDependencyFingerprint -FrontendRoot $FrontendRoot | Set-Content -Path $installStamp
    }
    finally {
        Pop-Location
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
    if (-not $NoInspector) {
        Clear-ListeningPort -Port $InspectorPort -Service "Audit Inspector"
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

    # Every emulator-backed start passes through here, primary and sandbox alike,
    # so this is where the place cache meets the central dump: hand over whatever
    # this database fetched since last time, and take the rest if it is empty.
    # Nothing reads the dump at request time -- it is a copy, not a data source.
    $cacheScript = Join-Path $repoRoot "scripts/dev/corpus_cache.py"
    $cacheRelativePython = if ($IsWindows) { ".venv\Scripts\python.exe" } else { ".venv/bin/python" }
    $cachePython = @(
        (Join-Path $repoRoot $cacheRelativePython),
        (Join-Path $sharedRepoRoot $cacheRelativePython)
    ) | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
    if ((Test-Path $cacheScript -PathType Leaf) -and $cachePython) {
        & $cachePython $cacheScript --sync --database $emulatorDatabase
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not sync the place cache; places will be fetched as they are needed."
        }
    }
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
        $env:APP_LOG_PATH = Join-Path (Join-Path (Join-Path $sharedRepoRoot "logs") "diagnostics") "local-app.jsonl"
    }
    Write-Host "  Diagnostics: $env:APP_LOG_PATH" -ForegroundColor DarkGray
    if ($Logs) {
        $env:LOG_LEVEL = "DEBUG"
        Write-Host "  LOG_LEVEL=DEBUG (verbose backend logs)" -ForegroundColor DarkGray
    }
    $pythonRelativePath = if ($IsWindows) { ".venv\Scripts\python.exe" } else { ".venv/bin/python" }
    $py = $null
    $pythonCandidates = @(
        (Join-Path $repoRoot $pythonRelativePath),
        (Join-Path $sharedRepoRoot $pythonRelativePath)
    )
    foreach ($candidate in $pythonCandidates) {
        if (-not (Test-Path $candidate -PathType Leaf)) { continue }
        & $candidate -c "import uvicorn" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $py = $candidate
            break
        }
        Write-Warning "Skipping incomplete Python environment at $candidate (uvicorn is unavailable)."
    }
    if (-not $py) { $py = "python" }
    # src-layout project: make imports work even if pip install -e . was not run.
    $uvicornArgs = @("-m", "uvicorn", "tripplanner.api:app", "--app-dir", "src", "--port", "$ApiPort")
    if ($Watch) { $uvicornArgs += "--reload" }
    $backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory $repoRoot $py -ArgumentList $uvicornArgs
    Wait-BackendReady -Process $backend -Port $ApiPort
}

if (-not $BackendOnly) {
    $frontendRoot = Join-Path $repoRoot "frontend"
    Use-CompatibleNode
    $npmCommand = if ($IsWindows) { "npm.cmd" } else { "npm" }
    if (-not (Test-FrontendDependenciesCurrent -FrontendRoot $frontendRoot)) {
        Install-FrontendDependencies -FrontendRoot $frontendRoot -NpmCommand $npmCommand
    }
    $labs = $null
    if (-not $NoLabs) {
        Write-Host "Starting UX Labs on :$LabsPort ..." -ForegroundColor Cyan
        $env:VITE_LABS_PORT = "$LabsPort"
        $env:VITE_HMR = if ($Watch) { "1" } else { "0" }
        $labs = Start-Process -PassThru -NoNewWindow -WorkingDirectory $frontendRoot `
            -FilePath $npmCommand -ArgumentList @("run", "dev:ux-lab")
        Write-Host "  Labs: http://127.0.0.1:$LabsPort/catalog.html" -ForegroundColor Green
    }

    $inspector = $null
    if (-not $NoInspector) {
        Write-Host "Starting Audit Inspector on :$InspectorPort ..." -ForegroundColor Cyan
        $env:VITE_INSPECTOR_PORT = "$InspectorPort"
        $env:VITE_HMR = if ($Watch) { "1" } else { "0" }
        # Where the inspector's "Open" links send the browser.
        $env:VITE_APP_URL = "http://localhost:$FrontendPort"
        $inspector = Start-Process -PassThru -NoNewWindow -WorkingDirectory $frontendRoot `
            -FilePath $npmCommand -ArgumentList @("run", "dev:inspector")
        Write-Host "  Inspector: http://127.0.0.1:$InspectorPort/" -ForegroundColor Green
    }

    Write-Host "Starting Vite dev server on :$FrontendPort ..." -ForegroundColor Cyan
    Push-Location $frontendRoot
    try {
        $env:VITE_API_TARGET = "http://localhost:$ApiPort"
        $env:VITE_PORT = "$FrontendPort"
        $env:VITE_HMR = if ($Watch) { "1" } else { "0" }
        # Local-only: enables ?inspect=<user_id> so an audit finding can be
        # opened in the real UI. Never set for a production build.
        $env:VITE_DEBUG_TOOLS = "1"
        # Stable guest identity for emulator dev; the sandbox seed re-owns the
        # owner's data under this id (keep in sync with sandbox_seed.py).
        if ($configuredCosmosBackend -eq "emulator") {
            $env:VITE_DEV_GUEST_ID = "web-00000000-0000-4000-8000-000000000001"
        }
        & $npmCommand run dev
        if ($LASTEXITCODE -ne 0) {
            throw "Vite dev server exited with code $LASTEXITCODE."
        }
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
        if ($inspector) {
            try {
                Clear-ListeningPort -Port $InspectorPort -Service "Audit Inspector"
            } catch {
                Write-Warning "Could not stop the inspector cleanly: $($_.Exception.Message)"
            }
            if (-not $inspector.HasExited) {
                Stop-Process -Id $inspector.Id -ErrorAction SilentlyContinue
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
