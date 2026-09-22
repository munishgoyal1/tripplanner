# Shared Windows discovery for both machine setup entry points.
function Get-SetupPythonPaths {
    foreach ($base in @($env:LOCALAPPDATA, $env:ProgramFiles)) {
        if (-not $base) { continue }
        foreach ($relative in @("Programs/Python/Python313/python.exe", "Python313/python.exe")) {
            $candidate = Join-Path $base $relative
            if (Test-Path $candidate -PathType Leaf) { $candidate }
        }
    }
}

function Add-SetupToolPaths {
    $directories = @()
    if ($env:LOCALAPPDATA) {
        $directories += Join-Path $env:LOCALAPPDATA "Programs/Microsoft VS Code/bin"
    }
    if ($env:ProgramFiles) {
        foreach ($relative in @("Microsoft VS Code/bin", "Docker/Docker/resources/bin",
            "PowerShell/7", "Git/cmd", "nodejs", "GitHub CLI",
            "Microsoft SDKs/Azure/CLI2/wbin")) {
            $directories += Join-Path $env:ProgramFiles $relative
        }
    }
    foreach ($directory in $directories) {
        if (Test-Path $directory -PathType Container) {
            $env:Path += [IO.Path]::PathSeparator + $directory
        }
    }
}

function Assert-SetupPackageMissing {
    param([string]$Package)

    & winget list --id $Package --exact --accept-source-agreements --disable-interactivity *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "$Package is installed but its required CLI/version is unavailable. Repair PATH or the installation and rerun; setup will not reinstall it."
    }
    # APPINSTALLER_CLI_ERROR_NO_APPLICATIONS_FOUND is the only safe install signal.
    if ($LASTEXITCODE -notin @(-1978335212, 2316632084)) {
        throw "Could not determine whether $Package is installed (winget exit $LASTEXITCODE). No installation attempted."
    }
}
