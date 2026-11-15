# Production-mode run WITHOUT Docker (Windows): builds the web UI if needed, verifies the data, serves UI + API on one port.
# Usage: .\scripts\run_production.ps1 [-Port 8000]
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
if (-not (Test-Path "web\dist\index.html")) {
  $node = Join-Path $env:LOCALAPPDATA "Programs\nodejs"
  if (Test-Path $node) { $env:PATH = "$node;$env:PATH" }
  Push-Location web; npm ci; npm run build; Pop-Location
}
& $py scripts\verify_data.py
if ($LASTEXITCODE -ne 0) { Write-Error "Data not ready: see docs/DEPLOYMENT.md"; exit 1 }
if (-not $env:LUNARNAV_ENV) { $env:LUNARNAV_ENV = "production" }
if (-not $env:LUNARNAV_LOG_JSON) { $env:LUNARNAV_LOG_JSON = "true" }
if (-not $env:LUNARNAV_MAX_HEAVY_REQUESTS) { $env:LUNARNAV_MAX_HEAVY_REQUESTS = "2" }
& $py -m uvicorn lunarnav_api.serve:app --host 0.0.0.0 --port $Port --proxy-headers
