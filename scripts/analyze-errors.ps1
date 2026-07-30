#!/usr/bin/env pwsh
param(
    [ValidateSet("local", "canary")]
    [string]$Environment = "local",
    [int]$Hours = 24,
    [string]$LogPath = "logs/diagnostics/local-app.jsonl",
    [string]$ReportPath = "",
    [string]$WorkspaceId = ""
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$arguments = @(
    (Join-Path $PSScriptRoot "analyze_errors.py"),
    $Environment,
    "--hours", $Hours,
    "--log-path", $LogPath
)
if (-not [string]::IsNullOrWhiteSpace($ReportPath)) {
    $arguments += @("--report-path", $ReportPath)
}
if (-not [string]::IsNullOrWhiteSpace($WorkspaceId)) {
    $arguments += @("--workspace-id", $WorkspaceId)
}

& $python @arguments
exit $LASTEXITCODE