#!/usr/bin/env pwsh
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ConfigPath,
    [Parameter(Mandatory)][ValidateSet("canary", "prod")][string]$Environment,
    [Parameter(Mandatory)][string]$EvidenceDirectory,
    [switch]$BindDomains
)

$ErrorActionPreference = "Stop"
$migrationRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $migrationRoot "../..")
. "$migrationRoot/common.ps1"
. "$repoRoot/infra/deployment-common.ps1"

$config = Read-MigrationConfig -Path $ConfigPath
$azure = $config.azure
$target = $azure.target
$environmentConfig = $target.hosted.$Environment
$resourceGroup = "rg-tripplanner-$Environment"
$prefix = if ($Environment -eq "prod") { "prod" } else { "canary" }
$profile = Join-Path $repoRoot "config/environments/$Environment.env"
$secretFile = Join-Path $repoRoot ([string]$azure.sourceSecretFiles.$Environment)
$parametersFile = Join-Path $repoRoot "infra/$Environment.bicepparam"
$templateFile = Join-Path $repoRoot "infra/main.bicep"

Import-DeploymentEnvironment -Path $profile
Import-DeploymentEnvironment -Path $secretFile

$openAiKey = Invoke-CheckedCommand -Executable "az" -Capture -Description "read target OpenAI key" -Arguments @(
    "cognitiveservices", "account", "keys", "list",
    "--subscription", $target.subscriptionId,
    "--resource-group", $resourceGroup,
    "--name", $environmentConfig.openAiAccount,
    "--query", "key1", "--output", "tsv"
)
$openAiEndpoint = Invoke-CheckedCommand -Executable "az" -Capture -Description "read target OpenAI endpoint" -Arguments @(
    "cognitiveservices", "account", "show",
    "--subscription", $target.subscriptionId,
    "--resource-group", $resourceGroup,
    "--name", $environmentConfig.openAiAccount,
    "--query", "properties.endpoint", "--output", "tsv"
)
$env:AZURE_OPENAI_API_KEY = $openAiKey
$env:AZURE_OPENAI_ENDPOINT = $openAiEndpoint
$env:AZURE_OPENAI_DEPLOYMENT = [string]$environmentConfig.openAiDeployment
$env:COSMOS_ACCOUNT_NAME = [string]$target.cosmosAccount
$env:COSMOS_RESOURCE_GROUP = [string]$target.cosmosResourceGroup
$env:COSMOS_DATABASE = "tripplanner-$Environment"
$communication = $target.communications
$communicationId = "/subscriptions/$($target.subscriptionId)/resourceGroups/rg-tripplanner-canary/providers/Microsoft.Communication/communicationServices/$($communication.serviceName)"
$connectionString = Invoke-CheckedCommand -Executable "az" -Capture -Description "read target Communication Services key" -Arguments @(
    "rest", "--method", "post",
    "--url", "https://management.azure.com$communicationId/listKeys?api-version=2023-04-01",
    "--query", "primaryConnectionString", "--output", "tsv"
)
$senderDomain = Invoke-CheckedCommand -Executable "az" -Capture -Description "read target email sender domain" -Arguments @(
    "deployment", "group", "show", "--subscription", $target.subscriptionId,
    "--resource-group", "rg-tripplanner-canary", "--name", "tripplanner-communications",
    "--query", "properties.outputs.senderDomain.value", "--output", "tsv"
)
$env:AZURE_COMMUNICATION_CONNECTION_STRING = $connectionString
$env:AZURE_COMMUNICATION_EMAIL_SENDER = "DoNotReply@$senderDomain"

