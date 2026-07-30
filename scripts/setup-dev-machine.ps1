#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Prepare a Windows machine for local development and Azure releases.

.DESCRIPTION
  Installs missing prerequisites with winget, creates the Python environment,
  restores web dependencies, and reports authentication still required for
  canary or production. It never starts servers, logs in, or overwrites .env.
#>

[CmdletBinding()]
param(
    [switch]$SkipToolInstall,
    [switch]$IncludeMobile,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$tools = @(
    @{ Name = "Git"; Command = "git"; Package = "Git.Git" },
    @{ Name = "Node.js LTS"; Command = "node"; Package = "OpenJS.NodeJS.LTS" },
    @{ Name = "Docker Desktop"; Command = "docker"; Package = "Docker.DockerDesktop" },
    @{ Name = "Azure CLI"; Command = "az"; Package = "Microsoft.AzureCLI" }
)

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Install-MissingTool {
    param([hashtable]$Tool)

    if (Get-Command $Tool.Command -ErrorAction SilentlyContinue) {
        Write-Host "[ok] $($Tool.Name)"
        return
    }
    if ($SkipToolInstall) {
        throw "$($Tool.Name) is missing and -SkipToolInstall was supplied."
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "$($Tool.Name) is missing and winget is unavailable. Install App Installer, then rerun."
    }

    Write-Host "[install] $($Tool.Name)"
    winget install --id $Tool.Package --exact --accept-package-agreements `
        --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $($Tool.Name)."
    }
    Refresh-ProcessPath
    if (-not (Get-Command $Tool.Command -ErrorAction SilentlyContinue)) {
        throw "$($Tool.Name) installed but is not available in this process. Restart PowerShell and rerun."
    }
}

function Assert-LastCommandSucceeded {
    param([string]$Description)

    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

Write-Host "`nTripplanner developer-machine setup`n"
foreach ($tool in $tools) {
    Install-MissingTool $tool
}

function Resolve-Python313 {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $resolved = & py -3.13 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            return $resolved.Trim()
        }
    }

    if ($SkipToolInstall) {
        throw "Python 3.13 is required but was not found. Install it with 'winget install --id Python.Python.3.13 --exact', then rerun."
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python 3.13 is required and winget is unavailable. Install Python 3.13, then rerun."
    }

    Write-Host "[install] Python 3.13"
    winget install --id Python.Python.3.13 --exact --accept-package-agreements `
        --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install Python 3.13."
    }
    Refresh-ProcessPath

    $resolved = & py -3.13 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $resolved) {
        throw "Python 3.13 installed but the Python launcher cannot resolve it. Restart PowerShell and rerun."
    }
    return $resolved.Trim()
}

$python313 = Resolve-Python313
Write-Host "[ok] Python 3.13 ($python313)"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[created] .env from .env.example; add provider secrets locally."
} else {
    Write-Host "[kept] existing .env"
}

if (-not $SkipDependencyInstall) {
    if (Test-Path ".venv\Scripts\python.exe") {
        $venvVersion = & ".venv\Scripts\python.exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($venvVersion -ne "3.13") {
            Write-Host "[recreate] .venv uses Python $venvVersion; Python 3.13 is required"
            Remove-Item ".venv" -Recurse -Force
        }
    }
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        & $python313 -m venv .venv
    }
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    Assert-LastCommandSucceeded "pip upgrade"
    & ".venv\Scripts\python.exe" -m pip install -r requirements.lock
    Assert-LastCommandSucceeded "locked Python dependency install"
    & ".venv\Scripts\python.exe" -m pip install -e . --no-deps
    Assert-LastCommandSucceeded "editable package install"

    Push-Location frontend
    try {
        npm ci
        Assert-LastCommandSucceeded "frontend dependency install"
    } finally {
        Pop-Location
    }

    if ($IncludeMobile) {
        Push-Location mobile
        try {
            npm ci
            Assert-LastCommandSucceeded "mobile dependency install"
        } finally {
            Pop-Location
        }
    }
}

& ".venv\Scripts\python.exe" -c "import fastapi, tripplanner; print('[ok] Python environment')"
Assert-LastCommandSucceeded "Python environment verification"
npm --prefix frontend run build
Assert-LastCommandSucceeded "frontend production build"

$dockerReady = $false
try {
    docker info *> $null
    $dockerReady = $LASTEXITCODE -eq 0
} catch {
    $dockerReady = $false
}

Write-Host "`nSetup complete."
Write-Host "Local app:       .\scripts\dev\dev-spa.ps1"
Write-Host "Canary release:  .\infra\deploy-canary.ps1"
Write-Host "Prod promotion:  .\infra\deploy-prod.ps1"
Write-Host "Azure access:    run 'az login' before deployment."
Write-Host "GHCR access:     run 'docker login ghcr.io' with a write:packages PAT."
if (-not $dockerReady) {
    Write-Host "Docker Desktop is installed but its daemon is not running; start it before local Cosmos or image builds."
}