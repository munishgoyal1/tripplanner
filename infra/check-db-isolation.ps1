#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

Write-Output "LOCAL Cosmos:"
az cosmosdb list -g rg-tripplanner-local --query "[].name" -o tsv
Write-Output ""
Write-Output "CANARY Cosmos:"
az cosmosdb list -g rg-tripplanner-canary --query "[].name" -o tsv
