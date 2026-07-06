$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"
$python = (Resolve-Path $python).Path
& $python -m pip install -e ".[hops]"
Write-Host "Hops dependencies installed."
