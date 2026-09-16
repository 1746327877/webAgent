#Requires -Version 5.1
<#
  Start the local Whisper ASR MCP server (mcp_servers/voice_asr) on the host.

  Why on the host: faster-whisper large-v3 is ~3GB and lives in the host HF cache;
  running it inside Docker would mean a slow Windows bind mount and no GPU anyway.

  One-time install (separate venv, keep it off the backend image):
    uv venv mcp_servers\voice_asr\.venv --python 3.12
    uv pip install --python mcp_servers\voice_asr\.venv\Scripts\python.exe -r mcp_servers\voice_asr\requirements.txt

  Then enable it for the backend by setting in .env:
    ASR_MCP_URL=http://host.docker.internal:10001/mcp   # Docker mode (backend in Docker)
    ASR_MCP_URL=http://localhost:10001/mcp              # local dev mode
    ASR_INPUT_MODE=base64                               # host MCP cannot read container paths

  Usage:
    .\scripts\start-voice-asr.ps1
    .\scripts\start-voice-asr.ps1 -Port 10002
    .\scripts\start-voice-asr.ps1 -Model Systran/faster-whisper-base   # 更快，先验证链路
#>
[CmdletBinding()]
param(
  [int]$Port = 10001,
  [string]$Model = "Systran/faster-whisper-large-v3",
  [string]$Venv = "mcp_servers\voice_asr\.venv",
  [switch]$Install
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location (Split-Path -Parent $root)

$python = Join-Path $Venv "Scripts\python.exe"
if ($Install) {
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[fail] uv not found. Install: https://docs.astral.sh/uv/" -ForegroundColor Red
    exit 1
  }
  if (-not (Test-Path $python)) {
    Write-Host "[voice-asr] creating venv: $Venv" -ForegroundColor Cyan
    uv venv $Venv --python 3.12
  }
  Write-Host "[voice-asr] installing requirements (first run downloads ~hundreds of MB)" -ForegroundColor Cyan
  uv pip install --python $python -r "mcp_servers\voice_asr\requirements.txt"
}

if (-not (Test-Path $python)) {
  Write-Host "[fail] venv python not found: $python" -ForegroundColor Red
  Write-Host "       install first:  .\scripts\start-voice-asr.ps1 -Install" -ForegroundColor Yellow
  exit 1
}

if (-not $env:WHISPER_MODEL) { $env:WHISPER_MODEL = $Model }
if (-not $env:WHISPER_DEVICE) { $env:WHISPER_DEVICE = "cpu" }
if (-not $env:WHISPER_COMPUTE_TYPE) { $env:WHISPER_COMPUTE_TYPE = "int8" }
if (-not $env:VOICE_PORT) { $env:VOICE_PORT = "$Port" }

Write-Host "[voice-asr] http://0.0.0.0:$Port/mcp  (model: $env:WHISPER_MODEL, device: $env:WHISPER_DEVICE/$env:WHISPER_COMPUTE_TYPE)" -ForegroundColor Cyan
Write-Host "[voice-asr] first transcription loads the model into memory; keep this window open." -ForegroundColor Cyan
& $python -m mcp_servers.voice_asr.server
