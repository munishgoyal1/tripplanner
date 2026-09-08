#!/usr/bin/env pwsh
<#+
.SYNOPSIS
    Report, disable, or enable one Tripplanner Azure environment or the whole estate.

.DESCRIPTION
    Discovers supported resources only in the selected resource groups configured
    in infra/billing-guardrails.json. Disable stops Container Apps, makes recurring
    Container Apps Jobs manual, stops active job executions, and blocks public
    access to Azure OpenAI and Azure Managed Redis. The shared Cosmos account is
    controlled only by the all scope. The script never deletes a resource or data.

  Network blocking prevents application usage but does not stop fixed charges
  for provisioned services such as Azure Managed Redis and Cosmos DB.

.EXAMPLE
  ./infra/azure/set-azure-services-access.ps1 status

.EXAMPLE
    ./infra/azure/set-azure-services-access.ps1 disable prod

.EXAMPLE
    ./infra/azure/set-azure-services-access.ps1 enable prod APPROVE_AZURE_SPEND
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "disable", "enable", "off", "on")]
    [string]$Action = "status",

    [Parameter(Position = 1)]
    [ValidateSet("all", "local", "canary", "prod")]
    [string]$Environment = "all",

    [Parameter(Position = 2)]
    [string]$Approval = "",

    [string]$ConfigPath = "$PSScriptRoot/../billing-guardrails.json",

    [switch]$ServingOnly
)

$ErrorActionPreference = "Stop"
$script:OriginalTriggerTag = "tripplannerControlOriginalTrigger"
$script:OriginalCronTag = "tripplannerControlOriginalCron"
$script:ContainerAppsApiVersion = "2025-01-01"
$script:ResourceGroups = @()
$script:AzureOpenAiFlag = "ENABLE_AZURE_OPENAI"

function Get-AzureOpenAiProfilePath {
    param([Parameter(Mandatory)][string]$EnvironmentName)

    return Join-Path $PSScriptRoot "../../config/environments/$EnvironmentName.env"
}

function Get-AzureOpenAiDesiredState {
    param([Parameter(Mandatory)][string]$EnvironmentName)

    $path = Get-AzureOpenAiProfilePath -EnvironmentName $EnvironmentName
    $match = [regex]::Match(
        (Get-Content $path -Raw),
        "(?m)^$([regex]::Escape($script:AzureOpenAiFlag))=([01])$"
    )
    if (-not $match.Success) {
        throw "$script:AzureOpenAiFlag must be set to 0 or 1 in $path."
    }
    return $match.Groups[1].Value -eq "1"
}

