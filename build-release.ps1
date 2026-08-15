[CmdletBinding()]
param(
    [string]$Version,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "artifacts"),
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = $PSScriptRoot
$packageMetadata = Get-Content -Raw -LiteralPath (Join-Path $repositoryRoot "package.json") | ConvertFrom-Json
$declaredVersion = [string]$packageMetadata.version
$requestedVersion = if ([string]::IsNullOrWhiteSpace($Version)) {
    $declaredVersion
} else {
    $Version.Trim().TrimStart("v")
}

if ($requestedVersion -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
    throw "Version '$requestedVersion' is not a supported semantic version."
}
if ($requestedVersion -ne $declaredVersion) {
    throw "Requested version $requestedVersion does not match package.json version $declaredVersion."
}

function Invoke-Checked([string]$Command, [string[]]$Arguments) {
    Push-Location $repositoryRoot
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Command failed with exit code $LASTEXITCODE"
        }
    }
    finally { Pop-Location }
}

if (-not $SkipBuild) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found. Install Node.js 20 or later to build a release package."
    }
    Invoke-Checked "npm" @("ci")
    Invoke-Checked "npm" @("run", "build")
}

$clientIndex = Join-Path $repositoryRoot "dist\client\index.html"
if (-not (Test-Path -LiteralPath $clientIndex -PathType Leaf)) {
    throw "dist/client/index.html is missing. Build the frontend before packaging."
}

$packageName = "irodori-studio-v$requestedVersion-windows"
$outputRoot = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $OutputDirectory))
}
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$temporaryRoot = Join-Path $temporaryBase ("irodori-studio-release-" + [guid]::NewGuid().ToString("N"))
$packageRoot = Join-Path $temporaryRoot $packageName
New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

function Copy-ReleaseFile([string]$RelativePath) {
    $source = Join-Path $repositoryRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required release file is missing: $RelativePath"
    }
    $destination = Join-Path $packageRoot $RelativePath
    $destinationDirectory = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}

function Copy-ReleaseTree([string]$RelativePath) {
    $sourceRoot = Join-Path $repositoryRoot $RelativePath
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
        throw "Required release directory is missing: $RelativePath"
    }
    $sourcePrefixLength = $sourceRoot.TrimEnd('\', '/').Length + 1
    Get-ChildItem -LiteralPath $sourceRoot -Recurse -File |
        Where-Object {
            $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
            $_.Extension -notin @('.pyc', '.pyo')
        } |
        ForEach-Object {
            $childRelativePath = $_.FullName.Substring($sourcePrefixLength)
            $destination = Join-Path (Join-Path $packageRoot $RelativePath) $childRelativePath
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $destination
        }
}

$releaseFiles = @(
    "CHANGELOG.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "server.py",
    "setup-studio.ps1",
    "start-studio.cmd",
    "start-studio.ps1"
)
$releaseDirectories = @(
    "dist\client",
    "studio_backend",
    "third_party\aica-corpus"
)

try {
    foreach ($releaseFile in $releaseFiles) { Copy-ReleaseFile $releaseFile }
    foreach ($releaseDirectory in $releaseDirectories) { Copy-ReleaseTree $releaseDirectory }

    $readme = Get-Content -Raw -LiteralPath (Join-Path $repositoryRoot "README.md")
    $onlineDocuments = @(
        "AGENTS.md",
        "DESIGN.md",
        "docs/DEVELOPMENT.md",
        "docs/ROADMAP.md",
        "docs/VOICEVOX_API_COMPATIBILITY.md"
    )
    foreach ($onlineDocument in $onlineDocuments) {
        $onlineUrl = "https://github.com/godmt/irodori-studio/blob/v$requestedVersion/$onlineDocument"
        $readme = $readme.Replace("]($onlineDocument)", "]($onlineUrl)")
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $packageRoot "README.md"),
        $readme,
        (New-Object System.Text.UTF8Encoding($false))
    )

    $forbiddenPaths = @("AGENTS.md", "DESIGN.md", "docs", "src", "tests", ".github", "workspace", ".studio")
    foreach ($forbiddenPath in $forbiddenPaths) {
        if (Test-Path -LiteralPath (Join-Path $packageRoot $forbiddenPath)) {
            throw "Development-only path was staged unexpectedly: $forbiddenPath"
        }
    }

    $zipPath = Join-Path $outputRoot "$packageName.zip"
    $checksumPath = "$zipPath.sha256"
    if (Test-Path -LiteralPath $zipPath -PathType Leaf) { Remove-Item -LiteralPath $zipPath -Force }
    if (Test-Path -LiteralPath $checksumPath -PathType Leaf) { Remove-Item -LiteralPath $checksumPath -Force }

    Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
    $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumLine = "$hash  $([System.IO.Path]::GetFileName($zipPath))$([Environment]::NewLine)"
    [System.IO.File]::WriteAllText($checksumPath, $checksumLine, (New-Object System.Text.UTF8Encoding($false)))

    Write-Host "[release] Package: $zipPath" -ForegroundColor Green
    Write-Host "[release] SHA-256: $checksumPath" -ForegroundColor Green
}
finally {
    $resolvedTemporaryRoot = [System.IO.Path]::GetFullPath($temporaryRoot)
    $safeTemporaryPrefix = $temporaryBase.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (
        $resolvedTemporaryRoot.StartsWith($safeTemporaryPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedTemporaryRoot).StartsWith("irodori-studio-release-")
    ) {
        Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
