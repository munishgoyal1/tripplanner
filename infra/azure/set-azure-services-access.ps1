#!/usr/bin/env pwsh
<#+
.SYNOPSIS
  Report, disable, or enable the Tripplanner Azure estate as one unit.

.DESCRIPTION
  Discovers supported resources only in the resource groups configured in
  infra/billing-guardrails.json. Disable stops Container Apps, makes recurring
  Container Apps Jobs manual, stops active job executions, and blocks public
  access to Azure OpenAI, Cosmos DB, and Azure Managed Redis. It never deletes
  a resource or data.

  Network blocking prevents application usage but does not stop fixed charges
  for provisioned services such as Azure Managed Redis and Cosmos DB.

.EXAMPLE
  ./infra/azure/set-azure-services-access.ps1 status

.EXAMPLE
  ./infra/azure/set-azure-services-access.ps1 disable APPROVE_AZURE_DISABLE

.EXAMPLE
  ./infra/azure/set-azure-services-access.ps1 enable APPROVE_AZURE_SPEND
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "disable", "enable", "off", "on")]
    [string]$Action = "status",

    [Parameter(Position = 1)]
    [string]$Approval = "",

    [string]$ConfigPath = "$PSScriptRoot/../billing-guardrails.json"
)

$ErrorActionPreference = "Stop"
$script:OriginalTriggerTag = "tripplannerControlOriginalTrigger"
$script:ContainerAppsApiVersion = "2025-01-01"
$script:ResourceGroups = @()

function Invoke-AzJson {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $output = & az @Arguments --only-show-errors --output json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI failed: az $($Arguments -join ' ')"
    }
    if ([string]::IsNullOrWhiteSpace(($output -join "`n"))) {
        return $null
    }
    return ($output -join "`n") | ConvertFrom-Json
}

function Invoke-AzMutation {
    param(
        [Parameter(Mandatory)][string]$Target,
        [Parameter(Mandatory)][string]$Operation,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    if (-not $PSCmdlet.ShouldProcess($Target, $Operation)) {
        return
    }
    & az @Arguments --only-show-errors --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI failed while attempting to $Operation on $Target."
    }
}

function Get-ResourcesByType {
    param([Parameter(Mandatory)][string]$ResourceType)

    $resources = @()
    foreach ($resourceGroup in $script:ResourceGroups) {
        $found = Invoke-AzJson -Arguments @(
            "resource", "list",
            "--resource-group", $resourceGroup,
            "--subscription", $script:SubscriptionId,
            "--query", "[?type=='$ResourceType']"
        )
        if ($null -ne $found) {
            $resources += @($found)
        }
    }
    return $resources
}

function Get-ResourceDetails {
    param([Parameter(Mandatory)]$Resource)

    return Invoke-AzJson -Arguments @(
        "resource", "show", "--ids", $Resource.id,
        "--subscription", $script:SubscriptionId
    )
}

function Write-ControlRow {
    param(
        [Parameter(Mandatory)][string]$Kind,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$State,
        [Parameter(Mandatory)][string]$Billing
    )

    Write-Host ("  {0,-18} {1,-38} {2,-18} {3}" -f $Kind, $Name, $State, $Billing)
}

function Set-ContainerAppState {
    param([Parameter(Mandatory)]$Resource, [Parameter(Mandatory)][string]$State)

    $operation = if ($State -eq "Disabled") { "stop" } else { "start" }
    Invoke-AzMutation -Target $Resource.name -Operation "$operation Container App" -Arguments @(
        "rest", "--method", "post",
        "--url", "https://management.azure.com$($Resource.id)/$operation`?api-version=$script:ContainerAppsApiVersion",
        "--subscription", $script:SubscriptionId
    )
}

