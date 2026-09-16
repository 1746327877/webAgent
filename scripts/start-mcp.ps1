#Requires -Version 5.1
<#
  One-click launcher for the local MCP services in mcp_servers/.

  Install (once):
    .\scripts\start-mcp.ps1 -Install

  Run:
    .\scripts\start-mcp.ps1                 # start mcp_voice2text (default)
    .\scripts\start-mcp.ps1 -Service all    # start every service
    .\scripts\start-mcp.ps1 -Stop           # stop every service

  Then point the backend at it (.env):
    ASR_MCP_URL=http://host.docker.internal:10001/mcp   # backend in Docker
    ASR_INPUT_MODE=base64                               # host MCP cannot read container paths

  Adding a service: add it to $Services below and to src/main.py's SERVICES.
#>
[CmdletBinding()]
param(
  [ValidateSet("voice2text", "all")]
  [string]$Service = "voice2text",
  [switch]$Install,
  [switch]$Stop,
  [string]$Venv = "mcp_servers\.venv"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
Set-Location $root

# 服务别名 → (MCP_SERVICE 名, 说明端口来自 mcp_servers/.env)
$Services = @{
  "voice2text" = "mcp_voice2text"
}

$selected = if ($Service -eq "all") { $Services.Keys | Sort-Object } else { @($Service) }

if ($Stop) {
  $killed = 0
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*mcp_servers*" -or $_.CommandLine -like "*src.main*" } |
    ForEach-Object { Write-Host "[mcp] stopping pid $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force; $killed++ }
  Write-Host "[mcp] stopped $killed process(es)" -ForegroundColor Green
  exit 0
}

$python = Join-Path $root "$Venv\Scripts\python.exe"

if ($Install) {
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[fail] uv not found. Install: https://docs.astral.sh/uv/" -ForegroundColor Red
    exit 1
  }
  if (-not (Test-Path $python)) {
    Write-Host "[mcp] creating venv: $Venv" -ForegroundColor Cyan
    uv venv $Venv --python 3.12
  }
  Write-Host "[mcp] installing requirements (first run downloads hundreds of MB)" -ForegroundColor Cyan
  uv pip install --python $python -r "mcp_servers\requirements.txt"
}

if (-not (Test-Path $python)) {
  Write-Host "[fail] venv python not found: $python" -ForegroundColor Red
  Write-Host "       install first:  .\scripts\start-mcp.ps1 -Install" -ForegroundColor Yellow
  exit 1
}

$projectDir = Join-Path $root "mcp_servers"
foreach ($alias in $selected) {
  $name = $Services[$alias]
  if (-not $name) { Write-Host "[fail] unknown service: $alias" -ForegroundColor Red; exit 1 }
  $cmd = "Set-Location '$projectDir'; `$env:MCP_SERVICE='$name'; & '$python' -m src.main"
  Write-Host "[mcp] starting $name in a new window" -ForegroundColor Cyan
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd -WindowStyle Minimized
}

Start-Sleep -Seconds 3
Write-Host ""
Write-Host "[mcp] started: $($selected -join ', ')" -ForegroundColor Green
Write-Host "      voice2text  http://localhost:10001/mcp   (端口以 mcp_servers\.env 的 VOICE_PORT 为准)"
Write-Host "      stop        .\scripts\start-mcp.ps1 -Stop"
Write-Host "      first transcription loads the model into memory; keep the window open."
