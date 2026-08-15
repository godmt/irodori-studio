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
    [switch]$AccessLog,
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

function Get-IrodoriTorchBackend([string]$PythonPath) {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { return $null }
    $ErrorActionPreference = "Continue"
    $probe = @'
from importlib.metadata import PackageNotFoundError, version

try:
    torch_version = version('torch').lower()
except PackageNotFoundError:
    raise SystemExit(1)

backend = None
if '+cu128' in torch_version:
    backend = 'cu128'
elif '+rocm' in torch_version:
    backend = 'rocm'
elif '+xpu' in torch_version:
    backend = 'xpu'
elif '+cpu' in torch_version:
    backend = 'cpu'
else:
    try:
        import torch

        if torch.version.hip:
            backend = 'rocm'
        elif torch.version.cuda and str(torch.version.cuda).startswith('12.8'):
            backend = 'cu128'
        elif getattr(torch, 'xpu', None) is not None and torch.xpu.is_available():
            backend = 'xpu'
        elif not torch.version.cuda:
            backend = 'cpu'
    except Exception:
        pass

if backend is None:
    raise SystemExit(2)
print(backend)
'@
    $detected = @(& $PythonPath -c $probe 2>$null) |
        Where-Object { $_ -in @("cpu", "cu128", "xpu", "rocm") } |
        Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($detected)) { return $null }
    return [string]$detected
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found. Install it from https://docs.astral.sh/uv/."
}

$clientIndex = Join-Path $studioRoot "dist\client\index.html"
$frontendSourceDirectory = Join-Path $studioRoot "src"
$hasFrontendSource = Test-Path -LiteralPath $frontendSourceDirectory -PathType Container
if ($hasFrontendSource) {
    $requiredFrontendFiles = @("index.html", "package.json", "package-lock.json", "vite.config.mjs")
    foreach ($requiredFrontendFile in $requiredFrontendFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $studioRoot $requiredFrontendFile) -PathType Leaf)) {
            throw "Frontend source is present, but $requiredFrontendFile is missing. Restore the source checkout before starting Studio."
        }
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found. Source checkouts require Node.js 20 or later; packaged releases use the bundled frontend without Node.js."
    }
}
elseif (-not (Test-Path -LiteralPath $clientIndex -PathType Leaf)) {
    throw "The packaged Studio frontend is missing. Download and extract the complete Windows release package again."
}

$config = Read-StudioConfig
$resolvedIrodoriPath = Resolve-IrodoriRepository $config
$irodoriPython = Join-Path $resolvedIrodoriPath ".venv\Scripts\python.exe"

if ([string]::IsNullOrWhiteSpace($TorchBackend)) {
    $detectedBackend = Get-IrodoriTorchBackend $irodoriPython
    if (-not [string]::IsNullOrWhiteSpace($detectedBackend)) {
        $TorchBackend = $detectedBackend
        $torchBackendSource = "Irodori-TTS environment"
    }
    elseif (
        $null -ne $config -and
        $null -ne $config.PSObject.Properties["torchBackend"] -and
        @("cpu", "cu128", "xpu", "rocm") -contains [string]$config.torchBackend
    ) {
        $TorchBackend = [string]$config.torchBackend
        $torchBackendSource = "saved Studio configuration"
    }
    else {
        $TorchBackend = if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { "cu128" } else { "cpu" }
        $torchBackendSource = "detected hardware"
    }
}
else {
    $torchBackendSource = "explicit option"
}

New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
@{
    irodoriTtsPath = $resolvedIrodoriPath
    torchBackend = $TorchBackend
} | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8

$installedBackend = Get-IrodoriTorchBackend $irodoriPython
$backendMatches = $installedBackend -eq $TorchBackend
if ($ForceSync -or -not $backendMatches) {
    Write-Host "[setup] Syncing the Irodori-TTS environment ($TorchBackend)" -ForegroundColor Cyan
    Invoke-Checked "uv" @("sync", "--project", $resolvedIrodoriPath, "--extra", $TorchBackend) $resolvedIrodoriPath
}

& $irodoriPython -c "import fastapi, faster_whisper, uvicorn, numpy, pydantic, pyloudnorm, scipy, soundfile" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[setup] Installing the local Studio server dependencies into the Irodori environment" -ForegroundColor Cyan
    Invoke-Checked "uv" @(
        "pip", "install", "--python", $irodoriPython,
        "fastapi>=0.115", "faster-whisper>=1.2.1", "numpy>=1.26", "pydantic>=2.10", "pyloudnorm>=0.1.1", "scipy>=1.11", "soundfile>=0.12", "uvicorn>=0.34"
    ) $studioRoot
}

if ($hasFrontendSource) {
    $nodeModules = Join-Path $studioRoot "node_modules"
    if (-not (Test-Path -LiteralPath $nodeModules -PathType Container)) {
        Write-Host "[setup] Installing Studio frontend dependencies" -ForegroundColor Cyan
        Invoke-Checked "npm" @("ci") $studioRoot
    }

    $needsBuild = -not (Test-Path -LiteralPath $clientIndex -PathType Leaf)
    if (-not $needsBuild) {
        $buildTime = (Get-Item -LiteralPath $clientIndex).LastWriteTimeUtc
        $sourcePaths = @(
            $frontendSourceDirectory,
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
}
else {
    Write-Host "[setup] Using the bundled Studio frontend" -ForegroundColor Green
}

Write-Host "[setup] Irodori-TTS: $resolvedIrodoriPath" -ForegroundColor Green
Write-Host "[setup] PyTorch backend: $TorchBackend ($torchBackendSource)" -ForegroundColor Green
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
if ($AccessLog) { $pythonArguments += "--access-log" }
if ($ServerArgs) { $pythonArguments += $ServerArgs }

Write-Host "[studio] Starting the Studio API, Irodori runtime, and VOICEVOX compatibility API" -ForegroundColor Cyan
& $irodoriPython @pythonArguments
exit $LASTEXITCODE
