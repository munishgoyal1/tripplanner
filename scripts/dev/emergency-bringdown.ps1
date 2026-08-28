#!/usr/bin/env pwsh
<#+
.SYNOPSIS
    Stop, restore, or report all hosted Tripplanner serving.

.DESCRIPTION
    Controls only canary and production Container Apps and recurring jobs. Down
    is immediate and reversible. Up requires explicit spend approval. Provider
    access, databases, resources, DNS, domains, and data are not changed.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "down", "up", "stop", "start")]
    [string]$Action = "status",

    [Parameter(Position = 1)]
    [ValidateSet("all", "canary", "prod")]
    [string]$Target = "all",

    [Parameter(Position = 2)]
    [string]$Approval = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$azureControl = Join-Path $repoRoot "infra/azure/set-azure-services-access.ps1"
$normalizedAction = @{
    down = "disable"
    stop = "disable"
    up = "enable"
    start = "enable"
}[$Action]
if (-not $normalizedAction) { $normalizedAction = $Action }

if ($normalizedAction -eq "enable" -and $Approval -cne "APPROVE_AZURE_SPEND") {
    throw "Restoring hosted serving permits paid Azure usage. Pass APPROVE_AZURE_SPEND as the third argument."
}

& $azureControl $normalizedAction $Target $Approval -ServingOnly
if ($LASTEXITCODE -ne 0) {
    throw "Azure hosted serving control exited with code $LASTEXITCODE."
}