function Set-ContainerJobState {
    param([Parameter(Mandatory)]$Resource, [Parameter(Mandatory)][string]$State)

    $details = Get-ResourceDetails -Resource $Resource
    $triggerType = [string]$details.properties.configuration.triggerType
    $originalTrigger = [string]$details.tags.$script:OriginalTriggerTag

    if ($State -eq "Disabled" -and $triggerType -ne "Manual") {
        Invoke-AzMutation -Target $Resource.name -Operation "remember its $triggerType trigger" -Arguments @(
            "tag", "update", "--resource-id", $Resource.id, "--operation", "Merge",
            "--tags", "$script:OriginalTriggerTag=$triggerType",
            "--subscription", $script:SubscriptionId
        )
        Invoke-AzMutation -Target $Resource.name -Operation "change its trigger to Manual" -Arguments @(
            "resource", "update", "--ids", $Resource.id,
            "--api-version", $script:ContainerAppsApiVersion,
            "--set", "properties.configuration.triggerType=Manual",
            "properties.configuration.manualTriggerConfig.parallelism=1",
            "properties.configuration.manualTriggerConfig.replicaCompletionCount=1",
            "--subscription", $script:SubscriptionId
        )
    }

    if ($State -eq "Enabled" -and -not [string]::IsNullOrWhiteSpace($originalTrigger)) {
        Invoke-AzMutation -Target $Resource.name -Operation "restore its $originalTrigger trigger" -Arguments @(
            "resource", "update", "--ids", $Resource.id,
            "--api-version", $script:ContainerAppsApiVersion,
            "--set", "properties.configuration.triggerType=$originalTrigger",
            "--subscription", $script:SubscriptionId
        )
    }

    if ($State -eq "Disabled") {
        $executions = Invoke-AzJson -Arguments @(
            "containerapp", "job", "execution", "list",
            "--name", $Resource.name, "--resource-group", $Resource.resourceGroup,
            "--subscription", $script:SubscriptionId,
            "--query", "[?properties.status=='Running'].name"
        )
        foreach ($execution in @($executions)) {
            Invoke-AzMutation -Target "$($Resource.name)/$execution" -Operation "stop job execution" -Arguments @(
                "containerapp", "job", "stop",
                "--name", $Resource.name, "--resource-group", $Resource.resourceGroup,
                "--job-execution-name", $execution,
                "--subscription", $script:SubscriptionId
            )
        }
    }
}

function Set-PublicNetworkState {
    param(
        [Parameter(Mandatory)]$Resource,
        [Parameter(Mandatory)][string]$State
    )

    $publicNetworkAccess = if ($State -eq "Disabled") { "Disabled" } else { "Enabled" }
    switch ($Resource.type.ToLowerInvariant()) {
        "microsoft.cognitiveservices/accounts" {
            Invoke-AzMutation -Target $Resource.name -Operation "set public network access to $publicNetworkAccess" -Arguments @(
                "resource", "update", "--ids", $Resource.id,
                "--set", "properties.publicNetworkAccess=$publicNetworkAccess",
                "--subscription", $script:SubscriptionId
            )
        }
        "microsoft.documentdb/databaseaccounts" {
            Invoke-AzMutation -Target $Resource.name -Operation "set public network access to $publicNetworkAccess" -Arguments @(
                "cosmosdb", "update", "--name", $Resource.name,
                "--resource-group", $Resource.resourceGroup,
                "--public-network-access", $publicNetworkAccess,
                "--subscription", $script:SubscriptionId
            )
        }
        "microsoft.cache/redisenterprise" {
            Invoke-AzMutation -Target $Resource.name -Operation "set public network access to $publicNetworkAccess" -Arguments @(
                "redisenterprise", "update", "--name", $Resource.name,
                "--resource-group", $Resource.resourceGroup,
                "--public-network-access", $publicNetworkAccess,
                "--subscription", $script:SubscriptionId
            )
        }
    }
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "az is not on PATH. Install the Azure CLI, then sign in with the approved personal account."
}

$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$script:SubscriptionId = [string]$config.azure.subscriptionId
$script:ResourceGroups = @($config.azure.environments | ForEach-Object { $_.resourceGroup })
if ($config.azure.actionGroupResourceGroup -notin $script:ResourceGroups) {
    $script:ResourceGroups += $config.azure.actionGroupResourceGroup
}

$account = Invoke-AzJson -Arguments @("account", "show", "--query", "{id:id,name:name,user:user.name}")
if ($account.user -ine "munishgoyal1@gmail.com") {
    throw "Refusing Azure access as '$($account.user)'. Sign in with munishgoyal1@gmail.com."
}
if ($account.id -ne $script:SubscriptionId -or $account.name -ne "Visual Studio Enterprise Subscription") {
    throw "Refusing Azure subscription '$($account.name)' ($($account.id)). Select the configured personal Visual Studio Enterprise subscription."
}

