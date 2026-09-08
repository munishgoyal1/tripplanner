# Resolve a Node.js that satisfies the frontend's engine requirement.
#
# A macOS box often carries an old Node from Node's own installer package in
# /usr/local/bin, which shadows a current Homebrew Node because /usr/local/bin
# comes first on PATH. npm then installs against the wrong runtime and prints a
# wall of EBADENGINE warnings for packages it cannot actually support. Picking
# the interpreter explicitly is the same fix the .command launchers apply to
# PowerShell, for the same reason.

$script:MinimumNodeVersion = [version]"20.19.0"

function Get-NodeVersion {
    param([Parameter(Mandatory = $true)][string]$Path)

    $raw = & $Path --version 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    try {
        return [version](([string]$raw).Trim().TrimStart("v") -replace "-.*$", "")
    } catch {
        return $null
    }
}

function Get-CandidateNodePaths {
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($fixed in @("/opt/homebrew/bin/node", "/usr/local/bin/node")) {
        if (Test-Path -LiteralPath $fixed -PathType Leaf) { $candidates.Add($fixed) }
    }
    # nvm keeps every installed runtime side by side; prefer the newest.
    $nvmRoot = Join-Path $HOME ".nvm/versions/node"
    if (Test-Path -LiteralPath $nvmRoot -PathType Container) {
        Get-ChildItem -LiteralPath $nvmRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object {
                $binary = Join-Path $_.FullName "bin/node"
                if (Test-Path -LiteralPath $binary -PathType Leaf) { $candidates.Add($binary) }
            }
    }
    return $candidates
}

function Use-CompatibleNode {
    <#
    .SYNOPSIS
      Put a Node that meets the minimum version first on PATH for this process.
    #>
    $current = Get-Command node -ErrorAction SilentlyContinue
    if ($current) {
        $version = Get-NodeVersion -Path $current.Source
        if ($version -and $version -ge $script:MinimumNodeVersion) { return }
    }

    foreach ($candidate in Get-CandidateNodePaths) {
        $version = Get-NodeVersion -Path $candidate
        if (-not $version -or $version -lt $script:MinimumNodeVersion) { continue }
        $binDirectory = Split-Path -Parent $candidate
        $env:PATH = "$binDirectory$([System.IO.Path]::PathSeparator)$env:PATH"
        Write-Host "Using Node $version from $binDirectory" -ForegroundColor DarkGray
        return
    }

    $found = if ($current) { Get-NodeVersion -Path $current.Source } else { $null }
    $detail = if ($found) { "found $found" } else { "none found" }
    $hint = if ($IsWindows) { "https://nodejs.org/en/download" } else { "brew install node" }
    Write-Warning (
        "Node $($script:MinimumNodeVersion) or newer is required by the frontend " +
        "($detail). Install it from: $hint"
    )
}
