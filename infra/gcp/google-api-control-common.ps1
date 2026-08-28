function Get-GoogleApiCapability {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("places", "maps")]
        [string]$Name
    )

    if ($Name -eq "places") {
        return [pscustomobject]@{
            Name = "Places"
            Flag = "ENABLE_GOOGLE_PLACES"
            Approval = "APPROVE_GOOGLE_PLACES_SPEND"
            Services = @("places.googleapis.com")
        }
    }
    return [pscustomobject]@{
        Name = "Maps"
        Flag = "ENABLE_GOOGLE_MAPS"
        Approval = "APPROVE_GOOGLE_MAPS_SPEND"
        Services = @(
            "maps-backend.googleapis.com",
            "routes.googleapis.com",
            "static-maps-backend.googleapis.com"
        )
    }
}

function Get-GoogleApiProfilePath {
    param([Parameter(Mandatory)][string]$Environment)

    return Join-Path $PSScriptRoot "../../config/environments/$Environment.env"
}

function Get-GoogleApiDesiredState {
    param(
        [Parameter(Mandatory)][string]$Environment,
        [Parameter(Mandatory)][string]$Flag
    )

    $path = Get-GoogleApiProfilePath -Environment $Environment
    $match = [regex]::Match((Get-Content $path -Raw), "(?m)^$([regex]::Escape($Flag))=([01])$")
    if (-not $match.Success) {
        throw "$Flag must be set to 0 or 1 in $path."
    }
    return $match.Groups[1].Value -eq "1"
}

function Set-GoogleApiDesiredState {
    param(
        [Parameter(Mandatory)][string]$Environment,
        [Parameter(Mandatory)][string]$Flag,
        [Parameter(Mandatory)][bool]$Enabled
    )

    $path = Get-GoogleApiProfilePath -Environment $Environment
    $content = Get-Content $path -Raw
    $pattern = "(?m)^$([regex]::Escape($Flag))=[01]$"
    if (-not [regex]::IsMatch($content, $pattern)) {
        throw "$Flag must be set to 0 or 1 in $path."
    }
    $value = if ($Enabled) { "1" } else { "0" }
    $updated = [regex]::Replace($content, $pattern, "$Flag=$value")
    [System.IO.File]::WriteAllText($path, $updated, [System.Text.UTF8Encoding]::new($false))
}