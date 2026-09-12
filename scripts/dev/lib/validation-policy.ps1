# Read the shared validation-gate policy.
#
# Three call sites decide whether to run a gate: sandbox.ps1 (-Merge/-Promote),
# full-2way-sync.ps1 (branch-lane publish), and multiagent.py (coordinator
# integration). Keeping the decision in scripts/dev/validation-policy.json means
# flipping a gate is one word in one checked-in file rather than three edits that
# drift apart. multiagent.py reads the same file through validation_policy.py.
#
# Nothing here deletes a gate: a suspended gate's command still lives at its call
# site, wrapped in Test-GateEnabled, so restoring it is a policy edit and never a
# code change.

$script:ValidationPolicyPath = Join-Path (Split-Path -Parent $PSScriptRoot) "validation-policy.json"
$script:ValidationPolicyCache = $null

function Get-ValidationPolicy {
    <#
    .SYNOPSIS
      Parsed validation-policy.json, or $null when it cannot be read.
    .DESCRIPTION
      Cached per process. A missing or malformed file returns $null, and every
      caller treats that as "run everything" -- see Test-GateEnabled.
    #>
    if ($null -ne $script:ValidationPolicyCache) { return $script:ValidationPolicyCache }

    if (-not (Test-Path -LiteralPath $script:ValidationPolicyPath -PathType Leaf)) {
        Write-Warning "validation-policy.json not found; every validation gate will run."
        return $null
    }
    try {
        $script:ValidationPolicyCache = Get-Content -LiteralPath $script:ValidationPolicyPath -Raw |
            ConvertFrom-Json
    } catch {
        Write-Warning "validation-policy.json is unreadable ($($_.Exception.Message)); every validation gate will run."
        return $null
    }
    return $script:ValidationPolicyCache
}

function Test-GateEnabled {
    <#
    .SYNOPSIS
      True when the named gate should run in this invocation.
    .DESCRIPTION
      Resolution order, in full:
        1. TRIPPLANNER_FULL_SUITES=1  -> every gate runs (the per-run override
           that -FullSuites sets, and that child processes inherit).
        2. The gate's "state" in validation-policy.json: "suspended" means skip.
        3. Anything else -- unknown gate name, missing file, malformed JSON --
           means run. Fail closed: a policy we cannot read must never be the
           reason a gate silently stops protecting the tree.
    #>
    param([Parameter(Mandatory = $true)][string]$Gate)

    if ($env:TRIPPLANNER_FULL_SUITES -eq "1") { return $true }

    $policy = Get-ValidationPolicy
    if (-not $policy) { return $true }

    $entry = $policy.gates.$Gate
    if (-not $entry) { return $true }
    return ($entry.state -ne "suspended")
}

function Write-SuspendedGateNotice {
    <#
    .SYNOPSIS
      Announce, in place of the gate, that it did not run.
    .DESCRIPTION
      Printed instead of the usual cyan "[check] <gate>" line so no transcript
      ever reads as though the suite ran and passed. Yellow on purpose: the
      "[check]" lines are cyan, and someone scanning a long log by colour must
      not confuse "skipped" with "passed".
    #>
    param([Parameter(Mandatory = $true)][string]$Gate)

    $policy = Get-ValidationPolicy
    $entry = if ($policy) { $policy.gates.$Gate } else { $null }
    $since = if ($entry -and $entry.since) { ", suspended $($entry.since)" } else { "" }
    $health = if ($policy -and $policy.health_check) { $policy.health_check } else { "scripts/dev/suite-health.ps1" }
    $baseline = if ($policy -and $policy.baseline) { $policy.baseline } else { "scripts/dev/test-health-baseline.json" }

    Write-Host "[SUSPENDED] $Gate is NOT part of this gate (scripts/dev/validation-policy.json$since)." -ForegroundColor Yellow
    Write-Host "[SUSPENDED]   A green result here does NOT mean the $Gate suite passes." -ForegroundColor Yellow
    Write-Host "[SUSPENDED]   Health: pwsh $health  |  Known debt: $baseline  |  Override: -FullSuites" -ForegroundColor Yellow
    if ($entry -and $entry.reason) {
        Write-Host "[SUSPENDED]   Why: $($entry.reason)" -ForegroundColor Yellow
    }
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
