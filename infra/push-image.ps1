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

  The image is built from a clean export of one commit (-Commit, default HEAD),
  never from the live checkout. The primary checkout is fast-forwarded by other
  sessions while a deploy runs, so a live-tree build could carry code from a
  different commit than the SHA tag names; uncommitted edits are excluded too.

    Auth: GHCR_TOKEN, CR_PAT, GITHUB_TOKEN, the GitHub CLI token, and Docker's
    stored ghcr.io credential are tried in that order. Each is verified with
    GitHub to belong to the publisher and carry `write:packages` before the
    build starts; a public package's readable manifest is not proof of push.

.EXAMPLE
  ./infra/push-image.ps1
  ./infra/push-image.ps1 -Tag v2          # also tag :v2 alongside :latest
  ./infra/push-image.ps1 -SkipLatest      # push only the SHA tag
  ./infra/push-image.ps1 -Commit d5cded67 # build that commit, not HEAD
#>

param(
    [string]$Tag = "",
    [string]$Commit = "HEAD",
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

# Resolve the commit once; every later step uses this SHA, not HEAD.
$commitSha = (git rev-parse --verify --quiet "$Commit^{commit}" 2>$null)
if ([string]::IsNullOrWhiteSpace($commitSha)) {
    throw "Could not resolve '$Commit' to a Git commit for the immutable image tag."
}
$sha = (git rev-parse --short $commitSha)

$repo = "$Registry/$Image"
$tags = @("$repo`:$sha")
if (-not $SkipLatest) { $tags += "$repo`:latest" }
if (-not [string]::IsNullOrWhiteSpace($Tag)) { $tags += "$repo`:$Tag" }
$tags = @($tags | Select-Object -Unique)

Write-Host "Image:    $repo"
Write-Host "Commit:   $commitSha"
Write-Host "Tags:     $($tags -join ', ')`n"

# Ensure Docker is available.
docker --version *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker is not available. Start Docker Desktop and retry." }

# Establish a verified GHCR session before building, so a missing or stale
# credential fails in seconds instead of after the build.
$credential = Resolve-GhcrPublishCredential -Registry $Registry -User $GhcrUser
Write-Host "✓ Logging in to $Registry as $GhcrUser using $($credential.Source) ..."
$credential.Token | docker login $Registry --username $GhcrUser --password-stdin
$loginExitCode = $LASTEXITCODE
$credential = $null
if ($loginExitCode -ne 0) {
    throw "docker login to $Registry failed. Refresh the token's write:packages access and retry."
}
Write-Host "  ✓ Logged in`n"

$headSha = (git rev-parse HEAD 2>$null)
if ($headSha -eq $commitSha -and -not [string]::IsNullOrWhiteSpace((git status --porcelain --untracked-files=no | Out-String))) {
    Write-Host -ForegroundColor Yellow "ℹ Uncommitted changes are not part of the image; it contains $sha exactly.`n"
}

# Build with all tags from a clean export of the commit. Azure Container Apps
# runs linux/amd64, including when the publisher is on Apple Silicon.
Write-Host "✓ Building image ..."
$buildTimer = [System.Diagnostics.Stopwatch]::StartNew()
$contextRoot = Join-Path ([System.IO.Path]::GetTempPath()) "tripplanner-image-$sha-$PID"
$contextArchive = "$contextRoot.tar"
try {
    git archive --format=tar -o $contextArchive $commitSha
    if ($LASTEXITCODE -ne 0) { throw "git archive failed for $commitSha." }
    New-Item -ItemType Directory -Force -Path $contextRoot | Out-Null
    tar -xf $contextArchive -C $contextRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not extract the build context for $commitSha." }

    $buildArgs = @("build", "--platform", "linux/amd64")
    foreach ($t in $tags) { $buildArgs += @("-t", $t) }
    $buildArgs += $contextRoot
    Invoke-LoggedNative -FilePath "docker" -ArgumentList $buildArgs -FailureMessage "docker build failed."
} finally {
    Remove-Item -Recurse -Force -LiteralPath $contextRoot, $contextArchive -ErrorAction SilentlyContinue
}
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
