$ErrorActionPreference = "Stop"

Write-Host "Creating Python virtual environment..."
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3.11 -m venv .venv
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m venv .venv
} else {
    throw "Python was not found. Install Python 3.11 and retry."
}

$python = Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"
$python = (Resolve-Path $python).Path

& $python -m pip install --upgrade pip
& $python -m pip install -e ".[dev,cad,api]"

Write-Host ""
Write-Host "Running tests..."
& $python -m pytest

Write-Host ""
Write-Host "Setup completed."
Write-Host "Select .venv\\Scripts\\python.exe as the VS Code interpreter."
