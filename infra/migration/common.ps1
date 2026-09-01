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
        [switch]$Capture
    )

    Write-Host "[$Description] $Executable $($Arguments -join ' ')"
    $output = & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
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