#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Prepare a Windows machine for local development and Azure releases.

.DESCRIPTION
  Installs missing prerequisites with winget, creates the Python environment,
  restores web dependencies, and reports authentication still required for
    canary or production. Full agent mode applies the portable VS Code and Copilot
    configuration. It never starts servers, logs in, or overwrites .env.
#>

[CmdletBinding()]
param(
    [switch]$SkipToolInstall,
    [switch]$IncludeMobile,
    [switch]$SkipDependencyInstall,
    [switch]$FullAgentEnvironment,
    [switch]$OpenAgentWindows
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$pipIndexUrl = if ($env:PIP_INDEX_URL) { $env:PIP_INDEX_URL } else { "https://pypi.org/simple" }
$npmRegistryUrl = if ($env:NPM_CONFIG_REGISTRY) { $env:NPM_CONFIG_REGISTRY } else { "https://registry.npmjs.org/" }

function Assert-IndependentPackageSource {
    param(
        [string]$SourceName,
        [string]$SourceUrl
    )

    if ($SourceUrl -match "(?i)(pkgs\.visualstudio\.com|1es-public)") {
        throw "$SourceName must not use Microsoft corporate package infrastructure: $SourceUrl"
    }
}

Assert-IndependentPackageSource "PIP_INDEX_URL" $pipIndexUrl
Assert-IndependentPackageSource "NPM_CONFIG_REGISTRY" $npmRegistryUrl

$tools = @(
    @{ Name = "Git"; Command = "git"; Package = "Git.Git" },
    @{ Name = "Node.js LTS"; Command = "node"; Package = "OpenJS.NodeJS.LTS" },
    @{ Name = "Docker Desktop"; Command = "docker"; Package = "Docker.DockerDesktop" },
    @{ Name = "Azure CLI"; Command = "az"; Package = "Microsoft.AzureCLI" }
)
if ($FullAgentEnvironment) {
    $tools += @(
        @{ Name = "Visual Studio Code"; Command = "code"; Package = "Microsoft.VisualStudioCode" },
        @{ Name = "PowerShell"; Command = "pwsh"; Package = "Microsoft.PowerShell" },
        @{ Name = "GitHub CLI"; Command = "gh"; Package = "GitHub.cli" }
    )
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $separator = [IO.Path]::PathSeparator
    $env:Path = @($machinePath, $userPath, $env:Path) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique |
        Join-String -Separator $separator
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
    if (-not $IsWindows) {
        throw "$($Tool.Name) is missing. Install it with Homebrew or the vendor installer, then rerun."
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

if ($FullAgentEnvironment) {
    & (Join-Path (Join-Path $repoRoot "devconfigs") "Apply-DevConfigs.ps1") -InstallExtensions
    Write-Host "[ok] Portable VS Code and Copilot configuration applied"

    if (-not (Get-Command copilot -ErrorAction SilentlyContinue)) {
        Write-Host "[install] GitHub Copilot CLI"
        npm install --global @github/copilot --registry=$npmRegistryUrl
        Assert-LastCommandSucceeded "GitHub Copilot CLI install"
    } else {
        Write-Host "[ok] GitHub Copilot CLI"
    }
}

# Safe, self-healing merges for parallel worktree development: record and replay
# conflict resolutions (rerere) and show the common ancestor in every conflict.
& git -C $repoRoot config rerere.enabled true
& git -C $repoRoot config rerere.autoupdate true
& git -C $repoRoot config merge.conflictstyle zdiff3
Write-Host "[ok] Git configured for rerere + zdiff3 conflict style"

function Resolve-Python313 {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $resolved = & py -3.13 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            return $resolved.Trim()
        }
    }
    foreach ($candidate in @("python3.13", "python3", "python")) {
        if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
        $resolved = & $candidate -c "import sys; ok = sys.version_info[:2] == (3, 13); print(sys.executable) if ok else None; raise SystemExit(0 if ok else 1)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            return $resolved.Trim()
        }
    }

    if ($SkipToolInstall) {
        throw "Python 3.13 is required but was not found. Install it with 'winget install --id Python.Python.3.13 --exact', then rerun."
    }
    if (-not $IsWindows) {
        throw "Python 3.13 is required but was not found. Install it with Homebrew or python.org, then rerun."
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
    $venvPython = if ($IsWindows) { Join-Path (Join-Path ".venv" "Scripts") "python.exe" } else { Join-Path (Join-Path ".venv" "bin") "python" }
    if (Test-Path $venvPython) {
        $venvVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($venvVersion -ne "3.13") {
            Write-Host "[recreate] .venv uses Python $venvVersion; Python 3.13 is required"
            Remove-Item ".venv" -Recurse -Force
        }
    }
    if (-not (Test-Path $venvPython)) {
        & $python313 -m venv .venv
    }
    & $venvPython -m pip install --index-url $pipIndexUrl --upgrade pip
    Assert-LastCommandSucceeded "pip upgrade"
    & $venvPython -m pip install --index-url $pipIndexUrl -r requirements.lock
    Assert-LastCommandSucceeded "locked Python dependency install"
    & $venvPython -m pip install --index-url $pipIndexUrl -e . --no-deps
    Assert-LastCommandSucceeded "editable package install"

    Push-Location frontend
    try {
        npm ci --registry=$npmRegistryUrl
        Assert-LastCommandSucceeded "frontend dependency install"
    } finally {
        Pop-Location
    }

    if ($IncludeMobile) {
        Push-Location mobile
        try {
            npm ci --registry=$npmRegistryUrl
            Assert-LastCommandSucceeded "mobile dependency install"
        } finally {
            Pop-Location
        }
    }
}

$venvPython = if ($IsWindows) { Join-Path (Join-Path ".venv" "Scripts") "python.exe" } else { Join-Path (Join-Path ".venv" "bin") "python" }
& $venvPython -c "import fastapi, tripplanner; print('[ok] Python environment')"
Assert-LastCommandSucceeded "Python environment verification"
npm --prefix frontend run build
Assert-LastCommandSucceeded "frontend production build"

if ($FullAgentEnvironment -and $OpenAgentWindows) {
    & code --new-window $repoRoot
}

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
if ($FullAgentEnvironment) {
    Write-Host "GitHub access:   run 'gh auth login' and sign into GitHub in VS Code."
    Write-Host '.\scripts\sandbox\New-Sandbox.cmd <name> "<purpose>"'
}
if (-not $dockerReady) {
    Write-Host "Docker Desktop is installed but its daemon is not running; start it before local Cosmos or image builds."
}