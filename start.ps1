#Requires -Version 5.1
<#
  One-click launcher for the webAgent project.

  Usage:
    .\start.ps1              # Docker mode (recommended): build + start the full stack
    .\start.ps1 -Local       # Local dev mode: postgres/redis in Docker, backend/worker/frontend on the host
    .\start.ps1 -NoBuild     # Docker mode: reuse existing images (skip --build)
    .\start.ps1 -NoOpen      # do not open the browser
    .\start.ps1 -Down        # stop and remove all containers, then exit

  Docker mode entry points:
    web  http://localhost:8090   (override with FRONTEND_PORT in .env)
    api  http://localhost:8000/docs   (override with BACKEND_PORT in .env)
    login demo / Demo123456

  Local mode entry points:
    web  http://localhost:5173
#>
[CmdletBinding()]
param(
  [switch]$Local,
  [switch]$NoBuild,
  [switch]$NoOpen,
  [switch]$Down
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

# Frontend / backend host ports: read from .env when present, else 8090 / 8000.
# (8080 is commonly taken by Steam's CEF debug port; some Windows machines also
#  reserve 8000 via Hyper-V/WinNAT, hence both are configurable.)
$frontendPort = 8090
$backendPort = 8000
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
  $match = Select-String -Path $envFile -Pattern '^\s*FRONTEND_PORT\s*=\s*(\d+)' | Select-Object -First 1
  if ($match) { $frontendPort = [int]$match.Matches[0].Groups[1].Value }
  $match = Select-String -Path $envFile -Pattern '^\s*BACKEND_PORT\s*=\s*(\d+)' | Select-Object -First 1
  if ($match) { $backendPort = [int]$match.Matches[0].Groups[1].Value }
}
$frontendUrl = "http://localhost:$frontendPort"
$backendUrl = "http://localhost:$backendPort"

function Info($m) { Write-Host "[start] $m" -ForegroundColor Cyan }
function Ok($m) { Write-Host "[ ok  ] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[warn ] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[fail ] $m" -ForegroundColor Red; exit 1 }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Wait-Http($url, $timeoutSec) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $res = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3
      if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 500) { return $true }
    } catch { }
    Start-Sleep -Seconds 2
  }
  return $false
}

function Test-Ollama {
  try {
    Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 | Out-Null
    return $true
  } catch { return $false }
}

if (-not (Have docker)) {
  Fail "docker not found. Install Docker Desktop (https://www.docker.com/products/docker-desktop/) and retry."
}

if ($Down) {
  Info "docker compose down"
  docker compose down
  if ($LASTEXITCODE -ne 0) { Fail "docker compose down failed" }
  Ok "stopped (named volumes kept). Wipe data with: docker compose down -v"
  exit 0
}

# docker compose plugin (v2) is required
docker compose version *> $null
if ($LASTEXITCODE -ne 0) { Fail "docker compose v2 not available. Update Docker Desktop." }

docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker daemon is not running. Start Docker Desktop and retry." }

if (-not (Test-Path (Join-Path $root ".env"))) {
  Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
  Warn "created .env from .env.example (local demo defaults)"
}

if (-not (Test-Ollama)) {
  Warn "Ollama not reachable at http://localhost:11434"
  Warn "start it and pull a model, e.g. 'ollama pull qwen2.5:7b-instruct-q4_K_M'"
  Warn "chat will not answer until Ollama is up (other pages still work)"
}

if ($Local) {
  # ------------------------- local dev mode -------------------------
  Info "local dev mode: postgres + redis in Docker, app processes on the host"

  Info "docker compose up -d postgres redis"
  docker compose up -d postgres redis
  if ($LASTEXITCODE -ne 0) { Fail "failed to start postgres/redis" }

  if (-not (Have uv)) { Fail "uv not found. Install: https://docs.astral.sh/uv/" }
  if (-not (Have pnpm)) { Fail "pnpm not found. Install: https://pnpm.io/installation" }

  Push-Location (Join-Path $root "backend")
  try {
    Info "backend: uv sync"
    uv sync
    if ($LASTEXITCODE -ne 0) { Fail "uv sync failed" }

    Info "backend: alembic upgrade head"
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail "alembic upgrade failed" }

    Info "backend: seed demo user (idempotent)"
    uv run python -m scripts.seed
  } finally {
    Pop-Location
  }

  $backendCmd = "Set-Location '$(Join-Path $root "backend")'; uv run uvicorn app.main:app --reload --port $backendPort"
  $workerCmd = "Set-Location '$(Join-Path $root "backend")'; uv run arq app.workers.settings.WorkerSettings"
  $frontCmd = "Set-Location '$(Join-Path $root "frontend")'; if (-not (Test-Path node_modules)) { pnpm install }; pnpm dev"

  # Vite 的 /api 代理目标读 BACKEND_PORT，子进程从父进程继承环境变量
  $env:BACKEND_PORT = "$backendPort"

  Info "starting backend / worker / frontend in separate windows"
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $workerCmd
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontCmd

  Info "waiting for frontend (http://localhost:5173) ..."
  if (Wait-Http "http://localhost:5173" 120) { Ok "frontend ready" }
  else { Warn "frontend not responding yet; check the frontend window for errors" }

  if (-not $NoOpen) { Start-Process "http://localhost:5173" }
  Write-Host ""
  Ok "up and running (local)"
  Write-Host "  web    : http://localhost:5173"
  Write-Host "  api    : $backendUrl/docs"
  Write-Host "  login  : demo / Demo123456"
  Write-Host "  stop   : close the three spawned windows (or .\start.ps1 -Down)"
  exit 0
}

# ------------------------- docker mode (default) -------------------------
$upArgs = @("compose", "up", "-d")
if (-not $NoBuild) { $upArgs += "--build" }
Info ("docker " + ($upArgs -join " "))
& docker @upArgs
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" }

Info "waiting for backend health ($backendUrl/health) ..."
if (Wait-Http "$backendUrl/health" 180) { Ok "backend healthy" }
else { Warn "backend health check timed out; run 'docker compose logs -f backend'" }

Info "waiting for frontend ($frontendUrl) ..."
if (Wait-Http $frontendUrl 120) { Ok "frontend ready" }
else { Warn "frontend not responding yet; run 'docker compose logs -f frontend'" }

if (-not $NoOpen) { Start-Process $frontendUrl }
Write-Host ""
Ok "up and running"
Write-Host "  web    : $frontendUrl"
Write-Host "  api    : $backendUrl/docs"
Write-Host "  login  : demo / Demo123456"
Write-Host "  logs   : docker compose logs -f"
Write-Host "  stop   : .\start.ps1 -Down"
