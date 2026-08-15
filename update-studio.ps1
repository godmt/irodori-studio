[CmdletBinding()]
param(
    [switch]$ForceSync
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$studioRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\', '/')

function Invoke-GitChecked([string[]]$Arguments) {
    Push-Location $studioRoot
    try {
        & git @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "git failed with exit code $LASTEXITCODE"
        }
    }
    finally { Pop-Location }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git was not found. Install Git for Windows before updating a source checkout."
}

Push-Location $studioRoot
try {
    $repositoryRootOutput = @(& git rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -ne 0 -or $repositoryRootOutput.Count -eq 0) {
        throw "This folder is not a Git source checkout. Windows release packages must be updated by downloading the latest release ZIP."
    }
    $repositoryRoot = [System.IO.Path]::GetFullPath([string]$repositoryRootOutput[-1]).TrimEnd('\', '/')
    if (-not $repositoryRoot.Equals($studioRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Run update-studio.ps1 from the Irodori Studio repository root."
    }

    $workingTreeChanges = @(& git status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the Git working tree."
    }
}
finally { Pop-Location }

if ($workingTreeChanges.Count -gt 0) {
    throw "The Studio source checkout has uncommitted changes. Commit or discard them before updating so user edits are not overwritten."
}

Write-Host "[update] Downloading the latest Irodori Studio source" -ForegroundColor Cyan
Invoke-GitChecked @("pull", "--ff-only")

$setupArguments = @{ SetupOnly = $true }
if ($ForceSync) {
    $setupArguments.ForceSync = $true
}

Write-Host "[update] Synchronizing changed dependencies and the Studio frontend" -ForegroundColor Cyan
& (Join-Path $studioRoot "start-studio.ps1") @setupArguments
if ($LASTEXITCODE -ne 0) {
    throw "Studio setup failed with exit code $LASTEXITCODE"
}

Write-Host "[update] Complete. Start Studio with .\start-studio.ps1 or start-studio.cmd." -ForegroundColor Green
