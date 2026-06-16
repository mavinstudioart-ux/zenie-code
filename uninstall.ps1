$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:USERPROFILE ".zenie\app"
$Launcher = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\zenie.cmd"

if (Test-Path $Launcher) {
    Remove-Item $Launcher -Force
}
if (Test-Path $InstallRoot) {
    Remove-Item $InstallRoot -Recurse -Force
}

Write-Host "Zenie Code runtime removed." -ForegroundColor Green
Write-Host "Model profiles and user config remain in $env:USERPROFILE\.zenie" -ForegroundColor DarkGray
