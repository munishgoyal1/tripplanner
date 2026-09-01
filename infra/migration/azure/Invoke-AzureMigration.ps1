#!/usr/bin/env pwsh
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ConfigPath,
    [Parameter(Mandatory)][ValidateSet("preflight", "inventory", "provision", "data", "validate", "cutover", "retire")][string]$Phase,
    [Parameter(Mandatory)][string]$RunId,
    [Parameter(Mandatory)][string]$EvidenceDirectory,
    [string]$Approval = ""
)

$ErrorActionPreference = "Stop"
$migrationRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $migrationRoot "../..")
. "$migrationRoot/common.ps1"

$config = Read-MigrationConfig -Path $ConfigPath
$azure = $config.azure
$source = $azure.source
$target = $azure.target
$cosmosDatabases = @($azure.cosmosDatabases)
if ($cosmosDatabases.Count -eq 0) {
    throw "azure.cosmosDatabases must explicitly list the hosted databases to migrate."
}
if ($cosmosDatabases -contains "tripplanner-local") {
    throw "azure.cosmosDatabases must not include tripplanner-local; local development uses the Cosmos emulator."
}
$requiredProviders = @(
    "Microsoft.App", "Microsoft.CognitiveServices", "Microsoft.Communication",
    "Microsoft.DocumentDB", "Microsoft.Insights", "Microsoft.OperationalInsights"
)

function Get-AzureJson {
    param([Parameter(Mandatory)][string[]]$Arguments, [Parameter(Mandatory)][string]$Description)
    $raw = Invoke-CheckedCommand -Executable "az" -Arguments ($Arguments + @("--output", "json")) -Description $Description -Capture
    if ([string]::IsNullOrWhiteSpace($raw)) { return @() }
    return $raw | ConvertFrom-Json
}

function Assert-AzureIdentity {
    $accounts = @(Get-AzureJson -Description "list Azure subscriptions" -Arguments @("account", "list", "--all"))
    foreach ($side in @("source", "target")) {
        $expected = $azure.$side
        Assert-ConfiguredValue "azure.$side.account" $expected.account
        Assert-ConfiguredValue "azure.$side.tenantId" $expected.tenantId
        Assert-ConfiguredValue "azure.$side.subscriptionId" $expected.subscriptionId
            $matchingAccounts = @($accounts | Where-Object {
            $_.id -eq $expected.subscriptionId -and $_.tenantId -eq $expected.tenantId
        })
            if ($matchingAccounts.Count -ne 1) {
            throw "Azure $side subscription $($expected.subscriptionId) in tenant $($expected.tenantId) is not available to the CLI."
        }
            if ($matchingAccounts[0].user.name -ine $expected.account) {
                throw "Azure $side subscription resolves to '$($matchingAccounts[0].user.name)', expected '$($expected.account)'."
        }
    }
    if ($source.subscriptionId -eq $target.subscriptionId -or $source.tenantId -eq $target.tenantId) {
        throw "Source and target must be different Azure subscriptions and tenants for this migration workflow."
    }
    if (@($source.account, $target.account) -icontains "mugoy@microsoft.com") {
        throw "The prohibited work identity must not appear in migration configuration."
    }
}

function Get-SourceResources {
    return @(Get-AzureJson -Description "inventory source Azure resources" -Arguments @(
        "resource", "list", "--subscription", $source.subscriptionId,
        "--query", "[].{id:id,name:name,type:type,resourceGroup:resourceGroup,location:location,sku:sku,tags:tags}"
    ))
}

function Assert-SourceScopeComplete {
    $resources = @(Get-SourceResources)
    $outside = @($resources | Where-Object { $_.resourceGroup -notin @($source.resourceGroups) })
    if ($outside.Count -gt 0) {
        $summary = $outside | ForEach-Object { "$($_.resourceGroup)/$($_.name) [$($_.type)]" }
        throw "Source subscription has resources outside the retirement allowlist: $($summary -join '; '). Add them explicitly or migrate them separately."
    }
}

