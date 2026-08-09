#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("canary", "production")]
    [string]$Environment,
    [string]$BaseUrl = "",
    [string]$ExpectedOAuthCallback = "",
    [switch]$Deep = $false,
    [switch]$AllowProductionWrites = $false,
    [string]$SubscriptionId = ""
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot/deployment-common.ps1"

if ($Deep -and $Environment -eq "production" -and -not $AllowProductionWrites) {
    throw "Deep production smoke creates an isolated chat turn. Pass -AllowProductionWrites explicitly."
}

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    az account set --subscription $SubscriptionId
}

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    $resourceGroup = if ($Environment -eq "canary") { "rg-tripplanner-canary" } else { "rg-tripplanner-prod" }
    $prefix = if ($Environment -eq "canary") { "canary" } else { "prod" }
    $fqdns = @(az containerapp list `
        --resource-group $resourceGroup `
        --query "[?starts_with(name, '${prefix}-app-')].properties.configuration.ingress.fqdn" `
        --output tsv)
    if ($fqdns.Count -ne 1) {
        throw "Expected one ${prefix}-app-* Container App in $resourceGroup; found $($fqdns.Count)."
    }
    $BaseUrl = "https://$($fqdns[0])"
}

if ([string]::IsNullOrWhiteSpace($ExpectedOAuthCallback)) {
    $ExpectedOAuthCallback = if ($Environment -eq "production") {
        "https://aitripplanner.co/api/auth/callback/google"
    } else {
        "$($BaseUrl.TrimEnd('/'))/api/auth/callback/google"
    }
}

$pythonCandidates = @(
    (Join-Path (Join-Path ".venv" "Scripts") "python.exe"),
    (Join-Path (Join-Path ".venv" "bin") "python"),
    "python3",
    "python"
)
$python = $pythonCandidates | Where-Object {
    if ($_ -match "[\\/]") { Test-Path $_ -PathType Leaf } else { Get-Command $_ -ErrorAction SilentlyContinue }
} | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($python)) {
    throw "Python is required to run hosted smoke tests."
}
$arguments = @(
    "scripts/hosted_smoke.py",
    "--environment", $Environment,
    "--base-url", $BaseUrl,
    "--expected-oauth-callback", $ExpectedOAuthCallback
)
if ($Deep) { $arguments += "--deep" }

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Hosted smoke tests failed for $Environment."
}