#Requires -Version 5.1
<#
  Pre-push secret guard.

  Scans the files git would commit (tracked + untracked, ignoring .gitignore) for
  common credential shapes and forbidden filenames. Exit code 1 when something
  looks like a real secret.

  Usage:
    .\scripts\check-secrets.ps1
    git add -A
    .\scripts\check-secrets.ps1
    git commit -m "..." ; git push
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Fail($m) { Write-Host "[fail] $m" -ForegroundColor Red }
function Ok($m) { Write-Host "[ ok ] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[warn] $m" -ForegroundColor Yellow }

# 1) forbidden file names (env files / keys / credentials)
$namePatterns = @(
  '(^|/)\.env$',
  '\.env\.(local|dev|prod|production|staging)$',
  '\.pem$', '\.key$', '\.p12$', '\.pfx$', '\.jks$',
  '(^|/)id_rsa', '(^|/)id_ed25519$',
  'credentials\.json$', '(^|/)\.npmrc$', '(^|/)\.pypirc$'
)

# 2) forbidden content shapes (real-looking credentials)
$contentPatterns = @(
  'sk-[A-Za-z0-9]{20,}',
  'sk-proj-[A-Za-z0-9_-]{20,}',
  'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}',
  '-----BEGIN [A-Z ]*PRIVATE KEY-----',
  'gh[pousr]_[A-Za-z0-9]{20,}',
  'hf_[A-Za-z0-9]{20,}',
  'AKIA[0-9A-Z]{16}',
  'xox[baprs]-[A-Za-z0-9-]{10,}',
  'AIza[0-9A-Za-z_-]{30,}',
  'Bearer [A-Za-z0-9._-]{30,}'
)

# 3) allowlist: placeholders / test fixtures. A hit containing any of these is ignored.
$allow = @(
  'sk-test', 'sk-plaintext-secret', 'sk-AbCd1234', 'sk-mock',
  'change-me', 'change-me-to-32-random-chars-0123456789',
  'dev-secret-change-me-0123456789abcdef'
)

$problems = 0

# --- name check (tracked + untracked-not-ignored) ---
$names = @()
$names += git ls-files
$names += git ls-files --others --exclude-standard
$names = $names | Where-Object { $_ } | Sort-Object -Unique

foreach ($f in $names) {
  if ($f -match '\.example$') { continue }   # templates are fine
  foreach ($pat in $namePatterns) {
    if ($f -match $pat) {
      Fail "forbidden file in commit set: $f"
      $problems += 1
      break
    }
  }
}

# --- content check (git grep handles paths/encodings) ---
foreach ($pat in $contentPatterns) {
  $hits = @(git grep -nIE --untracked -- $pat 2>$null)
  foreach ($hit in $hits) {
    $allowed = $false
    foreach ($a in $allow) {
      if ($hit -like "*$a*") { $allowed = $true; break }
    }
    if ($allowed) { continue }
    Fail "possible secret: $hit"
    $problems += 1
  }
}

if ($problems -gt 0) {
  Write-Host ""
  Fail "$problems potential secret(s) found. Do NOT push."
  Warn "fix: remove the value, keep it in .env (gitignored), then re-run this script."
  exit 1
}

Ok "no secrets detected (scanned $($names.Count) tracked/untracked files)"