function Get-CosmosDatabases {
    param($Coordinates)
    $available = @(Get-AzureJson -Description "list Cosmos databases" -Arguments @(
        "cosmosdb", "sql", "database", "list", "--subscription", $Coordinates.subscriptionId,
        "--resource-group", $Coordinates.cosmosResourceGroup,
        "--account-name", $Coordinates.cosmosAccount, "--query", "[].name"
    ))
    $missing = @($cosmosDatabases | Where-Object { $_ -notin $available })
    if ($missing.Count -gt 0) {
        throw "Configured Cosmos databases are missing from $($Coordinates.cosmosAccount): $($missing -join ', ')."
    }
    return @($cosmosDatabases)
}

function Invoke-CosmosCopy {
    param([Parameter(Mandatory)][string]$Database, [switch]$VerifyOnly)
    $arguments = @(
        (Join-Path $repoRoot "scripts/cosmos_copy.py"),
        "--src-subscription", $source.subscriptionId,
        "--src-resource-group", $source.cosmosResourceGroup,
        "--src-account", $source.cosmosAccount, "--src-db", $Database,
        "--dst-subscription", $target.subscriptionId,
        "--dst-resource-group", $target.cosmosResourceGroup,
        "--dst-account", $target.cosmosAccount, "--dst-db", $Database,
        "--json"
    )
    if ($VerifyOnly) { $arguments += "--verify-only" }
    Invoke-CheckedCommand -Executable (Join-Path $repoRoot ".venv/bin/python") `
        -Arguments $arguments -Description "Cosmos $Database migration"
}

function Stop-SourceServing {
    $allowedResourceGroups = @($source.resourceGroups)
    $apps = @(Get-AzureJson -Description "list source apps" -Arguments @(
        "resource", "list", "--subscription", $source.subscriptionId,
        "--query", "[?type=='Microsoft.App/containerApps'].{id:id,name:name,resourceGroup:resourceGroup}"
    ) | Where-Object { $_.resourceGroup -in $allowedResourceGroups })
    foreach ($app in $apps) {
        Invoke-CheckedCommand -Executable "az" -Description "stop source Container App" -Arguments @(
            "rest", "--method", "post", "--url", "https://management.azure.com$($app.id)/stop?api-version=2025-01-01"
        )
    }
    $jobs = @(Get-AzureJson -Description "list source jobs" -Arguments @(
        "resource", "list", "--subscription", $source.subscriptionId,
        "--query", "[?type=='Microsoft.App/jobs'].{id:id,name:name,resourceGroup:resourceGroup}"
    ) | Where-Object { $_.resourceGroup -in $allowedResourceGroups })
    foreach ($job in $jobs) {
        Invoke-CheckedCommand -Executable "az" -Description "make source job manual" -Arguments @(
            "resource", "update", "--ids", $job.id, "--api-version", "2025-01-01",
            "--set", "properties.configuration.triggerType=Manual", "--output", "none"
        )
        $executions = @(Get-AzureJson -Description "list running source job executions" -Arguments @(
            "containerapp", "job", "execution", "list", "--subscription", $source.subscriptionId,
            "--resource-group", $job.resourceGroup, "--name", $job.name,
            "--query", "[?properties.status=='Running'].name"
        ))
        foreach ($execution in $executions) {
            Invoke-CheckedCommand "az" @(
                "containerapp", "job", "stop", "--subscription", $source.subscriptionId,
                "--resource-group", $job.resourceGroup, "--name", $job.name,
                "--job-execution-name", $execution, "--output", "none"
            ) "stop source job execution $execution"
        }
    }
}

Assert-CommandAvailable "az"
Assert-AzureIdentity

switch ($Phase) {
    "preflight" {
        Assert-SourceScopeComplete
        Assert-ConfiguredValue "azure.imageTag" $azure.imageTag
        Assert-ConfiguredValue "azure.target.cosmosAccount" $target.cosmosAccount
        foreach ($environment in @("local", "canary", "prod")) {
            if ($environment -ne "local") {
                $secretFile = Join-Path $repoRoot ([string]$azure.sourceSecretFiles.$environment)
                if (-not (Test-Path $secretFile)) { throw "Required secret overlay not found: $secretFile" }
            }
            Assert-ConfiguredValue "azure.target.hosted.$environment.openAiAccount" $target.hosted.$environment.openAiAccount
            Assert-ConfiguredValue "azure.target.hosted.$environment.openAiDeployment" $target.hosted.$environment.openAiDeployment
        }
        $providers = @(Get-AzureJson -Description "inspect target providers" -Arguments @(
            "provider", "list", "--subscription", $target.subscriptionId,
            "--query", "[?namespace=='$($requiredProviders -join "' || namespace=='")'].{namespace:namespace,state:registrationState}"
        ))
        $freeTier = @(Get-AzureJson -Description "inspect target Cosmos free tier" -Arguments @(
            "cosmosdb", "list", "--subscription", $target.subscriptionId,
            "--query", "[?enableFreeTier].{name:name,resourceGroup:resourceGroup}"
        ))
        if ($freeTier.Count -gt 0 -and $target.cosmosAccount -notin @($freeTier.name)) {
            throw "Target subscription already has another Cosmos lifetime free-tier account."
        }
        Write-MigrationCheckpoint -EvidenceDirectory $EvidenceDirectory -Name "preflight" -Value ([ordered]@{
            sourceSubscription = $source.subscriptionId
            targetSubscription = $target.subscriptionId
            providers = $providers
            targetFreeTierAccounts = $freeTier
        })
    }
    "inventory" {
        Assert-MigrationCheckpoint $EvidenceDirectory "preflight"
        $sourceResources = @(Get-SourceResources)
        $targetResources = @(Get-AzureJson -Description "inventory target Azure resources" -Arguments @(
            "resource", "list", "--subscription", $target.subscriptionId,
            "--query", "[].{id:id,name:name,type:type,resourceGroup:resourceGroup,location:location,sku:sku,tags:tags}"
        ))
        $roles = @(Get-AzureJson -Description "inventory source role assignments" -Arguments @(
            "role", "assignment", "list", "--subscription", $source.subscriptionId, "--all"
        ))
        $databases = @(Get-CosmosDatabases ([pscustomobject]@{
            subscriptionId = $source.subscriptionId
            cosmosResourceGroup = $source.cosmosResourceGroup
            cosmosAccount = $source.cosmosAccount
        }))
        $containers = [ordered]@{}
        foreach ($database in $databases) {
            $containers[$database] = @(Get-AzureJson -Description "inventory $database containers" -Arguments @(
                "cosmosdb", "sql", "container", "list", "--subscription", $source.subscriptionId,
                "--resource-group", $source.cosmosResourceGroup, "--account-name", $source.cosmosAccount,
                "--database-name", $database,
                "--query", "[].{name:name,partitionKey:resource.partitionKey,defaultTtl:resource.defaultTtl}"
            ))
        }
        Write-MigrationJson (Join-Path $EvidenceDirectory "source-resources.json") $sourceResources
        Write-MigrationJson (Join-Path $EvidenceDirectory "target-resources-before.json") $targetResources
        Write-MigrationJson (Join-Path $EvidenceDirectory "source-role-assignments.json") $roles
        Write-MigrationJson (Join-Path $EvidenceDirectory "source-cosmos-schema.json") $containers
        Write-MigrationCheckpoint $EvidenceDirectory "inventory" ([ordered]@{
            sourceResources = $sourceResources.Count
            targetResourcesBefore = $targetResources.Count
            cosmosDatabases = $databases
        })
    }
    "provision" {
        Assert-MigrationCheckpoint $EvidenceDirectory "inventory"
        Assert-Approval $Approval "APPROVE_TARGET_PROVISIONING" "Azure target provisioning"
        if ($WhatIfPreference) { Write-Host "Would provision the Azure target estate."; break }
        foreach ($provider in $requiredProviders) {
            Invoke-CheckedCommand "az" @("provider", "register", "--subscription", $target.subscriptionId, "--namespace", $provider, "--wait") "register $provider"
        }
        & (Join-Path $repoRoot "infra/deploy-data.ps1") -SubscriptionId $target.subscriptionId `
            -Location $target.location -ResourceGroup $target.cosmosResourceGroup -AccountName $target.cosmosAccount `
            -DryRun:$WhatIfPreference
        if (-not $WhatIfPreference) {
            foreach ($environment in @("local", "canary", "prod")) {
                $hosted = $target.hosted.$environment
                & (Join-Path $repoRoot "infra/provision-aoai.ps1") -Environment $environment `
                    -SubscriptionId $target.subscriptionId -ResourceGroup "rg-tripplanner-$environment" `
                    -Location $target.location -AccountName $hosted.openAiAccount `
                    -DeploymentName $hosted.openAiDeployment -SkuName $hosted.openAiSku `
                    -Capacity $hosted.openAiCapacity
            }
            $communications = $target.communications
            Invoke-CheckedCommand "az" @(
                "deployment", "group", "create", "--subscription", $target.subscriptionId,
                "--resource-group", "rg-tripplanner-canary",
                "--name", "tripplanner-communications",
                "--template-file", (Join-Path $PSScriptRoot "communications.bicep"),
                "--parameters", "communicationServiceName=$($communications.serviceName)",
                "emailServiceName=$($communications.emailServiceName)", "--output", "none"
            ) "deploy target Communication Services"
            foreach ($environment in @("canary", "prod")) {
                & (Join-Path $PSScriptRoot "Deploy-TargetEnvironment.ps1") `
                    -ConfigPath $ConfigPath -Environment $environment -EvidenceDirectory $EvidenceDirectory
            }
            $prod = Get-Content (Join-Path $EvidenceDirectory "target-prod.json") -Raw | ConvertFrom-Json
            $prodJobs = @(Get-AzureJson -Description "list target production jobs" -Arguments @(
                "resource", "list", "--subscription", $target.subscriptionId,
                "--resource-group", "rg-tripplanner-prod",
                "--query", "[?type=='Microsoft.App/jobs'].id"
            ))
            foreach ($jobId in $prodJobs) {
                Invoke-CheckedCommand "az" @(
                    "resource", "update", "--ids", $jobId, "--api-version", "2025-01-01",
                    "--set", "properties.configuration.triggerType=Manual", "--output", "none"
                ) "suspend target production job before cutover"
            }
            Invoke-CheckedCommand "az" @(
                "containerapp", "stop", "--subscription", $target.subscriptionId,
                "--resource-group", $prod.resourceGroup, "--name", $prod.appName, "--output", "none"
            ) "stop target production before data cutover"
            $guardrails = Get-Content (Join-Path $repoRoot "infra/billing-guardrails.json") -Raw | ConvertFrom-Json
            $guardrails.alertEmail = $target.failureAlertEmail
            $guardrails.azure.subscriptionId = $target.subscriptionId
            $targetGuardrails = Join-Path $EvidenceDirectory "target-billing-guardrails.json"
            Write-MigrationJson $targetGuardrails $guardrails
            & (Join-Path $repoRoot "infra/azure/apply-billing-guardrails.ps1") -ConfigPath $targetGuardrails
            if ($LASTEXITCODE -ne 0) { throw "Target Azure billing guardrails failed." }
            Write-MigrationCheckpoint $EvidenceDirectory "provision" ([ordered]@{
                targetProductionUrl = $prod.url
                billingGuardrails = "applied"
            })
        }
    }
    "data" {
        Assert-MigrationCheckpoint $EvidenceDirectory "provision"
        Assert-Approval $Approval "APPROVE_DATA_COPY" "Initial Azure data copy"
        if ($WhatIfPreference) { Write-Host "Would copy and exactly verify every source Cosmos database."; break }
        $databases = @(Get-CosmosDatabases ([pscustomobject]@{
            subscriptionId = $source.subscriptionId
            cosmosResourceGroup = $source.cosmosResourceGroup
            cosmosAccount = $source.cosmosAccount
        }))
        foreach ($database in $databases) { Invoke-CosmosCopy -Database $database }
        Write-MigrationCheckpoint $EvidenceDirectory "data" ([ordered]@{ databases = $databases; verification = "exact-content" })
    }
    "validate" {
        Assert-MigrationCheckpoint $EvidenceDirectory "data"
        $canary = Get-Content (Join-Path $EvidenceDirectory "target-canary.json") -Raw | ConvertFrom-Json
        & (Join-Path $repoRoot "infra/smoke-hosted.ps1") -Environment canary `
            -BaseUrl $canary.url -ExpectedOAuthCallback "$($canary.oauthRedirectBase)/auth/callback/google"
        if ($LASTEXITCODE -ne 0) { throw "Target canary smoke failed." }
        foreach ($database in @(Get-CosmosDatabases ([pscustomobject]@{
            subscriptionId = $source.subscriptionId
            cosmosResourceGroup = $source.cosmosResourceGroup
            cosmosAccount = $source.cosmosAccount
        }))) { Invoke-CosmosCopy -Database $database -VerifyOnly }
        Write-MigrationCheckpoint $EvidenceDirectory "validate" ([ordered]@{ canaryUrl = $canary.url; smoke = "passed"; data = "verified" })
    }
    "cutover" {
        Assert-MigrationCheckpoint $EvidenceDirectory "validate"
        Assert-Approval $Approval "APPROVE_CLOUD_CUTOVER" "Azure production cutover"
        Assert-ConfiguredValue "azure.dns.cutoverHook" $azure.dns.cutoverHook
        if (-not (Test-Path $azure.dns.cutoverHook)) { throw "DNS cutover hook not found: $($azure.dns.cutoverHook)" }
        if ($WhatIfPreference) { Write-Host "Would freeze source serving, take the final backup, copy data, change DNS, and bind domains."; break }
        Stop-SourceServing
        $backupDirectory = Join-Path $EvidenceDirectory "final-prod-backup"
        Invoke-CheckedCommand (Join-Path $repoRoot ".venv/bin/python") @(
            (Join-Path $repoRoot "scripts/cosmos_copy.py"), "--export-only",
            "--src-subscription", $source.subscriptionId,
            "--src-resource-group", $source.cosmosResourceGroup,
            "--src-account", $source.cosmosAccount, "--src-db", "tripplanner-prod",
            "--backup-dir", $backupDirectory, "--json"
        ) "export final production backup"
        foreach ($database in @(Get-CosmosDatabases ([pscustomobject]@{
            subscriptionId = $source.subscriptionId
            cosmosResourceGroup = $source.cosmosResourceGroup
            cosmosAccount = $source.cosmosAccount
        }))) { Invoke-CosmosCopy -Database $database }
        $prod = Get-Content (Join-Path $EvidenceDirectory "target-prod.json") -Raw | ConvertFrom-Json
        & $azure.dns.cutoverHook -TargetHostname ([uri]$prod.url).Host -Apex $azure.dns.apex -Www $azure.dns.www
        if ($LASTEXITCODE -ne 0) { throw "DNS cutover hook failed." }
        & (Join-Path $PSScriptRoot "Deploy-TargetEnvironment.ps1") `
            -ConfigPath $ConfigPath -Environment prod -EvidenceDirectory $EvidenceDirectory -BindDomains
        Invoke-CheckedCommand "az" @(
            "containerapp", "start", "--subscription", $target.subscriptionId,
            "--resource-group", $prod.resourceGroup, "--name", $prod.appName, "--output", "none"
        ) "start target production"
        & (Join-Path $repoRoot "infra/smoke-hosted.ps1") -Environment production `
            -BaseUrl $prod.url -BrowserBaseUrl "https://$($azure.dns.apex)" `
            -ExpectedOAuthCallback "https://$($azure.dns.apex)/api/auth/callback/google"
        if ($LASTEXITCODE -ne 0) { throw "Target production smoke failed after cutover." }
        Write-MigrationCheckpoint $EvidenceDirectory "cutover" ([ordered]@{ targetUrl = $prod.url; backup = $backupDirectory; smoke = "passed" })
    }
    "retire" {
        Assert-MigrationCheckpoint $EvidenceDirectory "cutover"
        Assert-Approval $Approval "APPROVE_SOURCE_RETIREMENT" "Azure source retirement"
        Assert-SourceScopeComplete
        if ($WhatIfPreference) { Write-Host "Would stop and delete the allowlisted Azure source resource groups."; break }
        Stop-SourceServing
        if (-not [bool]$azure.deleteSourceResourceGroupsOnRetire) {
            throw "Disabling services does not stop fixed Azure charges. Set deleteSourceResourceGroupsOnRetire=true after accepting irreversible deletion."
        }
        foreach ($resourceGroup in @($source.resourceGroups)) {
            Invoke-CheckedCommand "az" @(
                "group", "delete", "--subscription", $source.subscriptionId,
                "--name", $resourceGroup, "--yes"
            ) "delete source resource group $resourceGroup"
        }
        $remaining = @(Get-SourceResources)
        if ($remaining.Count -ne 0) { throw "Source subscription still contains $($remaining.Count) resource(s)." }
        Write-MigrationCheckpoint $EvidenceDirectory "retire" ([ordered]@{
            remainingResources = 0
            manualAction = "Cancel the empty source subscription in Azure billing to close the account boundary."
        })
    }
}