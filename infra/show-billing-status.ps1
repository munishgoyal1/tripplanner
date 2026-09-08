#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Show month-to-date spend against the configured budgets on both clouds.

.DESCRIPTION
  Read-only. Run this before editing limits in infra/billing-guardrails.json so
  the new numbers are chosen against real consumption rather than guesses.

.EXAMPLE
  ./infra/show-billing-status.ps1

.EXAMPLE
  ./infra/show-billing-status.ps1 -Cloud azure
#>

param(
    [string]$ConfigPath = "$PSScriptRoot/billing-guardrails.json",
    [ValidateSet("all", "gcp", "azure")]
    [string]$Cloud = "all"
)

$ErrorActionPreference = "Stop"
$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json

if ($Cloud -in @("all", "azure")) {
    Write-Host "=== Azure ($($config.azure.currency)) ==="
    $subscription = $config.azure.subscriptionId

    $query = [ordered]@{
        type      = "ActualCost"
        timeframe = "MonthToDate"
        dataset   = [ordered]@{
            granularity = "None"
            aggregation = [ordered]@{ totalCost = [ordered]@{ name = "Cost"; function = "Sum" } }
            grouping    = @(
                [ordered]@{ type = "Dimension"; name = "ResourceGroupName" },
                [ordered]@{ type = "Dimension"; name = "ServiceName" }
            )
        }
    } | ConvertTo-Json -Depth 10

    $file = Join-Path ([System.IO.Path]::GetTempPath()) "tp-cost-query.json"
    $query | Set-Content -Path $file -Encoding utf8

    $rawRows = az rest --method post `
        --url "https://management.azure.com/subscriptions/$subscription/providers/Microsoft.CostManagement/query?api-version=2023-11-01" `
        --body "@$file" --headers "Content-Type=application/json" `
        --query "properties.rows" -o json
    $azExitCode = $LASTEXITCODE
    Remove-Item $file -ErrorAction SilentlyContinue
    if ($azExitCode -ne 0) {
        throw "Azure Cost Management query failed. Wait briefly if Azure returned HTTP 429, then rerun the status script."
    }
    $rows = $rawRows | ConvertFrom-Json

    $byGroup = $rows | Group-Object { $_[1] } | Sort-Object { -($_.Group | ForEach-Object { $_[0] } | Measure-Object -Sum).Sum }
    foreach ($group in $byGroup) {
        $total = ($group.Group | ForEach-Object { $_[0] } | Measure-Object -Sum).Sum
        $budget = ($config.azure.environments | Where-Object { $_.resourceGroup -eq $group.Name }).budget
        $suffix = if ($budget) { "of $budget  ({0:N0}%)" -f (100 * $total / $budget) } else { "(no per-environment budget)" }
        Write-Host ("  {0,-24} {1,10:N2} {2}" -f $group.Name, $total, $suffix)
        foreach ($row in ($group.Group | Sort-Object { -$_[0] })) {
            Write-Host ("      {0,-22} {1,10:N2}" -f $row[2], $row[0])
        }
    }
    $grand = ($rows | ForEach-Object { $_[0] } | Measure-Object -Sum).Sum
    $globalBudget = $config.azure.globalBudget.amount
    Write-Host ("  {0,-24} {1,10:N2} of {2}  ({3:N0}%)" -f "SUBSCRIPTION TOTAL", $grand, $globalBudget, (100 * $grand / $globalBudget))
    Write-Host ""
}

if ($Cloud -in @("all", "gcp")) {
    Write-Host "=== Google Cloud ($($config.gcp.currency)) ==="
    Write-Host "  Budgets are reported by Cloud Billing with a lag of several hours."
    & gcloud billing budgets list --billing-account=$($config.gcp.billingAccount) `
        --format="table(displayName, amount.specifiedAmount.units:label=AMOUNT, budgetFilter.projects.list():label=SCOPE)" 2>&1 |
        ForEach-Object { Write-Host "  $_" }
    Write-Host ""
    Write-Host "  Per-API consumption is not available from the CLI; use the Cloud Console"
    Write-Host "  quota pages or the billing report for call-level detail."
}
