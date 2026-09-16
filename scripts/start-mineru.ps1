#Requires -Version 5.1
<#
  Start the MinerU document-parsing service (mineru-api) on the host.

  One-time install (separate venv, keep it off the backend image):
    uv venv D:\mineru\.venv --python 3.12
    uv pip install --python D:\mineru\.venv\Scripts\python.exe -U "mineru[all]"

  Then enable it for the backend by setting in .env:
    MINERU_API_URL=http://host.docker.internal:8001   # Docker mode
    MINERU_API_URL=http://localhost:8001              # local dev mode

  Usage:
    .\scripts\start-mineru.ps1
    .\scripts\start-mineru.ps1 -Port 8002
    .\scripts\start-mineru.ps1 -Venv "E:\mineru\.venv"
#>
[CmdletBinding()]
param(
  [int]$Port = 8001,
  [string]$Venv = "D:\mineru\.venv"
)

$ErrorActionPreference = "Stop"

$exe = Join-Path $Venv "Scripts\mineru-api.exe"
if (-not (Test-Path $exe)) {
  Write-Host "[fail] mineru-api not found: $exe" -ForegroundColor Red
  Write-Host "       install first:  uv pip install --python '$Venv\Scripts\python.exe' -U 'mineru[all]'" -ForegroundColor Yellow
  exit 1
}

# HuggingFace is blocked in some networks; modelscope is the usual fallback.
if (-not $env:MINERU_MODEL_SOURCE) { $env:MINERU_MODEL_SOURCE = "modelscope" }

Write-Host "[mineru] mineru-api on http://0.0.0.0:$Port  (model source: $env:MINERU_MODEL_SOURCE)" -ForegroundColor Cyan
Write-Host "[mineru] first run downloads models; keep this window open." -ForegroundColor Cyan
& $exe --host 0.0.0.0 --port $Port
