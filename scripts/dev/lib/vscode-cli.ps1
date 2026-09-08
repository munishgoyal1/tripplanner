# Resolve the VS Code CLI without depending on PATH.
#
# `code` is only on PATH when the shell inherited it from a normal login
# environment. A Finder double-click, and any process started from inside a
# `brew` command, both get a PATH without it — VS Code is installed and usable,
# but the bare-name lookup fails.

function Resolve-VsCodeCli {
    <#
    .SYNOPSIS
    Return a usable path to the VS Code CLI, or $null when none is installed.
    #>
    [CmdletBinding()]
    param()

    $onPath = Get-Command code -CommandType Application -ErrorAction SilentlyContinue
    if ($onPath) {
        return $onPath.Source
    }

    $candidates = @()
    if ($IsMacOS) {
        $candidates += "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
        $candidates += (Join-Path $HOME "Applications/Visual Studio Code.app/Contents/Resources/app/bin/code")
    } elseif ($IsLinux) {
        $candidates += "/usr/share/code/bin/code"
        $candidates += "/snap/bin/code"
    } else {
        if ($env:LOCALAPPDATA) {
            $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Microsoft VS Code\bin\code.cmd")
        }
        if ($env:ProgramFiles) {
            $candidates += (Join-Path $env:ProgramFiles "Microsoft VS Code\bin\code.cmd")
        }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    return $null
}
