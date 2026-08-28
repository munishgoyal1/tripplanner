[CmdletBinding()]
param(
    [ValidateSet("status", "apply", "enable", "disable", "on", "off")]
    [string]$Action = "status",
    [ValidateSet("all", "local", "canary", "prod")]
    [string]$Environment = "all",
    [string]$Approval = ""
)

& "$PSScriptRoot/set-google-api-access.ps1" -Capability maps -Action $Action `
    -Environment $Environment -Approval $Approval