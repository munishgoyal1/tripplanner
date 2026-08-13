#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Apply portable developer settings to the current VS Code user profile.

.DESCRIPTION
  Merges repository-owned VS Code settings without deleting unrelated settings,
  installs global Copilot instruction files, and optionally installs missing
    developer tools with winget on Windows. Existing VS Code settings are backed
    up before a changed file is written.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$InstallTools,
    [switch]$InstallExtensions
)

$ErrorActionPreference = "Stop"

function Merge-JsonSettings {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )

    $portable = Get-Content $SourcePath -Raw | ConvertFrom-Json
    if (Test-Path $DestinationPath) {
        try {
            $current = Get-Content $DestinationPath -Raw | ConvertFrom-Json
        } catch {
            throw "Cannot parse existing JSON settings at $DestinationPath. No changes were made."
        }
    } else {
        $current = [pscustomobject]@{}
    }

    foreach ($property in $portable.PSObject.Properties) {
        $existing = $current.PSObject.Properties[$property.Name]
        if ($null -ne $existing) {
            $existing.Value = $property.Value
        } else {
            $current | Add-Member -NotePropertyName $property.Name -NotePropertyValue $property.Value
        }
    }

    $rendered = $current | ConvertTo-Json -Depth 20
    $existingText = if (Test-Path $DestinationPath) {
        (Get-Content $DestinationPath -Raw).Trim()
    } else {
        ""
    }
    if ($existingText -eq $rendered.Trim()) {
        Write-Host "[ok] VS Code settings already match"
        return
    }

    if ($PSCmdlet.ShouldProcess($DestinationPath, "Merge portable VS Code settings")) {
        $destinationDirectory = Split-Path -Parent $DestinationPath
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        if (Test-Path $DestinationPath) {
            $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
            Copy-Item $DestinationPath "$DestinationPath.$timestamp.backup"
        }
        Set-Content -Path $DestinationPath -Value $rendered -Encoding UTF8
        Write-Host "[applied] VS Code settings"
    }
}

function Install-CopilotInstructions {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDirectory,
        [Parameter(Mandatory = $true)][string]$DestinationDirectory
    )

    foreach ($source in Get-ChildItem $SourceDirectory -Filter "*.instructions.md") {
        $destination = Join-Path $DestinationDirectory $source.Name
        $sourceText = Get-Content $source.FullName -Raw
        $destinationText = if (Test-Path $destination) {
            Get-Content $destination -Raw
        } else {
            ""
        }
        if ($sourceText -eq $destinationText) {
            Write-Host "[ok] Copilot instruction $($source.Name) already matches"
            continue
        }
        if ($PSCmdlet.ShouldProcess($destination, "Install global Copilot instruction")) {
            New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
            Copy-Item $source.FullName $destination -Force
            Write-Host "[applied] Copilot instruction $($source.Name)"
        }
    }
}

function Install-DeclaredTools {
    param([Parameter(Mandatory = $true)][string]$ManifestPath)

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is unavailable. Install Windows App Installer, then rerun with -InstallTools."
    }

    $manifest = Import-PowerShellDataFile $ManifestPath
    foreach ($package in $manifest.Packages) {
        if (Get-Command $package.Command -ErrorAction SilentlyContinue) {
            Write-Host "[ok] $($package.Name)"
            continue
        }
        if ($PSCmdlet.ShouldProcess($package.Id, "Install $($package.Name) with winget")) {
            & winget install --id $package.Id --exact --accept-package-agreements `
                --accept-source-agreements --silent
            if ($LASTEXITCODE -ne 0) {
                throw "winget could not install $($package.Name)."
            }
            Write-Host "[installed] $($package.Name)"
        }
    }
}

function Install-VsCodeExtensions {
    param([Parameter(Mandatory = $true)][string]$ManifestPath)

    . (Join-Path $PSScriptRoot "../scripts/dev/lib/vscode-cli.ps1")
    $code = Resolve-VsCodeCli
    if (-not $code) {
        throw "The VS Code command 'code' was not found. Install VS Code, then rerun."
    }

    $installed = @(& $code --list-extensions)
    if ($LASTEXITCODE -ne 0) {
        throw "VS Code could not list installed extensions."
    }
    foreach ($extension in Get-Content $ManifestPath) {
        $extension = $extension.Trim()
        if (-not $extension -or $extension.StartsWith("#")) {
            continue
        }
        if ($installed -contains $extension) {
            Write-Host "[ok] VS Code extension $extension"
            continue
        }
        $extensionLocation = @(& $code --locate-extension $extension)
        if ($LASTEXITCODE -ne 0) {
            throw "VS Code could not locate extension $extension."
        }
        if ($extensionLocation.Count -gt 0 -and
            -not [string]::IsNullOrWhiteSpace([string]$extensionLocation[0])) {
            Write-Host "[ok] Built-in VS Code extension $extension"
            continue
        }
        if ($PSCmdlet.ShouldProcess($extension, "Install VS Code extension")) {
            & $code --install-extension $extension
            if ($LASTEXITCODE -ne 0) {
                throw "VS Code could not install extension $extension."
            }
            Write-Host "[installed] VS Code extension $extension"
        }
    }
}

if ($IsMacOS) {
    $vscodeUserDirectory = Join-Path $HOME "Library/Application Support/Code/User"
} elseif ($env:APPDATA) {
    $vscodeUserDirectory = Join-Path $env:APPDATA "Code\User"
} else {
    throw "Cannot locate the VS Code user profile on this operating system."
}

Merge-JsonSettings `
    -SourcePath (Join-Path $PSScriptRoot "vscode\settings.json") `
    -DestinationPath (Join-Path $vscodeUserDirectory "settings.json")
Install-CopilotInstructions `
    -SourceDirectory (Join-Path $PSScriptRoot "github-copilot\instructions") `
    -DestinationDirectory (Join-Path $vscodeUserDirectory "prompts")

if ($InstallTools) {
    if ($IsMacOS) {
        throw "Use brew bundle --file devconfigs/macos/Brewfile to install macOS tools."
    }
    Install-DeclaredTools (Join-Path $PSScriptRoot "windows\packages.psd1")
}
if ($InstallExtensions) {
    Install-VsCodeExtensions (Join-Path $PSScriptRoot "vscode\extensions.txt")
}

Write-Host "Portable developer configuration is current."