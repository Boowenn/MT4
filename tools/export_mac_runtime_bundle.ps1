param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$Mt5FilesDir = 'C:\Program Files\HFM Metatrader 5\MQL5\Files',
  [string]$OutputRoot = '',
  [switch]$NoZip
)

$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path $RepoRoot).Path
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
  $OutputRoot = Join-Path $repo 'runtime'
}
$bundle = Join-Path $OutputRoot "mac_export_$stamp"
$dashboardDir = Join-Path $repo 'Dashboard'
$historyDir = Join-Path $repo 'archive\polymarket\history'

New-Item -ItemType Directory -Force -Path `
  $bundle, `
  (Join-Path $bundle 'mt5_files_snapshot'), `
  (Join-Path $bundle 'dashboard_runtime_snapshot'), `
  (Join-Path $bundle 'polymarket_history'), `
  (Join-Path $bundle 'env') | Out-Null

function Copy-QuantGodFiles {
  param(
    [string]$SourceDir,
    [string]$DestinationDir,
    [string]$Filter = 'QuantGod*'
  )
  $copied = @()
  if (Test-Path -LiteralPath $SourceDir) {
    Get-ChildItem -LiteralPath $SourceDir -File -Filter $Filter | ForEach-Object {
      Copy-Item -LiteralPath $_.FullName -Destination $DestinationDir -Force
      $copied += $_
    }
  }
  return $copied
}

$mt5Files = Copy-QuantGodFiles -SourceDir $Mt5FilesDir -DestinationDir (Join-Path $bundle 'mt5_files_snapshot')
$dashboardFiles = Copy-QuantGodFiles -SourceDir $dashboardDir -DestinationDir (Join-Path $bundle 'dashboard_runtime_snapshot')
$historyFiles = Copy-QuantGodFiles -SourceDir $historyDir -DestinationDir (Join-Path $bundle 'polymarket_history') -Filter 'QuantGod_PolymarketHistory.sqlite*'

$envExample = Join-Path $repo '.env.example'
if (Test-Path -LiteralPath $envExample) {
  Copy-Item -LiteralPath $envExample -Destination (Join-Path $bundle 'env\.env.example') -Force
}

@'
# QuantGod Mac runtime import template
# Copy to .env on Mac and adjust paths if you keep this bundle somewhere else.

QG_DASHBOARD_HOST=127.0.0.1
QG_DASHBOARD_PORT=8080
QG_READONLY_MODE=1

QG_RUNTIME_DIR=./runtime/mac_import/mt5_files_snapshot
QG_MT5_FILES_DIR=./runtime/mac_import/mt5_files_snapshot
QG_MT5_READONLY_BRIDGE_ENABLED=0
QG_MT5_TRADING_ENABLED=false
QG_MT5_ADAPTIVE_APPLY_ENABLED=false

QG_DASHBOARD_FILES_DIR=./runtime/mac_import/dashboard_runtime_snapshot
QG_POLYMARKET_DATA_DIR=./runtime/mac_import/dashboard_runtime_snapshot
QG_POLYMARKET_HISTORY_DB=./runtime/mac_import/polymarket_history/QuantGod_PolymarketHistory.sqlite
QG_POLYMARKET_LLM_ENV_FILE=./.env.local

QG_POLYMARKET_REAL_EXECUTION=false
QG_POLYMARKET_CANARY_ACK=
QG_POLYMARKET_CANARY_KILL_SWITCH=true
QG_POLYMARKET_WALLET_ADAPTER=
'@ | Set-Content -LiteralPath (Join-Path $bundle 'env\quantgod.mac.env') -Encoding UTF8

@'
# Optional secrets for Mac. Fill locally; do not commit or paste values into chat.
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-4o-mini
QG_POLYMARKET_OPENAI_API_KEY=
QG_POLYMARKET_PRIVATE_KEY=
QG_POLYMARKET_FUNDER=
QG_POLYMARKET_PROXY_ADDRESS=
QG_POLYMARKET_API_KEY=
QG_POLYMARKET_API_SECRET=
QG_POLYMARKET_API_PASSPHRASE=
'@ | Set-Content -LiteralPath (Join-Path $bundle 'env\quantgod.secrets.env.example') -Encoding UTF8

$required = @('QuantGod_Dashboard.json', 'QuantGod_TradeJournal.csv', 'QuantGod_CloseHistory.csv')
$mt5Names = @($mt5Files | ForEach-Object { $_.Name })
$latestMt5 = $mt5Files | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$latestDashboard = $dashboardFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1

$manifest = [ordered]@{
  generatedAt = (Get-Date).ToString('o')
  repo = $repo
  bundle = $bundle
  sourcePaths = [ordered]@{
    mt5Files = $Mt5FilesDir
    dashboard = $dashboardDir
    polymarketHistory = $historyDir
  }
  mt5 = [ordered]@{
    fileCount = $mt5Files.Count
    totalBytes = ($mt5Files | Measure-Object Length -Sum).Sum
    latestWriteTime = if ($latestMt5) { $latestMt5.LastWriteTime.ToString('o') } else { $null }
    requiredRealtimeFiles = $required
    missingRequiredRealtimeFiles = @($required | Where-Object { $mt5Names -notcontains $_ })
  }
  dashboard = [ordered]@{
    fileCount = $dashboardFiles.Count
    totalBytes = ($dashboardFiles | Measure-Object Length -Sum).Sum
    latestWriteTime = if ($latestDashboard) { $latestDashboard.LastWriteTime.ToString('o') } else { $null }
  }
  polymarketHistory = [ordered]@{
    fileCount = $historyFiles.Count
    files = @($historyFiles | Select-Object Name, Length, LastWriteTime)
  }
  env = [ordered]@{
    included = @('.env.example', 'quantgod.mac.env', 'quantgod.secrets.env.example')
    note = 'Secrets are not copied. Fill local Mac secrets manually if needed.'
  }
}

$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $bundle 'manifest.json') -Encoding UTF8

$generatedText = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
@"
# QuantGod Mac Migration Data Bundle

Generated: $generatedText

Copy this folder to the Mac repo as runtime/mac_import, then copy
env/quantgod.mac.env to the Mac repo root as .env.

Contents:

- mt5_files_snapshot/: copied HFM MT5 QuantGod* files.
- dashboard_runtime_snapshot/: copied Dashboard QuantGod* files.
- polymarket_history/: copied Polymarket SQLite history files.
- env/: Mac env template and non-secret secret placeholder.

Check manifest.json for counts and missing MT5 realtime files.
"@ | Set-Content -LiteralPath (Join-Path $bundle 'README.md') -Encoding UTF8

$zip = $null
if (-not $NoZip) {
  $zip = Join-Path $OutputRoot "quantgod_mac_export_$stamp.zip"
  Compress-Archive -Path (Join-Path $bundle '*') -DestinationPath $zip -Force
}

[pscustomobject]@{
  Bundle = $bundle
  Zip = $zip
  Mt5FileCount = $mt5Files.Count
  DashboardFileCount = $dashboardFiles.Count
  HistoryFileCount = $historyFiles.Count
  MissingMt5Required = ($manifest.mt5.missingRequiredRealtimeFiles -join ',')
}
