[CmdletBinding()]
param(
    [ValidateSet("List", "Create", "Open")]
    [string]$Action = "List",
    [string]$Name,
    [string]$Ref = "HEAD",
    [string]$Tag,
    [string]$Path
)

$ErrorActionPreference = "Stop"
$repoRoot = (git rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) {
    throw "Run this command from the tripplanner repository."
}

Push-Location $repoRoot
try {
    if ($Action -eq "List") {
        git for-each-ref --sort=-creatordate --format="%(refname:short) | %(*objectname:short) | %(creatordate:short) | %(subject)" refs/tags/ui-stable/
        exit $LASTEXITCODE
    }

    if ($Action -eq "Create") {
        if (-not $Name -or $Name -notmatch "^[a-z0-9][a-z0-9-]*$") {
            throw "Provide -Name using lowercase letters, numbers, and hyphens."
        }
        if ($Ref -eq "HEAD" -and (git status --porcelain)) {
            throw "Commit and push the stable milestone before creating its snapshot."
        }

        $commit = (git rev-parse --verify "$Ref^{commit}" 2>$null)
        if (-not $commit) {
            throw "Ref '$Ref' does not resolve to a commit."
        }
        $snapshotTag = "ui-stable/$(Get-Date -Format 'yyyy-MM-dd')-$Name"
        if (git tag --list $snapshotTag) {
            throw "Snapshot '$snapshotTag' already exists. Stable UI tags are immutable."
        }

        git tag -a $snapshotTag $commit -m "Stable UI snapshot: $Name"
        if ($LASTEXITCODE -ne 0) { throw "Failed to create snapshot tag." }
        git push origin "refs/tags/$snapshotTag"
        if ($LASTEXITCODE -ne 0) { throw "Snapshot was created locally but could not be pushed." }
        Write-Host "Preserved $snapshotTag at $($commit.Substring(0, 7))."
        exit 0
    }

    if (-not $Tag -or $Tag -notlike "ui-stable/*") {
        throw "Provide a stable UI tag with -Tag ui-stable/<name>."
    }
    if (-not (git tag --list $Tag)) {
        throw "Snapshot '$Tag' does not exist locally. Run git fetch --tags first."
    }

    if (-not $Path) {
        $folderName = ($Tag -replace "^ui-stable/", "tripplanner-ui-")
        $Path = Join-Path (Split-Path $repoRoot -Parent) $folderName
    }
    if (Test-Path $Path) {
        throw "Preview path '$Path' already exists. Remove its worktree or choose -Path."
    }

    git worktree add --detach $Path $Tag
    if ($LASTEXITCODE -ne 0) { throw "Failed to open the stable UI snapshot." }
    Write-Host "Opened $Tag at $Path. The primary workspace was not changed."
}
finally {
    Pop-Location
}