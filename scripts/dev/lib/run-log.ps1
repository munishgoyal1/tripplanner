#!/usr/bin/env pwsh
# Shared "last run" logging. Every entry-point script overwrites one transcript in
# <primary-root>/logs/last-run so any lane, worker, or sandbox can read the latest
# run of any script. Dot-source: . "$PSScriptRoot/lib/run-log.ps1".

function Get-PrimaryRepoRoot {
    # Worktrees keep their own logs/ and no .env.*; runs share the primary checkout's copies.
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $common = & git -C $PSScriptRoot rev-parse --path-format=absolute --git-common-dir 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($common)) {
            return Split-Path -Parent (@($common)[0])
        }
    }
    # scripts/dev/lib -> scripts/dev -> scripts -> repo root
    return Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

function Get-RunLogDirectory {
    $dir = Join-Path (Get-PrimaryRepoRoot) "logs/last-run"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Test-RunLogWritable {
    # A transcript held open by another live run cannot be rotated or reopened.
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    try {
        $stream = [System.IO.File]::Open($Path, "Open", "Write", "None")
        $stream.Dispose()
        return $true
    } catch {
        return $false
    }
}

function Remove-StaleRunLogs {
    # Concurrent runs leave per-process transcripts behind; they are only ever
    # read while diagnosing that run, so a few days is generous.
    param([Parameter(Mandatory = $true)][string]$Directory)
    try {
        Get-ChildItem -LiteralPath $Directory -Filter "*.pid*.log" -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-3) } |
            Remove-Item -Force -ErrorAction SilentlyContinue
    } catch {
        # Logging must never break a run.
    }
}

function Backup-RunLog {
    # Keeps <name>.1.log and <name>.2.log beside the current transcript. Diagnosing
    # a failed run usually needs the run before it, which a bare overwrite destroys.
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Keep = 3
    )
    try {
        if (-not (Test-Path $Path)) { return }
        $dir = Split-Path -Parent $Path
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($Path)
        $ext = [System.IO.Path]::GetExtension($Path)
        $oldest = $Keep - 1
        for ($i = $oldest; $i -ge 1; $i--) {
            $rolling = Join-Path $dir "$stem.$i$ext"
            if (-not (Test-Path $rolling)) { continue }
            if ($i -eq $oldest) {
                Remove-Item $rolling -Force -ErrorAction SilentlyContinue
            } else {
                Move-Item $rolling (Join-Path $dir "$stem.$($i + 1)$ext") -Force -ErrorAction SilentlyContinue
            }
        }
        Move-Item $Path (Join-Path $dir "$stem.1$ext") -Force -ErrorAction SilentlyContinue
    } catch {
        # Logging must never break a run.
    }
}

function Write-RunLog {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host ("[{0}] {1}" -f ((Get-Date).ToUniversalTime().ToString("u")), $Message) -ForegroundColor DarkGray
}

function Invoke-LoggedNative {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$FailureMessage = ""
    )
    # An unpiped native process writes straight to the console handle, so
    # Start-Transcript never sees it. Piping forces PowerShell to read both
    # streams and re-emit them, which is what lands them in the run log.
    $ErrorActionPreference = "Continue"
    $started = Get-Date
    Write-RunLog "exec $FilePath $($ArgumentList -join ' ')"
    & $FilePath @ArgumentList 2>&1 | ForEach-Object { Write-Host $_ }
    $exitCode = $LASTEXITCODE
    Write-RunLog ("exit {0} from {1} after {2:hh\:mm\:ss}" -f $exitCode, $FilePath, ((Get-Date) - $started))
    if ($exitCode -ne 0) {
        if ([string]::IsNullOrWhiteSpace($FailureMessage)) {
            throw "$FilePath exited with code $exitCode."
        }
        throw $FailureMessage
    }
}

function Add-RunLogIndex {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Outcome
    )
    try {
        $line = "{0}`t{1}`t{2}`t{3}" -f `
            ((Get-Date).ToUniversalTime().ToString("u")), $Name, $Outcome, (Get-Location).Path
        Add-Content -Path (Join-Path (Get-RunLogDirectory) "runs.log") -Value $line
    } catch {
        # Logging must never break a run.
    }
}

function Start-RunLog {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($global:TripplannerRunLog) {
        return $null   # a nested script keeps writing to the outer transcript
    }
    $started = Get-Date
    # A caller that already redirects its own output (the detached sandbox runner)
    # opts out, so it never holds the shared transcript open for hours.
    if ($env:TRIPPLANNER_RUN_LOG -eq "0") {
        $global:TripplannerRunLog = [pscustomobject]@{
            Name = $Name; Path = ""; Started = $started; Transcript = $false
        }
        return $null
    }
    $dir = Get-RunLogDirectory
    Remove-StaleRunLogs -Directory $dir
    $path = Join-Path $dir "$Name.log"
    if (-not (Test-RunLogWritable -Path $path)) {
        # Another live run owns the shared name. Take a private file rather than
        # lose this transcript, and leave that run's rotation untouched.
        $path = Join-Path $dir "$Name.pid$PID.log"
    }
    Backup-RunLog -Path $path
    $transcribing = $true
    try {
        Start-Transcript -Path $path -Force -ErrorAction Stop | Out-Null
    } catch {
        Write-Warning "Could not start the run log at ${path}: $($_.Exception.Message)"
        $transcribing = $false
    }
    # Registered even when the transcript failed: a nested script must not then
    # open a second transcript and file this run's output under its own name.
    $global:TripplannerRunLog = [pscustomobject]@{
        Name = $Name; Path = $path; Started = $started; Transcript = $transcribing
    }
    if (-not $transcribing) { return $null }
    $here = (Get-Location).Path
    $branch = & git -C $here branch --show-current 2>$null
    $head = & git -C $here rev-parse --short HEAD 2>$null
    Write-Host "[log]     $path"
    Write-Host "[run]     $Name | $here | $branch@$head | $env:USERNAME"
    Write-Host ("[time]    started {0} ({1} local)" -f `
            $started.ToUniversalTime().ToString("u"), $started.ToString("yyyy-MM-dd HH:mm:ss"))
    Add-RunLogIndex -Name $Name -Outcome "started"
    return $path
}

function Stop-RunLog {
    param([string]$Outcome = "completed")

    $log = $global:TripplannerRunLog
    if (-not $log) { return }
    Write-Host ("[time]    {0} {1} after {2:hh\:mm\:ss}" -f `
            $log.Name, $Outcome, ((Get-Date) - $log.Started))
    Add-RunLogIndex -Name $log.Name -Outcome $Outcome
    if ($log.Transcript) {
        try { Stop-Transcript | Out-Null } catch { }
    }
    $global:TripplannerRunLog = $null
}
