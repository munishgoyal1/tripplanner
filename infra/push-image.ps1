#!/usr/bin/env pwsh
<#
.SYNOPSIS
  One-click: build the container image and push it to GHCR.

.DESCRIPTION
  Builds the Docker image from the repo root and pushes it to
  ghcr.io/munishgoyal1/tripplanner tagged with BOTH the current git short SHA
  (immutable, traceable) and `latest` (what the canary/prod deploy scripts
  pull by default).

  Image push is intentionally MANUAL — the GitHub Actions workflow no longer
  builds on every commit, so the local loop stays fast. Run this only when you
  actually want to ship a new image.

  Auth: needs a `docker login ghcr.io` session. If you're not logged in, set a
  GitHub PAT (with `write:packages`) in one of these env vars and this script
  will log in for you: GHCR_TOKEN, CR_PAT, or GITHUB_TOKEN.

.EXAMPLE
  ./infra/push-image.ps1
  ./infra/push-image.ps1 -Tag v2          # also tag :v2 alongside :latest
  ./infra/push-image.ps1 -SkipLatest      # push only the SHA tag
#>

param(
    [string]$Tag = "",
    [string]$Registry = "ghcr.io",
    [string]$Image = "munishgoyal1/tripplanner",
    [string]$GhcrUser = "munishgoyal1",
    [switch]$SkipLatest = $false
)

$ErrorActionPreference = "Stop"

# Always run from the repo root (one level up from infra/).
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "`n╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  📦 BUILD & PUSH IMAGE → GHCR                            ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"

# Resolve the git short SHA for an immutable tag.
$sha = (git rev-parse --short HEAD 2>$null)
if ([string]::IsNullOrWhiteSpace($sha)) { $sha = "manual" }

$repo = "$Registry/$Image"
$tags = @("$repo`:$sha")
if (-not $SkipLatest) { $tags += "$repo`:latest" }
if (-not [string]::IsNullOrWhiteSpace($Tag)) { $tags += "$repo`:$Tag" }
$tags = @($tags | Select-Object -Unique)

Write-Host "Image:    $repo"
Write-Host "Tags:     $($tags -join ', ')`n"

# Ensure Docker is available.
docker --version *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker is not available. Start Docker Desktop and retry." }

# Log in to GHCR if a token is provided; otherwise assume an existing session.
$token = $env:GHCR_TOKEN
if ([string]::IsNullOrWhiteSpace($token)) { $token = $env:CR_PAT }
if ([string]::IsNullOrWhiteSpace($token)) { $token = $env:GITHUB_TOKEN }
if (-not [string]::IsNullOrWhiteSpace($token)) {
    Write-Host "✓ Logging in to $Registry as $GhcrUser ..."
    $token | docker login $Registry --username $GhcrUser --password-stdin
    if ($LASTEXITCODE -ne 0) { throw "docker login to $Registry failed." }
    Write-Host "  ✓ Logged in`n"
} else {
    Write-Host "ℹ No GHCR_TOKEN/CR_PAT/GITHUB_TOKEN set — assuming an existing"
    Write-Host "  'docker login $Registry' session. If push fails with auth, set a"
    Write-Host "  PAT in GHCR_TOKEN and retry.`n"
}

# Build with all tags.
Write-Host "✓ Building image ..."
$buildArgs = @("build")
foreach ($t in $tags) { $buildArgs += @("-t", $t) }
$buildArgs += "."
docker @buildArgs
if ($LASTEXITCODE -ne 0) { throw "docker build failed." }
Write-Host "  ✓ Built`n"

# Push every tag.
Write-Host "✓ Pushing image ..."
foreach ($t in $tags) {
    docker push $t
    if ($LASTEXITCODE -ne 0) { throw "docker push failed for $t" }
}
Write-Host "  ✓ Pushed`n"

# Log it.
. "$PSScriptRoot/../scripts/dev/lib/run-log.ps1"
$historyLog = Join-Path (Get-PrimaryRepoRoot) "logs/image-pushes.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $historyLog) | Out-Null
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content $historyLog "[$timestamp] Pushed $($tags -join ', ') | By: $env:USERNAME"

Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ✓ IMAGE PUSHED                                          ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"
Write-Host "Next: ./infra/deploy-canary.ps1 -NoBuild -ImageTag $sha`n"
