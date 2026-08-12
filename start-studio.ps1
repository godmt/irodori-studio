[CmdletBinding()]
param(
    [string]$IrodoriPath,
    [ValidateSet("cpu", "cu128", "xpu", "rocm")]
    [string]$TorchBackend,
    [switch]$Configure,
    [switch]$SetupOnly,
    [switch]$ForceSync,
    [switch]$NoOpen,
    [switch]$NoAutoloadModel,
    [switch]$NoVoicevoxApi,
    [int]$Port = 8765,
    [int]$VoicevoxPort = 50021,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ServerArgs
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$studioRoot = $PSScriptRoot
$configDirectory = Join-Path $studioRoot ".studio"
$configPath = Join-Path $configDirectory "config.json"

function Test-IrodoriRepository([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    $resolved = [System.IO.Path]::GetFullPath($Path)
    return (
        (Test-Path -LiteralPath (Join-Path $resolved "pyproject.toml") -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $resolved "irodori_tts\inference_runtime.py") -PathType Leaf)
    )
}

function Read-StudioConfig {
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { return $null }
    try { return Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json }
    catch { return $null }
}

function Select-IrodoriRepository {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Select the folder containing the Irodori-TTS repository."
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return $null }
    return $dialog.SelectedPath
}

function Resolve-IrodoriRepository($Config) {
    $sibling = Join-Path (Split-Path -Parent $studioRoot) "Irodori-TTS"
    $configuredPath = if ($null -ne $Config -and $null -ne $Config.PSObject.Properties["irodoriTtsPath"]) {
        [string]$Config.irodoriTtsPath
    } else { "" }
    $candidates = @($IrodoriPath, $env:IRODORI_TTS_PATH, $configuredPath, $sibling)
    if (-not $Configure) {
        foreach ($candidate in $candidates) {
            if (Test-IrodoriRepository $candidate) {
                return [System.IO.Path]::GetFullPath($candidate)
            }
        }
    }
    $selected = if (Test-IrodoriRepository $IrodoriPath) {
        [System.IO.Path]::GetFullPath($IrodoriPath)
    } else {
        Select-IrodoriRepository
    }
    if (-not (Test-IrodoriRepository $selected)) {
        throw "No valid Irodori-TTS repository was selected. Pass the folder containing irodori_tts/inference_runtime.py with -IrodoriPath."
    }
    return [System.IO.Path]::GetFullPath($selected)
}

function Invoke-Checked([string]$Command, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Command failed with exit code $LASTEXITCODE"
        }
    }
    finally { Pop-Location }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found. Install it from https://docs.astral.sh/uv/."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found. Install Node.js 20 or later."
}

$config = Read-StudioConfig
$resolvedIrodoriPath = Resolve-IrodoriRepository $config

if (
    [string]::IsNullOrWhiteSpace($TorchBackend) -and
    $null -ne $config -and
    $null -ne $config.PSObject.Properties["torchBackend"]
) {
    $TorchBackend = [string]$config.torchBackend
}
if ([string]::IsNullOrWhiteSpace($TorchBackend)) {
    $TorchBackend = if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { "cu128" } else { "cpu" }
}

New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
@{
    irodoriTtsPath = $resolvedIrodoriPath
    torchBackend = $TorchBackend
} | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8

$irodoriPython = Join-Path $resolvedIrodoriPath ".venv\Scripts\python.exe"
$backendMatches = $false
if (Test-Path -LiteralPath $irodoriPython -PathType Leaf) {
    $backendProbe = switch ($TorchBackend) {
        "cu128" { "from importlib.metadata import version; raise SystemExit(0 if '+cu128' in version('torch').lower() else 1)" }
        "rocm" { "from importlib.metadata import version; raise SystemExit(0 if '+rocm' in version('torch').lower() else 1)" }
        "xpu" { "from importlib.metadata import version; raise SystemExit(0 if '+xpu' in version('torch').lower() else 1)" }
        default { "from importlib.metadata import version; v=version('torch').lower(); raise SystemExit(0 if '+cpu' in v or '+' not in v else 1)" }
    }
    & $irodoriPython -c $backendProbe 2>$null
    $backendMatches = $LASTEXITCODE -eq 0
}
if ($ForceSync -or -not $backendMatches) {
    Write-Host "[setup] Syncing the Irodori-TTS environment ($TorchBackend)" -ForegroundColor Cyan
    Invoke-Checked "uv" @("sync", "--project", $resolvedIrodoriPath, "--extra", $TorchBackend) $resolvedIrodoriPath
}

& $irodoriPython -c "import fastapi, uvicorn, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[setup] Installing the local Studio server dependencies into the Irodori environment" -ForegroundColor Cyan
    Invoke-Checked "uv" @(
        "pip", "install", "--python", $irodoriPython,
        "fastapi>=0.115", "uvicorn>=0.34", "python-multipart>=0.0.20"
    ) $studioRoot
}

$nodeModules = Join-Path $studioRoot "node_modules"
if (-not (Test-Path -LiteralPath $nodeModules -PathType Container)) {
    Write-Host "[setup] Installing Studio frontend dependencies" -ForegroundColor Cyan
    Invoke-Checked "npm" @("ci") $studioRoot
}

$clientIndex = Join-Path $studioRoot "dist\client\index.html"
$needsBuild = -not (Test-Path -LiteralPath $clientIndex -PathType Leaf)
if (-not $needsBuild) {
    $buildTime = (Get-Item -LiteralPath $clientIndex).LastWriteTimeUtc
    $sourcePaths = @(
        (Join-Path $studioRoot "src"),
        (Join-Path $studioRoot "index.html"),
        (Join-Path $studioRoot "package.json"),
        (Join-Path $studioRoot "vite.config.mjs")
    )
    $latestSource = Get-ChildItem -LiteralPath $sourcePaths -Recurse -File |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    $needsBuild = $null -ne $latestSource -and $latestSource.LastWriteTimeUtc -gt $buildTime
}
if ($needsBuild) {
    Write-Host "[setup] Building the Studio SPA" -ForegroundColor Cyan
    Invoke-Checked "npm" @("run", "build") $studioRoot
}

Write-Host "[setup] Irodori-TTS: $resolvedIrodoriPath" -ForegroundColor Green
Write-Host "[setup] PyTorch backend: $TorchBackend" -ForegroundColor Green
if ($SetupOnly) {
    Write-Host "[setup] Complete. Use .\start-studio.ps1 for future launches." -ForegroundColor Green
    exit 0
}

$pythonArguments = @(
    (Join-Path $studioRoot "server.py"),
    "--irodori-root", $resolvedIrodoriPath,
    "--port", [string]$Port,
    "--voicevox-port", [string]$VoicevoxPort
)
if ($NoOpen) { $pythonArguments += "--no-open" }
if ($NoAutoloadModel) { $pythonArguments += "--no-autoload-model" }
if ($NoVoicevoxApi) { $pythonArguments += "--no-voicevox-api" }
if ($ServerArgs) { $pythonArguments += $ServerArgs }

Write-Host "[studio] Starting the Studio API, Irodori runtime, and VOICEVOX compatibility API" -ForegroundColor Cyan
& $irodoriPython @pythonArguments
exit $LASTEXITCODE
