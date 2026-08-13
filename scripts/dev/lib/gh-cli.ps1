# Resolve the GitHub CLI without depending on PATH.
#
# Same failure as `pwsh` and `code`: a Finder double-click and any shell started
# from inside a `brew` command both get a PATH without Homebrew's bin directory,
# so `gh` is installed and usable while the bare-name lookup fails.

function Resolve-GhCli {
    <#
    .SYNOPSIS
    Return a usable path to the GitHub CLI, or $null when none is installed.
    #>
    [CmdletBinding()]
    param()

    $onPath = Get-Command gh -CommandType Application -ErrorAction SilentlyContinue
    if ($onPath) {
        return $onPath.Source
    }

    $candidates = @()
    if ($IsMacOS) {
        $candidates += "/opt/homebrew/bin/gh"
        $candidates += "/usr/local/bin/gh"
    } elseif ($IsLinux) {
        $candidates += "/usr/bin/gh"
        $candidates += "/usr/local/bin/gh"
        $candidates += "/snap/bin/gh"
    } else {
        if ($env:ProgramFiles) {
            $candidates += (Join-Path $env:ProgramFiles "GitHub CLI\gh.exe")
        }
        if ($env:LOCALAPPDATA) {
            $candidates += (Join-Path $env:LOCALAPPDATA "Programs\GitHub CLI\gh.exe")
        }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    return $null
}

function Get-RequiredGhCli {
    <#
    .SYNOPSIS
    Return an authenticated GitHub CLI path, or throw with the fixing command.
    #>
    [CmdletBinding()]
    param([string]$Verb = "This command")

    $gh = Resolve-GhCli
    if (-not $gh) {
        throw "GitHub CLI 'gh' is required by $Verb. Install it (brew install gh), or open and merge the pull request yourself."
    }
    & $gh auth status --hostname github.com *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI is not authenticated. Run 'gh auth login --hostname github.com --web' before running $Verb."
    }
    return $gh
}
