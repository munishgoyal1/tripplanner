# Read which validation gates the lane scripts should run.
#
# The gates are declared as VALIDATION_GATE_<NAME> entries in
# config/environments/local.env, beside every other checked-in non-secret knob,
# so there is one configuration file to look in rather than a dedicated one for
# this. scripts/dev/validation_policy.py reads the same keys for multiagent.py.
# One file, one decision, three call sites that cannot drift apart.
#
# Because the declarations are environment-variable names, a real environment
# variable overrides the file for free -- which is how -FullSuites and the
# per-gate overrides work.
#
# Nothing here deletes a gate: a suspended gate's command still sits at its call
# site wrapped in Test-GateEnabled, so restoring it is a config edit and never a
# code change.

# $PSScriptRoot is <repo>/scripts/dev/lib, so the repository root is three
# levels up, not two.
$script:ValidationPolicyRepoRoot =
    Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$script:ValidationPolicyPath =
    Join-Path $script:ValidationPolicyRepoRoot "config/environments/local.env"
$script:ValidationPolicyCache = $null
$script:ValidationGates = @("lint", "typecheck", "build", "pytest", "vitest")

function Get-ValidationGateVariable {
    param([Parameter(Mandatory = $true)][string]$Gate)
    return "VALIDATION_GATE_$($Gate.ToUpperInvariant())"
}

function Get-ValidationPolicy {
    <#
    .SYNOPSIS
      The VALIDATION_GATE_* declarations from config/environments/local.env.
    .DESCRIPTION
      Cached per process. A missing or unreadable file returns an empty table,
      and every caller treats that as "run everything" -- see Test-GateEnabled.
    #>
    if ($null -ne $script:ValidationPolicyCache) { return $script:ValidationPolicyCache }

    $policy = @{}
    if (-not (Test-Path -LiteralPath $script:ValidationPolicyPath -PathType Leaf)) {
        Write-Warning "config/environments/local.env not found; every validation gate will run."
        $script:ValidationPolicyCache = $policy
        return $policy
    }

    foreach ($line in Get-Content -LiteralPath $script:ValidationPolicyPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or $trimmed -notmatch "=") { continue }
        $key, $value = $trimmed -split "=", 2
        $key = $key.Trim()
        if (-not $key.StartsWith("VALIDATION_GATE_")) { continue }
        # Trim an inline comment and surrounding quotes.
        $value = ($value -split "#", 2)[0].Trim().Trim("'").Trim('"').ToLowerInvariant()
        $policy[$key] = $value
    }

    $script:ValidationPolicyCache = $policy
    return $policy
}

function Test-GateEnabled {
    <#
    .SYNOPSIS
      True when the named gate should run in this invocation.
    .DESCRIPTION
      Resolution order, in full:
        1. TRIPPLANNER_FULL_SUITES=1 -> every gate runs (what -FullSuites sets,
           and what child processes inherit).
        2. A VALIDATION_GATE_<NAME> environment variable, if one is set.
        3. The same key in config/environments/local.env.
        4. Anything else -- unknown gate name, missing file, unrecognised value
           -- means run. Fail closed: a policy we cannot read must never be the
           reason a gate silently stops protecting the tree.

      Only the exact word "suspended" skips a gate, so a typo runs the check
      rather than quietly disabling it.
    #>
    param([Parameter(Mandatory = $true)][string]$Gate)

    if ($env:TRIPPLANNER_FULL_SUITES -eq "1") { return $true }

    $variable = Get-ValidationGateVariable -Gate $Gate
    $override = [System.Environment]::GetEnvironmentVariable($variable)
    if ($null -ne $override) { return ($override.Trim().ToLowerInvariant() -ne "suspended") }

    $policy = Get-ValidationPolicy
    if (-not $policy.ContainsKey($variable)) { return $true }
    return ($policy[$variable] -ne "suspended")
}

function Write-SuspendedGateNotice {
    <#
    .SYNOPSIS
      Announce, in place of the gate, that it did not run.
    .DESCRIPTION
      Printed instead of the usual cyan "[check] <gate>" line so no transcript
      ever reads as though the check ran and passed. Yellow on purpose: the
      "[check]" lines are cyan, and someone scanning a long log by colour must
      not confuse "skipped" with "passed".
    #>
    param([Parameter(Mandatory = $true)][string]$Gate)

    $variable = Get-ValidationGateVariable -Gate $Gate
    Write-Host "[SUSPENDED] $Gate did NOT run ($variable in config/environments/local.env)." -ForegroundColor Yellow
    Write-Host "[SUSPENDED]   A green result here does NOT mean $Gate passes." -ForegroundColor Yellow
    Write-Host "[SUSPENDED]   Suites: pwsh scripts/dev/suite-health.ps1  |  Debt: scripts/dev/test-health-baseline.json" -ForegroundColor Yellow
    Write-Host "[SUSPENDED]   Re-enable: set $variable=required, or pass -FullSuites for one run." -ForegroundColor Yellow
}

function Enable-FullSuitesForThisRun {
    <#
    .SYNOPSIS
      Force every gate on for this process and everything it launches.
    .DESCRIPTION
      -FullSuites calls this instead of threading a parameter through every
      nested script call. full-2way-sync.ps1 invokes sandbox.ps1, and
      sync-across-master-sbx.ps1 invokes it again; an environment variable
      reaches all of them without touching a single call site, and reaches
      multiagent.py's Python reader on the same terms.

      Returns the previous value so the caller can restore it in a finally block.
    #>
    $previous = $env:TRIPPLANNER_FULL_SUITES
    $env:TRIPPLANNER_FULL_SUITES = "1"
    return $previous
}
