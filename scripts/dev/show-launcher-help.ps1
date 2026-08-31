[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet(
        "full-2way-sync",
        "resolve-recorded-conflicts",
        "run-latest-master",
        "start-dev-spa",
        "sync-across-master-sbx",
        "sync-sbxs-from-master",
        "emergency-bringdown",
        "emergency-control",
        "azure-services-control",
        "google-maps-control",
        "google-places-control",
        "google-runtime-control"
    )]
    [string]$Launcher
)

$help = @{
    "emergency-bringdown" = @"
Emergency-Bringdown - immediately stop or restore all hosted Tripplanner serving.

Usage: Emergency-Bringdown [status|down|up|stop|start] [all|canary|prod] [approval]

  status  Report canary and production app/job state without changing it (default).
  down    Stop Container Apps, suspend recurring jobs, and stop active executions.
          No approval is required. Alias: stop.
  up      Start Container Apps and restore remembered job schedules.
          Requires APPROVE_AZURE_SPEND. Alias: start.

Examples:
  Emergency-Bringdown
  Emergency-Bringdown down all
  Emergency-Bringdown down prod
  Emergency-Bringdown up all APPROVE_AZURE_SPEND

This is a reversible serving stop, not a deletion or complete cost stop. It leaves
provider access, databases, resources, DNS, domains, and fixed charges unchanged.
Endpoints may still resolve while their Container Apps are stopped.
"@
    "emergency-control" = @"
Emergency-Control - one status and emergency shutdown entry point for Tripplanner services.

Usage: Emergency-Control [status|disable|enable|off|on]
                         [all|google|azure|local|canary|prod]
                         [azure-approval] [google-maps-approval] [google-places-approval]

  status   Read every selected provider state without changing it (default).
  disable  Stop or block every selected service. No approval is required.
  enable   Restore selected services. Each provider retains its spend approval gate.

Examples:
  Emergency-Control
  Emergency-Control status prod
  Emergency-Control disable all
  Emergency-Control disable google
  Emergency-Control enable azure APPROVE_AZURE_SPEND
  Emergency-Control enable all APPROVE_AZURE_SPEND APPROVE_GOOGLE_MAPS_SPEND APPROVE_GOOGLE_PLACES_SPEND

No resource or data is deleted. Disable is best-effort across all selected controls
and returns a failure if any control could not be changed. Provisioned Azure resources
can retain fixed charges after access is blocked. Profile changes need a local restart
or hosted deployment; no deployment is performed by this launcher.
"@
    "full-2way-sync" = @"
Full-2Way-Sync - converge committed work across master and local lanes.

Usage: Full-2Way-Sync [all|sbx] [-BaseBranch master] [-AlwaysValidate] [-PullOnly] [-WhatIf]

  all              Include sandboxes, multiagent worktrees, and unattached branches (default).
  sbx              Include registered sandboxes only.
  -PullOnly        Bring lanes up to master without publishing lane work.
  -AlwaysValidate  Validate even documentation-only merges.
  -WhatIf          Preview changes.

Examples:
  Full-2Way-Sync -WhatIf
  Full-2Way-Sync sbx -PullOnly
"@
    "resolve-recorded-conflicts" = @"
Resolve-All-Recorded-Conflicts - replay Git rerere resolutions in pending worktree merges.

Usage: Resolve-All-Recorded-Conflicts [-WhatIf]

Scans every attached worktree. It does not fetch, start or abort merges, or push branches.
New conflicts remain unresolved and are reported.

Example: Resolve-All-Recorded-Conflicts -WhatIf
"@
    "sync-across-master-sbx" = @"
Sync-Across-MasterSbx - merge sandbox work to master, then refresh every sandbox.

Usage: Sync-Across-MasterSbx [sandbox|all] [-BaseBranch master] [-WhatIf]

  sandbox          Slot number, full slug, or short name. Default: all registered sandboxes.
  -WhatIf          Preview the cross-lane synchronization.

This is a guarded publish operation and requires typing APPROVE_SANDBOX_TO_MASTER.

Examples:
  Sync-Across-MasterSbx -WhatIf
  Sync-Across-MasterSbx 2
"@
    "sync-sbxs-from-master" = @"
Sync-Sbxs-FromMaster - fast-forward primary master, then refresh registered sandboxes.

Usage: Sync-Sbxs-FromMaster [sandbox] [-ValidateOnly] [-WhatIf]

  sandbox        Optional slot number, full slug, or short name. Omit for every sandbox.
  -ValidateOnly  Check synchronization without changing branches.
  -WhatIf        Preview sandbox updates.

Examples:
  Sync-Sbxs-FromMaster
  Sync-Sbxs-FromMaster 4 -WhatIf
"@
    "run-latest-master" = @"
Run-Latest-Master - fast-forward primary master and start its canonical local stack.

Usage: Run-Latest-Master [-ValidateOnly] [-Watch] [-Logs] [-BackendOnly|-FrontendOnly]
                         [-NoLabs] [-ApiPort n] [-FrontendPort n] [-LabsPort n]
                         [-CosmosBackend azure|emulator] [-UseCanaryData]

  -ValidateOnly   Check the fast-forward without starting servers.
  -Watch          Enable backend reload and frontend HMR.
  -NoLabs         Skip the UX Labs server.
  -UseCanaryData  Use hosted canary data.

Example: Run-Latest-Master -Watch -NoLabs
"@
    "start-dev-spa" = @"
Start-Dev-Spa - start the local FastAPI, main SPA, Labs, and Inspector stack.

Usage: Start-Dev-Spa [-Watch] [-Logs] [-BackendOnly|-FrontendOnly] [-NoLabs] [-NoInspector]
                     [-ApiPort n] [-FrontendPort n] [-LabsPort n] [-InspectorPort n]
                     [-CosmosBackend azure|emulator] [-CosmosDatabase name] [-UseCanaryData]

  -Watch          Enable backend reload and frontend HMR.
  -BackendOnly    Start only FastAPI. -FrontendOnly starts browser surfaces only.
  -NoLabs         Skip Labs. -NoInspector skips the Quality Inspector.

Example: Start-Dev-Spa -Watch -NoLabs
"@
    "azure-services-control" = @"
Azure-Services-Control - report or control one Azure environment or the whole estate.

Usage: Azure-Services-Control [status|disable|enable|off|on] [all|local|canary|prod] [approval]

  status   Show state and residual billing for one environment or all (default).
  disable  Stop hosted apps/jobs and block environment-owned OpenAI or Redis access.
           The all scope also blocks the shared Cosmos account.
           No approval is required. Alias: off.
  enable   Start hosted apps, restore job schedules, and reopen service access.
           Requires APPROVE_AZURE_SPEND. Alias: on.

Examples:
  Azure-Services-Control status prod
  Azure-Services-Control disable prod
  Azure-Services-Control enable prod APPROVE_AZURE_SPEND
  Azure-Services-Control disable all

No resource or data is deleted. Redis, Cosmos, environments, logs, and other
provisioned resources can continue billing while application access is disabled.
Cosmos is shared by all environments, so only the all scope changes its access.
"@
    "google-maps-control" = @"
Google-Maps-Control - control Maps JavaScript, Routes, and Static Maps by environment.

Usage: Google-Maps-Control [status|apply|enable|disable|on|off] [all|local|canary|prod] [approval]

  status   Compare ENABLE_GOOGLE_MAPS with GCP Service Usage (default).
  apply    Synchronize GCP from the checked-in profile flag.
  disable  Set the profile off and immediately disable the GCP services. Alias: off.
  enable   Set the profile on and enable services. Alias: on. Requires approval.

Examples:
  Google-Maps-Control status all
  Google-Maps-Control disable prod
  Google-Maps-Control enable local APPROVE_GOOGLE_MAPS_SPEND

No application deployment is performed.
"@
    "google-places-control" = @"
Google-Places-Control - control paid Google Places access by environment.

Usage: Google-Places-Control [status|apply|enable|disable|on|off] [all|local|canary|prod] [approval]

  status   Compare ENABLE_GOOGLE_PLACES with GCP Service Usage (default).
  apply    Synchronize GCP from the checked-in profile flag.
  disable  Set the profile off and immediately disable Places. Alias: off.
  enable   Set the profile on and enable Places. Alias: on. Requires approval.

Examples:
  Google-Places-Control status all
  Google-Places-Control disable prod
  Google-Places-Control enable local APPROVE_GOOGLE_PLACES_SPEND

No application deployment is performed.
"@
    "google-runtime-control" = @"
Google-Runtime-Control - apply Google access to hosted apps without a full deployment.

Usage: Google-Runtime-Control [status|apply|enable|disable|on|off] [all|canary|prod] [maps-approval] [places-approval]

  status   Compare hosted runtime flags, checked-in profiles, and GCP Service Usage.
  apply    Create a same-image revision from the checked-in profile flags.
  disable  Gracefully stop app calls, then disable the GCP services. Alias: off.
  enable   Enable GCP services, then create a serving same-image revision. Alias: on.
           Requires both Google spend approvals.

Examples:
  Google-Runtime-Control status all
  Google-Runtime-Control disable prod
  Google-Runtime-Control enable canary APPROVE_GOOGLE_MAPS_SPEND APPROVE_GOOGLE_PLACES_SPEND
  Google-Runtime-Control apply prod APPROVE_GOOGLE_MAPS_SPEND APPROVE_GOOGLE_PLACES_SPEND

No image is built or changed and no Bicep deployment is run. Azure Container Apps
creates a new revision because environment variables are revision-scoped.
"@
}

Write-Host $help[$Launcher]