if ($Action -eq "off") { $Action = "disable" }
if ($Action -eq "on") { $Action = "enable" }
if ($Action -eq "disable" -and $Approval -cne "APPROVE_AZURE_DISABLE") {
    throw "Disabling takes hosted Tripplanner offline. Pass APPROVE_AZURE_DISABLE as the second argument."
}
if ($Action -eq "enable" -and $Approval -cne "APPROVE_AZURE_SPEND") {
    throw "Enabling permits paid Azure usage. Pass APPROVE_AZURE_SPEND as the second argument."
}

$containerApps = @(Get-ResourcesByType -ResourceType "Microsoft.App/containerApps")
$containerJobs = @(Get-ResourcesByType -ResourceType "Microsoft.App/jobs")
$openAiAccounts = @(Get-ResourcesByType -ResourceType "Microsoft.CognitiveServices/accounts")
$cosmosAccounts = @(Get-ResourcesByType -ResourceType "Microsoft.DocumentDB/databaseAccounts")
$redisClusters = @(Get-ResourcesByType -ResourceType "Microsoft.Cache/redisEnterprise")

Write-Host "Azure services control"
Write-Host "  account      : $($account.user)"
Write-Host "  subscription : $($account.name) ($($account.id))"
Write-Host "  action       : $Action"
Write-Host "  scope        : $($script:ResourceGroups -join ', ')"
Write-Host ""

if ($Action -eq "status") {
    Write-Host ("  {0,-18} {1,-38} {2,-18} {3}" -f "SERVICE", "RESOURCE", "ACCESS", "BILLING")
    foreach ($resource in $containerApps) {
        $details = Get-ResourceDetails -Resource $resource
        $runningState = [string]$details.properties.runningStatus
        if ([string]::IsNullOrWhiteSpace($runningState)) { $runningState = "Unknown" }
        Write-ControlRow -Kind "Container App" -Name $resource.name -State $runningState -Billing "compute only while running"
    }
    foreach ($resource in $containerJobs) {
        $details = Get-ResourceDetails -Resource $resource
        $trigger = [string]$details.properties.configuration.triggerType
        $original = [string]$details.tags.$script:OriginalTriggerTag
        if (-not [string]::IsNullOrWhiteSpace($original) -and $trigger -eq "Manual") {
            $trigger = "Manual (was $original)"
        }
        Write-ControlRow -Kind "Container Job" -Name $resource.name -State $trigger -Billing "compute per execution"
    }
    foreach ($resource in @($openAiAccounts + $cosmosAccounts + $redisClusters)) {
        $details = Get-ResourceDetails -Resource $resource
        $access = [string]$details.properties.publicNetworkAccess
        if ([string]::IsNullOrWhiteSpace($access)) { $access = "Unknown" }
        $kind = switch ($resource.type.ToLowerInvariant()) {
            "microsoft.cognitiveservices/accounts" { "Azure OpenAI" }
            "microsoft.documentdb/databaseaccounts" { "Cosmos DB" }
            default { "Managed Redis" }
        }
        $billing = switch ($kind) {
            "Azure OpenAI" { "usage-metered" }
            "Cosmos DB" { "throughput/storage continues" }
            default { "provisioned charge continues" }
        }
        Write-ControlRow -Kind $kind -Name $resource.name -State $access -Billing $billing
    }
} else {
    $targetState = if ($Action -eq "disable") { "Disabled" } else { "Enabled" }
    foreach ($resource in $containerApps) { Set-ContainerAppState -Resource $resource -State $targetState }
    foreach ($resource in $containerJobs) { Set-ContainerJobState -Resource $resource -State $targetState }
    foreach ($resource in @($openAiAccounts + $cosmosAccounts + $redisClusters)) {
        Set-PublicNetworkState -Resource $resource -State $targetState
    }
    if ($WhatIfPreference) {
        Write-Host "Preview complete: Azure services would be $($targetState.ToLowerInvariant())."
    } else {
        Write-Host "Azure services are now $($targetState.ToLowerInvariant())." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Residual-cost boundary: this command never deletes resources or data."
Write-Host "Managed Redis, Cosmos throughput/storage, Container Apps environments, Log Analytics retention,"
Write-Host "and other provisioned resources can continue billing while application access is disabled."
Write-Host "Communication Services and Email are usage-metered and have no reversible account-wide pause;"
Write-Host "stopping the hosted apps prevents their hosted Tripplanner caller, but stored credentials remain valid."