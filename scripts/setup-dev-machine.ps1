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
    @{ Name = "Python 3.11"; Command = "python"; Package = "Python.Python.3.11" },
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

Write-Host "`nTripplanner developer-machine setup`n"
foreach ($tool in $tools) {
    Install-MissingTool $tool
}

$pythonVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pythonVersion -lt [version]"3.11") {
    throw "Python 3.11 or newer is required; found $pythonVersion."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[created] .env from .env.example; add provider secrets locally."
} else {
    Write-Host "[kept] existing .env"
}

if (-not $SkipDependencyInstall) {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        python -m venv .venv
    }
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements.lock
    & ".venv\Scripts\python.exe" -m pip install -e . --no-deps

    Push-Location frontend
    try { npm ci } finally { Pop-Location }

    if ($IncludeMobile) {
        Push-Location mobile
        try { npm ci } finally { Pop-Location }
    }
}

& ".venv\Scripts\python.exe" -c "import fastapi, tripplanner; print('[ok] Python environment')"
npm --prefix frontend run build

$dockerReady = $false
try {
    docker info *> $null
    $dockerReady = $LASTEXITCODE -eq 0
} catch {
    $dockerReady = $false
}

Write-Host "`nSetup complete."
Write-Host "Local app:       .\scripts\dev-spa.ps1"
Write-Host "Canary release:  .\infra\deploy-canary.ps1"
Write-Host "Prod promotion:  .\infra\deploy-prod.ps1"
Write-Host "Azure access:    run 'az login' before deployment."
Write-Host "GHCR access:     run 'docker login ghcr.io' with a write:packages PAT."
if (-not $dockerReady) {
    Write-Host "Docker Desktop is installed but its daemon is not running; start it before local Cosmos or image builds."
}