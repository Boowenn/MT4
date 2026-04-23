param(
    [string]$SourceDir = "C:\Program Files (x86)\MetaTrader 4\MQL4\Files",
    [string]$RepoRoot = "C:\Users\OWNER\QuantGod_MT4"
)

$ErrorActionPreference = "Stop"

$archiveRoot = Join-Path $RepoRoot "archive\mt4-runtime-snapshots"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$snapshotRoot = Join-Path $archiveRoot $timestamp
$dataRoot = Join-Path $snapshotRoot "files"

$filesToArchive = @(
    "QuantGod_Dashboard.json",
    "QuantGod_AdaptiveStateHistory.csv",
    "QuantGod_BalanceHistory.csv",
    "QuantGod_EquitySnapshots.csv",
    "QuantGod_OpportunityLabels.csv",
    "QuantGod_RegimeEvaluationReport.csv",
    "QuantGod_SignalLog.csv",
    "QuantGod_SignalLog_pre_features_20260421_140826.csv",
    "QuantGod_SignalOpportunityQueue.csv",
    "QuantGod_StrategyEvaluationReport.csv",
    "QuantGod_TradeEventLinks.csv",
    "QuantGod_TradeJournal.csv",
    "QuantGod_TradeOutcomeLabels.csv"
)

New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null

$records = @()
foreach($name in $filesToArchive)
{
    $sourcePath = Join-Path $SourceDir $name
    if(!(Test-Path $sourcePath))
    {
        continue
    }

    $destPath = Join-Path $dataRoot $name
    Copy-Item $sourcePath $destPath -Force

    $sourceItem = Get-Item $sourcePath
    $destItem = Get-Item $destPath
    $hash = (Get-FileHash $destPath -Algorithm SHA256).Hash

    $records += [PSCustomObject]@{
        FileName = $name
        SourcePath = $sourcePath
        ArchivedPath = $destPath
        LastWriteTime = $sourceItem.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
        Length = $destItem.Length
        SHA256 = $hash
    }
}

$summary = [ordered]@{
    snapshotId = $timestamp
    createdAtLocal = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    sourceDir = $SourceDir
    repoRoot = $RepoRoot
    archivedFileCount = $records.Count
    files = $records
}

$dashboardPath = Join-Path $dataRoot "QuantGod_Dashboard.json"
if(Test-Path $dashboardPath)
{
    try
    {
        $dashboard = Get-Content $dashboardPath -Raw | ConvertFrom-Json
        $summary["dashboard"] = [ordered]@{
            timestamp = $dashboard.timestamp
            build = $dashboard.build
            tradeStatus = $dashboard.runtime.tradeStatus
            serverTime = $dashboard.runtime.serverTime
            localTime = $dashboard.runtime.localTime
            accountMode = $dashboard.account.mode
            startingBalance = $dashboard.account.startingBalance
            balance = $dashboard.account.balance
            equity = $dashboard.account.equity
            watchlist = $dashboard.watchlist
        }
    }
    catch
    {
        $summary["dashboardParseError"] = $_.Exception.Message
    }
}

$summary | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $snapshotRoot "snapshot-manifest.json") -Encoding UTF8
$records | Export-Csv -Path (Join-Path $snapshotRoot "snapshot-manifest.csv") -NoTypeInformation -Encoding UTF8

$latestNote = @"
Latest snapshot: $timestamp
Created at: $((Get-Date).ToString("yyyy-MM-dd HH:mm:ss"))
Source: $SourceDir
Archived files: $($records.Count)
"@
$latestNote | Set-Content -Path (Join-Path $archiveRoot "LATEST.txt") -Encoding UTF8

Write-Output "Archived $($records.Count) files to $snapshotRoot"
