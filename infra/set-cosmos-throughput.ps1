#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory)]
    [string]$ResourceGroup,
    [Parameter(Mandatory)]
    [string]$AccountName,
    [string]$DatabaseName = "tripplanner",
    [int]$Throughput = 400,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ($Throughput -ne 400) {
    throw "This cost-reduction helper only permits the 400 RU/s fixed minimum."
}

$current = az cosmosdb sql database throughput show `
    -g $ResourceGroup `
    -a $AccountName `
    -n $DatabaseName `
    --query resource.throughput `
    -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($current)) {
    throw "Could not read throughput for $ResourceGroup/$AccountName/$DatabaseName."
}

Write-Host "Current throughput: $current RU/s"
Write-Host "Target throughput:  $Throughput RU/s"
if ($DryRun -or [int]$current -eq $Throughput) {
    exit 0
}

$approval = Read-Host "Type APPROVE_COSMOS_400_RU to update this exact database"
if ($approval -cne "APPROVE_COSMOS_400_RU") {
    throw "Throughput approval denied."
}

az cosmosdb sql database throughput update `
    -g $ResourceGroup `
    -a $AccountName `
    -n $DatabaseName `
    --throughput $Throughput `
    -o none
if ($LASTEXITCODE -ne 0) {
    throw "Throughput update failed."
}

$updated = az cosmosdb sql database throughput show `
    -g $ResourceGroup `
    -a $AccountName `
    -n $DatabaseName `
    --query resource.throughput `
    -o tsv
if ([int]$updated -ne $Throughput) {
    throw "Throughput verification failed: expected $Throughput, got $updated."
}
Write-Host "Verified $ResourceGroup/$AccountName/$DatabaseName at $updated RU/s." -ForegroundColor Green