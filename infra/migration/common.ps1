$ErrorActionPreference = "Stop"

function Read-MigrationConfig {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Migration config not found: $Path. Copy migration.example.json outside the repository and fill every required value."
    }
    return Get-Content -Raw -Path $Path | ConvertFrom-Json
}

function Assert-ConfiguredValue {
    param([Parameter(Mandatory)][string]$Name, [AllowEmptyString()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -match '^<.+>$') {
        throw "Migration config value '$Name' is missing or still a placeholder."
    }
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not available on PATH."
    }
}

function New-MigrationEvidenceDirectory {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Cloud,
        [Parameter(Mandatory)][string]$RunId
    )

    $path = Join-Path $Root "$RunId/$Cloud"
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    return (Resolve-Path $path).Path
}

function Write-MigrationJson {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)]$Value
    )

    $Value | ConvertTo-Json -Depth 100 | Set-Content -Path $Path -Encoding utf8
}

function Write-MigrationCheckpoint {
    param(
        [Parameter(Mandatory)][string]$EvidenceDirectory,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)]$Value
    )

    $record = [ordered]@{
        checkpoint = $Name
        completedAt = (Get-Date).ToUniversalTime().ToString("o")
        evidence = $Value
    }
    Write-MigrationJson -Path (Join-Path $EvidenceDirectory "$Name.json") -Value $record
}

function Assert-MigrationCheckpoint {
    param(
        [Parameter(Mandatory)][string]$EvidenceDirectory,
        [Parameter(Mandatory)][string]$Name
    )

    $path = Join-Path $EvidenceDirectory "$Name.json"
    if (-not (Test-Path $path)) {
        throw "Required checkpoint '$Name' is missing from $EvidenceDirectory. Run the preceding phase successfully first."
    }
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$Description,
        [switch]$Capture,
        [string]$AzureConfigDirectory = ""
    )

    Write-Host "[$Description] $Executable $($Arguments -join ' ')"
    $oldAzureConfig = $env:AZURE_CONFIG_DIR
    if ($Executable -eq "az" -and [string]::IsNullOrWhiteSpace($AzureConfigDirectory)) {
        foreach ($side in @("SOURCE", "TARGET")) {
            $subscription = [Environment]::GetEnvironmentVariable("TRIPPLANNER_MIGRATION_${side}_SUBSCRIPTION")
            $directory = [Environment]::GetEnvironmentVariable("TRIPPLANNER_MIGRATION_${side}_AZURE_CONFIG_DIR")
            if ($subscription -and $directory -and
                (($Arguments -contains $subscription) -or
                 (@($Arguments | Where-Object { $_ -like "*/subscriptions/$subscription/*" }).Count -gt 0))) {
                $AzureConfigDirectory = $directory
                break
            }
        }
    }
    try {
        if ($AzureConfigDirectory) { $env:AZURE_CONFIG_DIR = $AzureConfigDirectory }
        $output = & $Executable @Arguments
        $commandExitCode = $LASTEXITCODE
    } finally {
        $env:AZURE_CONFIG_DIR = $oldAzureConfig
    }
    if ($commandExitCode -ne 0) {
        throw "$Description failed with exit code $commandExitCode."
    }
    if ($Capture) { return ($output | Out-String).Trim() }
}

function Assert-Approval {
    param(
        [Parameter(Mandatory)][string]$Actual,
        [Parameter(Mandatory)][string]$Expected,
        [Parameter(Mandatory)][string]$Operation
    )

    if ($Actual -cne $Expected) {
        throw "$Operation requires -Approval $Expected."
    }
}

function Assert-SourceRetirementAllowed {
    param($Azure)
    if ($Azure.preserveSource -ne $false -or -not [bool]$Azure.deleteSourceResourceGroupsOnRetire) {
        throw "Source preservation is enabled. No source stop/delete retirement action is allowed."
    }
}

function Assert-MigrationManifest {
    param([string]$ConfigPath, [string]$EvidenceDirectory)
    $fingerprint = (Get-FileHash -Algorithm SHA256 -LiteralPath $ConfigPath).Hash
    $path = Join-Path $EvidenceDirectory "manifest-fingerprint.json"
    if (Test-Path $path) {
        $record = Get-Content -Raw $path | ConvertFrom-Json
        if ($record.sha256 -ne $fingerprint) {
            throw "Migration configuration changed. Use a fresh run ID; old checkpoints cannot be reused."
        }
    } else {
        $oldCheckpoints = @(Get-ChildItem $EvidenceDirectory -Filter '*.json')
        if ($oldCheckpoints.Count -gt 0) {
            throw "Unbound migration evidence exists. Use a new run ID to prevent stale checkpoints."
        }
        Write-MigrationJson $path ([ordered]@{ sha256 = $fingerprint })
    }
}

function Get-MigrationPython {
    param([string]$RepoRoot)
    foreach ($root in @($RepoRoot, (Get-PrimaryRepoRoot))) {
        foreach ($relative in @('.venv/bin/python', '.venv/Scripts/python.exe')) {
            $candidate = Join-Path $root $relative
            if (Test-Path $candidate) { return $candidate }
        }
    }
    foreach ($name in @('python3', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    throw 'Restore the repository Python environment before migrating data.'
}
