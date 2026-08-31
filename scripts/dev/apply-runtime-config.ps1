#!/usr/bin/env pwsh
<#+
.SYNOPSIS
    Compare or apply registered runtime configuration to hosted environments.

.DESCRIPTION
    Provides one owner-facing entry point for safe same-image runtime updates.
    Each registered handler retains ownership of its provider sequencing,
    account allowlists, revision verification, and cloud-side state.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "apply", "help", "?")]
    [string]$Action = "status",

    [Parameter(Position = 1)]
    [ValidateSet("all", "canary", "prod")]
    [string]$Environment = "all",

    [Parameter(Position = 2)]
    [string]$Approval = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path

function Show-RuntimeConfigHelp {
    Write-Host @"
Apply-Runtime-Config - compare or apply hosted runtime configuration.

Usage: Apply-Runtime-Config [status|apply|help|?] [all|canary|prod] [approval]

  status  Compare registered runtime configuration without changing it (default).
  apply   Apply checked-in profiles through same-image revisions.
          Requires APPROVE_RUNTIME_CONFIG.
  help/?  Show this help.

Examples:
  Apply-Runtime-Config
  Apply-Runtime-Config status prod
  Apply-Runtime-Config apply canary APPROVE_RUNTIME_CONFIG
  Apply-Runtime-Config apply all APPROVE_RUNTIME_CONFIG

No image is built or changed and no Bicep deployment is run. A handler may
coordinate external provider state when its registered settings require it.
"@
}

if ($Action -in @("help", "?")) {
    Show-RuntimeConfigHelp
    exit 0
}
if ($Action -eq "apply" -and $Approval -cne "APPROVE_RUNTIME_CONFIG") {
    throw "Applying hosted runtime configuration requires APPROVE_RUNTIME_CONFIG."
}

# Add future runtime configuration owners here. Handlers retain specialized
# sequencing and safety checks; this script owns only orchestration.
$handlers = @(
    [pscustomobject]@{
        Name = "Google Maps and Places"
        Script = Join-Path $repoRoot "infra/azure/set-google-runtime-access.ps1"
        Arguments = if ($Action -eq "apply") {
            @("apply", $Environment, "APPROVE_GOOGLE_MAPS_SPEND", "APPROVE_GOOGLE_PLACES_SPEND")
        } else {
            @("status", $Environment)
        }
    }
)

Write-Host "Tripplanner runtime configuration"
Write-Host "  action      : $Action"
Write-Host "  environment : $Environment"
Write-Host "  handlers    : $($handlers.Name -join ', ')"
Write-Host ""

$failures = @()
foreach ($handler in $handlers) {
    Write-Host "[$($handler.Name)]" -ForegroundColor Cyan
    try {
        $handlerArguments = @($handler.Arguments)
        & $handler.Script @handlerArguments
        if ($LASTEXITCODE -ne 0) {
            throw "exited with code $LASTEXITCODE"
        }
    } catch {
        $failures += "$($handler.Name): $($_.Exception.Message)"
        Write-Error $failures[-1] -ErrorAction Continue
    }
    Write-Host ""
}

if ($failures.Count -gt 0) {
    throw "$($failures.Count) runtime configuration handler(s) failed:`n  $($failures -join "`n  ")"
}

if ($Action -eq "status") {
    Write-Host "Runtime configuration status completed successfully." -ForegroundColor Green
} else {
    Write-Host "Runtime configuration applied successfully." -ForegroundColor Green
}