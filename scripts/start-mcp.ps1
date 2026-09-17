#Requires -Version 5.1
<#
  One-click launcher for the local MCP services in mcp_servers/.

  NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 without a BOM
  as ANSI, so non-ASCII text here breaks parsing (same reason sync-docs.ps1 is ASCII).

  Install (once):
    .\scripts\start-mcp.ps1 -Install            # base deps
    .\scripts\start-mcp.ps1 -Install -Cuda      # + CUDA runtime libs (~1.3GB; skip if reuse works)

  Run:
    .\scripts\start-mcp.ps1                 # start mcp_voice2text (auto-detect GPU)
    .\scripts\start-mcp.ps1 -Service all    # start every service
    .\scripts\start-mcp.ps1 -Stop           # stop every service

  Device: when WHISPER_DEVICE is not set explicitly, this script probes for an NVIDIA
  GPU and for CUDA runtime libs (cublas64_12). It prefers reusing the CUDA libs shipped
  with Ollama (%LOCALAPPDATA%\Programs\Ollama\lib\ollama\cuda_v12), which avoids a
  ~1.3GB pip download; otherwise it falls back to cpu/int8. Override in mcp_servers\.env
  with WHISPER_DEVICE / WHISPER_CUDA_DLL_DIRS.

  Then point the backend at it (backend .env):
    ASR_MCP_URL=http://host.docker.internal:10001/mcp   # backend in Docker
    ASR_INPUT_MODE=base64                               # host MCP cannot read container paths

  Adding a service: add it to $Services below and to src/main.py's SERVICES.
#>
[CmdletBinding()]
param(
  [ValidateSet("voice2text", "all")]
  [string]$Service = "voice2text",
  [switch]$Install,
  [switch]$Cuda,
  [switch]$Stop,
  [string]$Model = "Systran/faster-whisper-large-v3",
  [string]$Venv = "mcp_servers\.venv"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
Set-Location $root

# service alias -> MCP_SERVICE name (port comes from mcp_servers\.env)
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
  if ($Cuda) {
    Write-Host "[mcp] installing CUDA runtime libs (cublas/cudnn, ~1.3GB)" -ForegroundColor Cyan
    uv pip install --python $python -r "mcp_servers\requirements-cuda.txt"
  }
}

if (-not (Test-Path $python)) {
  Write-Host "[fail] venv python not found: $python" -ForegroundColor Red
  Write-Host "       install first:  .\scripts\start-mcp.ps1 -Install" -ForegroundColor Yellow
  exit 1
}

$projectDir = Join-Path $root "mcp_servers"

if (-not $env:WHISPER_MODEL) { $env:WHISPER_MODEL = $Model }

# Find directories that provide cublas64_12 / cublasLt64_12:
#   1) pip packages nvidia-*-cu12  -> site-packages\nvidia\*\bin
#   2) CUDA libs shipped with Ollama -> %LOCALAPPDATA%\Programs\Ollama\lib\ollama\cuda_v12
# Reusing (2) avoids a ~1.3GB download and the platform already depends on Ollama.
function Get-CudaDllDirs {
  $found = @()
  $siteRoot = (& $python -c "import site; print(site.getsitepackages()[0])" 2>$null)
  if ($LASTEXITCODE -eq 0 -and $siteRoot) {
    $nvidiaRoot = Join-Path "$siteRoot".Trim() "nvidia"
    if (Test-Path $nvidiaRoot) {
      foreach ($bin in (Get-ChildItem -Path $nvidiaRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object { Join-Path $_.FullName "bin" })) {
        if (Get-ChildItem -Path $bin -Filter "cublas64_*.dll" -ErrorAction SilentlyContinue) { $found += $bin }
      }
    }
  }
  $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\lib\ollama\cuda_v12"
  if (Get-ChildItem -Path $ollama -Filter "cublas64_*.dll" -ErrorAction SilentlyContinue) { $found += $ollama }
  return $found
}

if (-not $env:WHISPER_DEVICE) {
  $device = "cpu"
  $cudaCount = (& $python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())" 2>$null)
  if ($LASTEXITCODE -eq 0 -and "$cudaCount".Trim() -eq "1") {
    $dllDirs = Get-CudaDllDirs
    if ($dllDirs.Count -gt 0) {
      $device = "cuda"
      if (-not $env:WHISPER_CUDA_DLL_DIRS) { $env:WHISPER_CUDA_DLL_DIRS = ($dllDirs -join ";") }
    }
  }
  $env:WHISPER_DEVICE = $device
}
if (-not $env:WHISPER_COMPUTE_TYPE) {
  $env:WHISPER_COMPUTE_TYPE = if ($env:WHISPER_DEVICE -like "cuda*") { "int8_float16" } else { "int8" }
}
if (-not $env:VOICE_PORT) { $env:VOICE_PORT = "$Port" }

Write-Host "[mcp] whisper: $env:WHISPER_MODEL @ $env:WHISPER_DEVICE/$env:WHISPER_COMPUTE_TYPE" -ForegroundColor Cyan
if ($env:WHISPER_DEVICE -like "cuda*") {
  Write-Host "[mcp] CUDA dll dirs: $env:WHISPER_CUDA_DLL_DIRS" -ForegroundColor Cyan
} else {
  Write-Host "[mcp] NVIDIA GPU without CUDA libs. Reuse Ollama's (auto-detected above) or run: .\scripts\start-mcp.ps1 -Install -Cuda" -ForegroundColor Yellow
}

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
Write-Host "      voice2text  http://localhost:10001/mcp   (port from mcp_servers\.env VOICE_PORT)"
Write-Host "      stop        .\scripts\start-mcp.ps1 -Stop"
Write-Host "      first transcription loads the model into memory; keep the window open."
