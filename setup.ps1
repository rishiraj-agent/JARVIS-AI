#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch] $SkipUpgradePip
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

function Stop-Setup([string] $Message) {
    Write-Error $Message
    exit 1
}

$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if (-not $pythonLauncher) {
    Stop-Setup 'Python Launcher (py.exe) was not found. Install 64-bit Python 3.11 and enable the Python Launcher.'
}

& py -3.11 --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-Setup 'Python 3.11 was not found. Install 64-bit Python 3.11, then run setup.ps1 again.'
}

$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host 'Creating the project virtual environment...'
    & py -3.11 -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) {
        Stop-Setup 'Could not create .venv. Check the Python installation and available disk space.'
    }
}

if (-not $SkipUpgradePip) {
    Write-Host 'Updating pip...'
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Stop-Setup 'Could not update pip. Check your internet connection and try again.'
    }
}

Write-Host 'Installing JARVIS dependencies...'
& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    Stop-Setup 'Dependency installation failed. Check the error above and the troubleshooting section in README.md.'
}

Write-Host ''
Write-Host 'JARVIS setup completed.' -ForegroundColor Green
Write-Host 'Launch from source with: .\.venv\Scripts\python.exe main.py'
Write-Host 'Or double-click start_jarvis.bat.'
