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

    Auth: set a GitHub PAT (with `write:packages`) in GHCR_TOKEN, CR_PAT, or
    GITHUB_TOKEN. If none is set, an authenticated Docker credential is verified
    against GHCR and reused. An eligible GitHub CLI token is also supported.

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
$totalTimer = [System.Diagnostics.Stopwatch]::StartNew()

. "$PSScriptRoot/../scripts/dev/lib/run-log.ps1"
. "$PSScriptRoot/deployment-common.ps1"
Start-RunLog -Name "push-image" | Out-Null

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

# Always establish a fresh GHCR session before building. A cached Docker credential
# can be expired while still appearing present and would fail only after the build.
$token = $null
$tokenSource = $null
if (-not [string]::IsNullOrWhiteSpace($env:GHCR_TOKEN)) {
    $token = $env:GHCR_TOKEN
    $tokenSource = "GHCR_TOKEN"
} elseif (-not [string]::IsNullOrWhiteSpace($env:CR_PAT)) {
    $token = $env:CR_PAT
    $tokenSource = "CR_PAT"
} elseif (-not [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
    $token = $env:GITHUB_TOKEN
    $tokenSource = "GITHUB_TOKEN"
}

if ([string]::IsNullOrWhiteSpace($token) -and (Get-Command gh -ErrorAction SilentlyContinue)) {
    $ghLogin = (& gh api user --jq .login 2>$null | Out-String).Trim()
    $loginExitCode = $LASTEXITCODE
    $ghHeaders = (& gh api --include user 2>$null | Out-String)
    $headersExitCode = $LASTEXITCODE
    $scopeMatch = [regex]::Match($ghHeaders, '(?im)^x-oauth-scopes:\s*(.+)$')
    $ghScopes = if ($scopeMatch.Success) {
        @($scopeMatch.Groups[1].Value.Split(',') | ForEach-Object { $_.Trim() })
    } else {
        @()
    }

    if ($loginExitCode -eq 0 -and $headersExitCode -eq 0 -and
        $ghLogin -eq $GhcrUser -and $ghScopes -contains "write:packages") {
        $token = (& gh auth token --hostname github.com 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($token)) {
            $tokenSource = "GitHub CLI"
        }
    }
}

if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "ℹ No token variable or eligible GitHub CLI token found. Verifying the existing Docker credential ..."
    docker manifest inspect "$repo`:latest" *> $null
    if ($LASTEXITCODE -eq 0) {
        $tokenSource = "Docker credential store"
        Write-Host "  ✓ Existing Docker credential authenticated to $Registry`n"
    } else {
        $remedy = "Set GHCR_TOKEN to a GitHub PAT with write:packages, run " +
            "'gh auth refresh -h github.com -s write:packages', or run " +
            "'docker login $Registry' and retry."
        throw "No valid GHCR publish token is available. $remedy"
    }
}

if (-not [string]::IsNullOrWhiteSpace($token)) {
    Write-Host "✓ Logging in to $Registry as $GhcrUser using $tokenSource ..."
    $token | docker login $Registry --username $GhcrUser --password-stdin
    $token = $null
    if ($LASTEXITCODE -ne 0) {
        throw "docker login to $Registry failed. Refresh the token's write:packages access and retry."
    }
    Write-Host "  ✓ Logged in`n"
}

# Build with all tags. Azure Container Apps runs linux/amd64, including when
# the publisher is running Docker Desktop on Apple Silicon.
Write-Host "✓ Building image ..."
$buildTimer = [System.Diagnostics.Stopwatch]::StartNew()
$buildArgs = @("build", "--platform", "linux/amd64")
foreach ($t in $tags) { $buildArgs += @("-t", $t) }
$buildArgs += "."
Invoke-LoggedNative -FilePath "docker" -ArgumentList $buildArgs -FailureMessage "docker build failed."
$buildTimer.Stop()
$imageDetails = docker image inspect $tags[0] --format '{{json .}}' | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $null -eq $imageDetails) {
    throw "Could not inspect the built image."
}
$imageBytes = [int64]$imageDetails.Size
$imageMiB = [math]::Round($imageBytes / 1MB, 1)
$buildSeconds = [math]::Round($buildTimer.Elapsed.TotalSeconds, 1)
Write-Host "  ✓ Built in ${buildSeconds}s | ${imageMiB} MiB uncompressed | $($imageDetails.Id)`n"

# Push every tag.
Write-Host "✓ Pushing image ..."
$pushTimings = @()
foreach ($t in $tags) {
    $pushTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Invoke-LoggedNative -FilePath "docker" -ArgumentList @("push", $t) -FailureMessage "docker push failed for $t"
    $pushTimer.Stop()
    $pushSeconds = [math]::Round($pushTimer.Elapsed.TotalSeconds, 1)
    $pushTimings += "${t}=${pushSeconds}s"
    Write-Host "  ✓ $t in ${pushSeconds}s"
}
$totalTimer.Stop()
$totalSeconds = [math]::Round($totalTimer.Elapsed.TotalSeconds, 1)
Write-Host "  ✓ Pushed | total workflow ${totalSeconds}s`n"

# Log it.
$historyLog = Join-Path (Get-PrimaryRepoRoot) "logs/image-pushes.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $historyLog) | Out-Null
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$metrics = "Build: ${buildSeconds}s | Push: $($pushTimings -join ', ') | Total: ${totalSeconds}s | Size: $imageBytes bytes | Image ID: $($imageDetails.Id)"
Add-Content $historyLog "[$timestamp] Pushed $($tags -join ', ') | $metrics | By: $(Get-DeploymentUser)"

Write-Host "╔═══════════════════════════════════════════════════════════╗"
Write-Host "║  ✓ IMAGE PUSHED                                          ║"
Write-Host "╚═══════════════════════════════════════════════════════════╝`n"
Write-Host "Next: ./infra/deploy-canary.ps1 -NoBuild -ImageTag $sha`n"
Stop-RunLog
