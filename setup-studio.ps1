[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$IrodoriPath,
    [ValidateSet("cpu", "cu128", "xpu", "rocm")]
    [string]$TorchBackend,
    [switch]$ForceSync
)

$arguments = @{
    IrodoriPath = $IrodoriPath
    Configure = $true
    SetupOnly = $true
    ForceSync = $ForceSync
}
if (-not [string]::IsNullOrWhiteSpace($TorchBackend)) {
    $arguments.TorchBackend = $TorchBackend
}
& (Join-Path $PSScriptRoot "start-studio.ps1") @arguments
exit $LASTEXITCODE