$domainParameters = if ($BindDomains -and $Environment -eq "prod") {
    @(
        "apexCustomDomain=$($azure.dns.apex)",
        "apexManagedCertificateName=$($target.apexManagedCertificateName)",
        "wwwCustomDomain=$($azure.dns.www)",
        "wwwManagedCertificateName=$($target.wwwManagedCertificateName)"
    )
} else {
    @(
        "apexCustomDomain=",
        "apexManagedCertificateName=",
        "wwwCustomDomain=",
        "wwwManagedCertificateName="
    )
}
$overrides = @(
    "namePrefix=$prefix",
    "containerImage=ghcr.io/munishgoyal1/tripplanner:$($azure.imageTag)",
    "cosmosResourceGroupName=$($target.cosmosResourceGroup)",
    "cosmosAccountName=$($target.cosmosAccount)",
    "failureAlertEmail=$($target.failureAlertEmail)",
    $(if ($BindDomains -and $Environment -eq "prod") {
        "oauthRedirectBase=https://$($azure.dns.apex)/api"
    } else {
        "oauthRedirectBase="
    })
) + $domainParameters

Invoke-CheckedCommand -Executable "az" -Description "ensure target resource group" -Arguments @(
    "group", "create", "--subscription", $target.subscriptionId,
    "--name", $resourceGroup, "--location", $target.location, "--output", "none"
)
$validationArguments = @(
    "deployment", "group", "validate", "--subscription", $target.subscriptionId,
    "--resource-group", $resourceGroup, "--template-file", $templateFile,
    "--parameters", $parametersFile, "--parameters"
) + $overrides
Invoke-CheckedCommand -Executable "az" -Description "validate target $Environment" -Arguments $validationArguments

$whatIfArguments = @(
    "deployment", "group", "what-if", "--subscription", $target.subscriptionId,
    "--resource-group", $resourceGroup, "--template-file", $templateFile,
    "--parameters", $parametersFile, "--parameters"
) + $overrides + @("--result-format", "ResourceIdOnly", "--output", "json")
$whatIfArguments += "--no-pretty-print"
$whatIfRaw = Invoke-CheckedCommand -Executable "az" -Capture -Description "preview target $Environment" -Arguments $whatIfArguments
$whatIf = ConvertFrom-AzureCliJson -Output $whatIfRaw -Action "Target $Environment what-if"
Assert-DeploymentHasNoDeletes -WhatIf $whatIf -EnvironmentName "Target $Environment"

if ($WhatIfPreference) {
    Write-Host "Target $Environment preview contains no deletes."
    exit 0
}

$deploymentArguments = @(
    "deployment", "group", "create", "--subscription", $target.subscriptionId,
    "--resource-group", $resourceGroup, "--template-file", $templateFile,
    "--parameters", $parametersFile, "--parameters"
) + $overrides + @("--query", "properties.outputs", "--output", "json")
$deploymentRaw = Invoke-CheckedCommand -Executable "az" -Capture -Description "deploy target $Environment" -Arguments $deploymentArguments
$deployment = $deploymentRaw | ConvertFrom-Json
$url = [string]$deployment.containerAppUrl.value
$appName = [string]$deployment.containerAppName.value
$oauthBase = if ($BindDomains -and $Environment -eq "prod") {
    "https://$($azure.dns.apex)/api"
} else {
    "$($url.TrimEnd('/'))/api"
}

if (-not ($BindDomains -and $Environment -eq "prod")) {
    Invoke-CheckedCommand -Executable "az" -Description "set target $Environment callback" -Arguments @(
        "containerapp", "update", "--subscription", $target.subscriptionId,
        "--resource-group", $resourceGroup, "--name", $appName,
        "--set-env-vars", "OAUTH_REDIRECT_BASE=$oauthBase", "--output", "none"
    )
}

Write-MigrationJson -Path (Join-Path $EvidenceDirectory "target-$Environment.json") -Value ([ordered]@{
    environment = $Environment
    subscriptionId = $target.subscriptionId
    resourceGroup = $resourceGroup
    appName = $appName
    url = $url
    oauthRedirectBase = $oauthBase
    domainsBound = [bool]$BindDomains
})
Write-Host "Target $Environment URL: $url"