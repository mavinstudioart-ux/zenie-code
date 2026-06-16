param(
    [switch]$WithTreeSitter,
    [switch]$Dev,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Join-Path $env:USERPROFILE ".zenie\app"
$VenvRoot = Join-Path $InstallRoot "venv"
$WindowsApps = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"
$Launcher = Join-Path $WindowsApps "zenie.cmd"

Write-Host ""
Write-Host "Installing Zenie Code..." -ForegroundColor Cyan
Write-Host "Source: $RepoRoot" -ForegroundColor DarkGray
Write-Host "Runtime: $VenvRoot" -ForegroundColor DarkGray

if ($Force -and (Test-Path $VenvRoot)) {
    Remove-Item $VenvRoot -Recurse -Force
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.11 or newer first."
}

$VersionOutput = & py -3.11 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
if ($LASTEXITCODE -ne 0) {
    $VersionOutput = & py -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
}

$VersionParts = $VersionOutput.Split(".")
if ([int]$VersionParts[0] -lt 3 -or ([int]$VersionParts[0] -eq 3 -and [int]$VersionParts[1] -lt 11)) {
    throw "Zenie Code requires Python 3.11 or newer. Detected: $VersionOutput"
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $WindowsApps | Out-Null

if (-not (Test-Path $VenvRoot)) {
    & py -m venv $VenvRoot
}

$Python = Join-Path $VenvRoot "Scripts\python.exe"
& $Python -m pip install --upgrade pip

$InstallTarget = "$RepoRoot"
if ($Dev) {
    & $Python -m pip install -e "$InstallTarget[dev]"
} elseif ($WithTreeSitter) {
    & $Python -m pip install "$InstallTarget[treesitter]"
} else {
    & $Python -m pip install --upgrade $InstallTarget
}

@"
@echo off
"$VenvRoot\Scripts\python.exe" -m zenie_code.cli %*
"@ | Set-Content -Encoding ASCII $Launcher

Write-Host ""
Write-Host "Zenie Code installed successfully." -ForegroundColor Green
Write-Host "Run from any project folder:" -ForegroundColor White
Write-Host "  zenie" -ForegroundColor Cyan
Write-Host ""
Write-Host "Launcher: $Launcher" -ForegroundColor DarkGray
Write-Host "Config:   $env:USERPROFILE\.zenie\config.json" -ForegroundColor DarkGray