function Set-AzureOpenAiDesiredState {
    param(
        [Parameter(Mandatory)][string]$EnvironmentName,
        [Parameter(Mandatory)][bool]$Enabled
    )

    $path = Get-AzureOpenAiProfilePath -EnvironmentName $EnvironmentName
    $content = Get-Content $path -Raw
    $pattern = "(?m)^$([regex]::Escape($script:AzureOpenAiFlag))=[01]$"
    if (-not [regex]::IsMatch($content, $pattern)) {
        throw "$script:AzureOpenAiFlag must be set to 0 or 1 in $path."
    }
    $value = if ($Enabled) { "1" } else { "0" }
    if ($PSCmdlet.ShouldProcess($path, "set $script:AzureOpenAiFlag=$value")) {
        $updated = [regex]::Replace($content, $pattern, "$script:AzureOpenAiFlag=$value")
        [System.IO.File]::WriteAllText($path, $updated, [System.Text.UTF8Encoding]::new($false))
    }
}

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
    $originalCron = [string]$details.tags.$script:OriginalCronTag

    if ($State -eq "Disabled" -and $triggerType -ne "Manual") {
        $controlTags = @("$script:OriginalTriggerTag=$triggerType")
        if ($triggerType -eq "Schedule") {
            $cron = [string]$details.properties.configuration.scheduleTriggerConfig.cronExpression
            if ([string]::IsNullOrWhiteSpace($cron)) {
                throw "Scheduled job '$($Resource.name)' does not declare a cron expression."
            }
            $controlTags += "$script:OriginalCronTag=$cron"
        }
        Invoke-AzMutation -Target $Resource.name -Operation "remember its $triggerType trigger" -Arguments (@(
            "tag", "update", "--resource-id", $Resource.id, "--operation", "Merge",
            "--tags"
        ) + $controlTags + @(
            "--subscription", $script:SubscriptionId
        ))
        Invoke-AzMutation -Target $Resource.name -Operation "change its trigger to Manual" -Arguments @(
            "resource", "update", "--ids", $Resource.id,
            "--api-version", $script:ContainerAppsApiVersion,
            "--remove", "properties.configuration.scheduleTriggerConfig",
            "--set", "properties.configuration.triggerType=Manual",
            "properties.configuration.manualTriggerConfig.parallelism=1",
            "properties.configuration.manualTriggerConfig.replicaCompletionCount=1",
            "--subscription", $script:SubscriptionId
        )
    }

    if ($State -eq "Enabled" -and -not [string]::IsNullOrWhiteSpace($originalTrigger)) {
        $restoreArguments = @(
            "resource", "update", "--ids", $Resource.id,
            "--api-version", $script:ContainerAppsApiVersion,
            "--remove", "properties.configuration.manualTriggerConfig",
            "--set", "properties.configuration.triggerType=$originalTrigger"
        )
        if ($originalTrigger -eq "Schedule") {
            if ([string]::IsNullOrWhiteSpace($originalCron)) {
                throw "Cannot restore scheduled job '$($Resource.name)' because its saved cron expression is missing."
            }
            $restoreArguments += @(
                "properties.configuration.scheduleTriggerConfig.cronExpression=$originalCron",
                "properties.configuration.scheduleTriggerConfig.parallelism=1",
                "properties.configuration.scheduleTriggerConfig.replicaCompletionCount=1"
            )
        }
        $restoreArguments += @(
            "--subscription", $script:SubscriptionId
        )
        Invoke-AzMutation -Target $Resource.name -Operation "restore its $originalTrigger trigger" `
            -Arguments $restoreArguments
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
$selectedEnvironments = @($config.azure.environments | Where-Object {
    ($Environment -eq "all" -or $_.name -eq $Environment) -and
    (-not $ServingOnly -or $_.name -in @("canary", "prod"))
})
if ($selectedEnvironments.Count -eq 0) {
    throw "Environment '$Environment' is not configured in $ConfigPath."
}
$script:ResourceGroups = @($selectedEnvironments | ForEach-Object { $_.resourceGroup })
if (-not $ServingOnly -and $Environment -eq "all" -and
    $config.azure.actionGroupResourceGroup -notin $script:ResourceGroups) {
    $script:ResourceGroups += $config.azure.actionGroupResourceGroup
}

$account = Invoke-AzJson -Arguments @("account", "show", "--query", "{id:id,name:name,user:user.name}")
if ($account.user -ine [string]$config.azure.operatorAccount) {
    throw "Refusing Azure access as '$($account.user)'. Sign in with $($config.azure.operatorAccount)."
}
if ($account.id -ne $script:SubscriptionId) {
    throw "Refusing Azure subscription '$($account.name)' ($($account.id)). Select $script:SubscriptionId."
}

if ($Action -eq "off") { $Action = "disable" }
if ($Action -eq "on") { $Action = "enable" }
if ($Action -eq "enable" -and $Approval -cne "APPROVE_AZURE_SPEND") {
    throw "Enabling permits paid Azure usage. Pass APPROVE_AZURE_SPEND as the third argument."
}

$containerApps = @(Get-ResourcesByType -ResourceType "Microsoft.App/containerApps")
$containerJobs = @(Get-ResourcesByType -ResourceType "Microsoft.App/jobs")
$openAiAccounts = @(if (-not $ServingOnly) {
    @(Get-ResourcesByType -ResourceType "Microsoft.CognitiveServices/accounts")
})
$cosmosAccounts = @(if (-not $ServingOnly) {
    @(Get-ResourcesByType -ResourceType "Microsoft.DocumentDB/databaseAccounts")
})
$redisClusters = @(if (-not $ServingOnly) {
    @(Get-ResourcesByType -ResourceType "Microsoft.Cache/redisEnterprise")
})

$controlName = if ($ServingOnly) { "Azure hosted serving" } else { "Azure services" }
Write-Host "$controlName control"
Write-Host "  account      : $($account.user)"
Write-Host "  subscription : $($account.name) ($($account.id))"
Write-Host "  action       : $Action"
Write-Host "  environment  : $Environment"
Write-Host "  scope        : $($script:ResourceGroups -join ', ')"
if ($ServingOnly) {
    Write-Host "  dependencies : unchanged"
} elseif ($Environment -ne "all") {
    Write-Host "  shared data  : not changed; Cosmos serves local, canary, and prod"
}
Write-Host ""

$openAiDesiredByResourceGroup = @{}
foreach ($selectedEnvironment in @($selectedEnvironments | Where-Object { -not $ServingOnly })) {
    if ($Action -in @("enable", "disable")) {
        Set-AzureOpenAiDesiredState -EnvironmentName $selectedEnvironment.name `
            -Enabled ($Action -eq "enable")
    }
    $desired = Get-AzureOpenAiDesiredState -EnvironmentName $selectedEnvironment.name
    $openAiDesiredByResourceGroup[[string]$selectedEnvironment.resourceGroup] = $desired
    Write-Host "  $($selectedEnvironment.name) OpenAI desired: $desired"
}
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
        if ($kind -eq "Azure OpenAI" -and $openAiDesiredByResourceGroup.ContainsKey($resource.resourceGroup)) {
            $desired = $openAiDesiredByResourceGroup[$resource.resourceGroup]
            $cloudEnabled = $access -eq "Enabled"
            $syncState = if ($access -eq "Unknown" -or $cloudEnabled -ne $desired) { "DRIFT" } else { "in sync" }
            $access = "$access ($syncState)"
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
        Write-Host "Preview complete: $controlName would be $($targetState.ToLowerInvariant())."
    } else {
        Write-Host "$controlName is now $($targetState.ToLowerInvariant())." -ForegroundColor Green
        if (-not $ServingOnly) {
            Write-Host "Updated $script:AzureOpenAiFlag in the selected checked-in environment profile(s)."
            Write-Host "Local processes require a restart; hosted environments require a deployment."
        }
    }
}

Write-Host ""
if ($ServingOnly) {
    Write-Host "Serving boundary: hosted apps are stopped and recurring jobs are suspended."
    Write-Host "DNS and ingress endpoints can still resolve, but no Tripplanner container serves requests."
    Write-Host "Dependencies, data, resources, and fixed charges remain unchanged."
} else {
    Write-Host "Residual-cost boundary: this command never deletes resources or data."
    Write-Host "Managed Redis, Cosmos throughput/storage, Container Apps environments, Log Analytics retention,"
    Write-Host "and other provisioned resources can continue billing while application access is disabled."
    Write-Host "Communication Services and Email are usage-metered and have no reversible account-wide pause;"
    Write-Host "stopping the hosted apps prevents their hosted Tripplanner caller, but stored credentials remain valid."
}