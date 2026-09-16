#Requires -Version 5.1
<#
  Sync repo design docs to the Obsidian vault.

  Mapping is by TITLE SUFFIX (the part after "NN-"), so vault numbering that
  differs from the repo is preserved
  (e.g. repo "12-<topic>" <-> vault "14-<topic>").

  Safety:
    - never overwrite a vault file whose modified time is newer than the repo file
      (use -Force to override)
    - a timestamped .bak-YYYYMMDDHHmmss copy is written before any overwrite
    - only files that differ are touched

  Usage:
    .\scripts\sync-docs.ps1
    .\scripts\sync-docs.ps1 -DryRun
    .\scripts\sync-docs.ps1 -Force
    .\scripts\sync-docs.ps1 -Vault "E:\some\other\vault"

  Vault path is read from scripts/obsidian-sync.json (UTF-8) unless -Vault is given.
#>
[CmdletBinding()]
param(
  [string]$Vault,
  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Info($m) { Write-Host "[sync] $m" -ForegroundColor Cyan }
function Ok($m) { Write-Host "[ ok  ] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[warn ] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[fail ] $m" -ForegroundColor Red; exit 1 }

$scriptsDir = $PSScriptRoot
$root = Split-Path -Parent $scriptsDir
$configPath = Join-Path $scriptsDir "obsidian-sync.json"

$sourceRel = $null
if (-not $Vault) {
  if (-not (Test-Path $configPath)) { Fail "missing config: $configPath (or pass -Vault)" }
  $config = [System.IO.File]::ReadAllText($configPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
  $Vault = $config.vault
  $sourceRel = $config.source
}
if (-not $sourceRel) { Fail "config missing 'source' (design docs dir)" }

$source = Join-Path $root ($sourceRel -replace '/', '\')

if (-not (Test-Path $source)) { Fail "source dir not found: $source" }
if (-not (Test-Path $Vault)) { Fail "vault not found: $Vault" }

function Get-Suffix([string]$name) {
  if ($name -match '^\d+-(.+)$') { return $Matches[1] }
  return $name
}

$vaultFiles = @(Get-ChildItem -LiteralPath $Vault -File -Filter *.md)
$maxNum = 0
foreach ($f in $vaultFiles) {
  if ($f.Name -match '^(\d+)-') { $n = [int]$Matches[1]; if ($n -gt $maxNum) { $maxNum = $n } }
}

$added = 0; $updated = 0; $unchanged = 0; $protected = 0

foreach ($doc in Get-ChildItem -LiteralPath $source -File -Filter *.md | Sort-Object Name) {
  $suffix = Get-Suffix $doc.Name
  $target = $vaultFiles | Where-Object { (Get-Suffix $_.Name) -eq $suffix } | Select-Object -First 1

  if (-not $target) {
    $maxNum += 1
    $targetName = ('{0:D2}-{1}' -f $maxNum, $suffix)
    if ($DryRun) { Info "[dry] NEW    $($doc.Name)  ->  $targetName" }
    else {
      Copy-Item -LiteralPath $doc.FullName -Destination (Join-Path $Vault $targetName)
      Ok "NEW    $targetName"
    }
    $added += 1
    continue
  }

  $repoLen = (Get-Item -LiteralPath $doc.FullName).Length
  if ($repoLen -eq $target.Length) {
    $sameHash = (Get-FileHash -LiteralPath $doc.FullName -Algorithm MD5).Hash -eq
      (Get-FileHash -LiteralPath $target.FullName -Algorithm MD5).Hash
    if ($sameHash) { $unchanged += 1; continue }
  }

  $repoNewer = (Get-Item -LiteralPath $doc.FullName).LastWriteTime -gt $target.LastWriteTime
  if (-not $repoNewer -and -not $Force) {
    Warn "vault is newer, skipped: $($target.Name)  (repo: $($doc.Name); use -Force to overwrite)"
    $protected += 1
    continue
  }

  if ($DryRun) {
    Info "[dry] UPDATE $($target.Name)  <-  $($doc.Name)"
  } else {
    $backup = "$($target.FullName).bak-$(Get-Date -Format yyyyMMddHHmmss)"
    Copy-Item -LiteralPath $target.FullName -Destination $backup
    Copy-Item -LiteralPath $doc.FullName -Destination $target.FullName -Force
    Ok "UPDATE $($target.Name)  (backup: $([System.IO.Path]::GetFileName($backup)))"
  }
  $updated += 1
}

Write-Host ""
Ok "vault = $Vault"
Ok "done: added=$added updated=$updated unchanged=$unchanged protected=$protected"
if ($protected -gt 0) { Warn "$protected file(s) skipped because the vault copy is newer (use -Force)" }
