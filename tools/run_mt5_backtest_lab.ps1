param(
    [string[]]$Symbols = @("EURUSDc", "USDJPYc"),
    [string]$FromDate = (Get-Date).AddMonths(-3).ToString("yyyy.MM.dd"),
    [string]$ToDate = (Get-Date).ToString("yyyy.MM.dd"),
    [switch]$RunTerminal
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$hfmRoot = "C:\Program Files\HFM Metatrader 5"
$hfmExperts = Join-Path $hfmRoot "MQL5\Experts"
$hfmPresets = Join-Path $hfmRoot "MQL5\Presets"
$hfmFiles = Join-Path $hfmRoot "MQL5\Files"
$terminal = Join-Path $hfmRoot "terminal64.exe"
$archiveRoot = Join-Path $repoRoot "archive\backtests"
$latestDir = Join-Path $archiveRoot "latest"
$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $archiveRoot ("runs\" + $runStamp)
$configDir = Join-Path $runDir "configs"
$reportDir = Join-Path $runDir "reports"

function Ensure-Directory($path) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}

function Copy-IfExists($source, $destination) {
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $destination -Force
        return $true
    }
    return $false
}

function Parse-ReportMetric($text, [string[]]$labels) {
    foreach ($label in $labels) {
        $escaped = [regex]::Escape($label)
        $patterns = @(
            "$escaped\s*</[^>]+>\s*<[^>]+>\s*([-+]?[0-9][0-9\s,]*(?:\.[0-9]+)?)",
            "$escaped[^-+0-9]*([-+]?[0-9][0-9\s,]*(?:\.[0-9]+)?)"
        )
        foreach ($pattern in $patterns) {
            $match = [regex]::Match($text, $pattern, "IgnoreCase")
            if ($match.Success) {
                $raw = $match.Groups[1].Value -replace "\s", "" -replace ",", ""
                $value = 0.0
                if ([double]::TryParse($raw, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$value)) {
                    return $value
                }
            }
        }
    }
    return $null
}

function Read-BacktestReport($reportPath) {
    if (-not (Test-Path -LiteralPath $reportPath)) {
        return [ordered]@{
            reportExists = $false
            closedTrades = $null
            netProfit = $null
            profitFactor = $null
            winRate = $null
            parseStatus = "REPORT_MISSING"
        }
    }

    $text = Get-Content -LiteralPath $reportPath -Raw
    $netProfit = Parse-ReportMetric $text @("Total Net Profit", "Net Profit", "Total profit")
    $profitFactor = Parse-ReportMetric $text @("Profit Factor")
    $totalTrades = Parse-ReportMetric $text @("Total Trades", "Trades")
    $winRate = Parse-ReportMetric $text @("Profit Trades (% of total)", "Win rate", "Winning trades")

    [ordered]@{
        reportExists = $true
        closedTrades = $totalTrades
        netProfit = $netProfit
        profitFactor = $profitFactor
        winRate = $winRate
        parseStatus = if ($null -ne $netProfit -or $null -ne $totalTrades) { "PARSED_PARTIAL" } else { "REPORT_FOUND_UNPARSED" }
    }
}

function New-TesterConfig($symbol, $presetName, $configPath, $reportPath) {
    $content = @"
[Tester]
Expert=QuantGod_MultiStrategy.ex5
ExpertParameters=$presetName
Symbol=$symbol
Period=M15
Model=1
ExecutionMode=0
Optimization=0
FromDate=$FromDate
ToDate=$ToDate
ForwardMode=0
Deposit=10000
Currency=USC
Leverage=1000
Report=$reportPath
ReplaceReport=1
ShutdownTerminal=1
"@
    Set-Content -LiteralPath $configPath -Value $content -Encoding ASCII
}

Ensure-Directory $archiveRoot
Ensure-Directory $latestDir
Ensure-Directory $runDir
Ensure-Directory $configDir
Ensure-Directory $reportDir
Ensure-Directory $hfmPresets

$syncedSource = Copy-IfExists (Join-Path $repoRoot "MQL5\Experts\QuantGod_MultiStrategy.mq5") (Join-Path $hfmExperts "QuantGod_MultiStrategy.mq5")
$syncedBinary = Copy-IfExists (Join-Path $repoRoot "MQL5\Experts\QuantGod_MultiStrategy.ex5") (Join-Path $hfmExperts "QuantGod_MultiStrategy.ex5")

$runs = @()
foreach ($symbol in $Symbols) {
    $presetName = "QuantGod_MT5_HFM_Backtest_$symbol.set"
    $presetSource = Join-Path $repoRoot ("MQL5\Presets\" + $presetName)
    $presetDest = Join-Path $hfmPresets $presetName
    $presetSynced = Copy-IfExists $presetSource $presetDest

    $symbolReportDir = Join-Path $reportDir $symbol
    Ensure-Directory $symbolReportDir
    $reportPath = Join-Path $symbolReportDir ("QuantGod_Backtest_" + $symbol + ".html")
    $configPath = Join-Path $configDir ("QuantGod_MT5_HFM_Backtest_" + $symbol + ".ini")
    New-TesterConfig $symbol $presetName $configPath $reportPath

    $terminalExitCode = $null
    if ($RunTerminal) {
        if (-not (Test-Path -LiteralPath $terminal)) {
            throw "HFM terminal not found: $terminal"
        }
        $process = Start-Process -FilePath $terminal -ArgumentList ('/config:"' + $configPath + '"') -Wait -PassThru
        $terminalExitCode = $process.ExitCode
    }

    $report = Read-BacktestReport $reportPath
    $runs += [ordered]@{
        symbol = $symbol
        strategy = "MA_Cross"
        lot = 0.01
        signalTimeframe = "M15"
        trendTimeframe = "H1"
        preset = $presetName
        presetSynced = $presetSynced
        configPath = $configPath
        reportPath = $reportPath
        terminalExitCode = $terminalExitCode
        status = if ($report.reportExists) { $report.parseStatus } else { if ($RunTerminal) { "REPORT_MISSING_AFTER_RUN" } else { "CONFIG_READY" } }
        closedTrades = $report.closedTrades
        netProfit = $report.netProfit
        profitFactor = $report.profitFactor
        winRate = $report.winRate
    }
}

$summary = [ordered]@{
    schemaVersion = 1
    lab = "HFM_MT5_BACKTEST_LAB_V1"
    generatedAtLocal = (Get-Date).ToString("yyyy.MM.dd HH:mm:ss")
    generatedAtIso = (Get-Date).ToString("o")
    status = if ($RunTerminal) { "RUN_ATTEMPTED" } else { "CONFIG_READY" }
    note = if ($RunTerminal) { "Tester run attempted. Check report paths for full MT5 output." } else { "Tester configs prepared. Run again with -RunTerminal when you intentionally want to launch MT5 Strategy Tester." }
    strategy = "MA_Cross"
    symbols = $Symbols
    lot = 0.01
    signalTimeframe = "M15"
    trendTimeframe = "H1"
    fromDate = $FromDate
    toDate = $ToDate
    archiveDir = $runDir
    sourceSynced = $syncedSource
    binarySynced = $syncedBinary
    decisionGate = "Future strategy changes must check both backtest support and live forward samples before loosening risk."
    runs = $runs
}

$summaryJson = $summary | ConvertTo-Json -Depth 8
$runSummaryPath = Join-Path $runDir "QuantGod_BacktestSummary.json"
$latestSummaryPath = Join-Path $latestDir "QuantGod_BacktestSummary.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($runSummaryPath, $summaryJson, $utf8NoBom)
[System.IO.File]::WriteAllText($latestSummaryPath, $summaryJson, $utf8NoBom)

if (Test-Path -LiteralPath $hfmFiles) {
    Copy-Item -LiteralPath $latestSummaryPath -Destination (Join-Path $hfmFiles "QuantGod_BacktestSummary.json") -Force
}

Write-Host "QuantGod Backtest Lab V1 summary written:"
Write-Host "  $runSummaryPath"
Write-Host "  $latestSummaryPath"
if (-not $RunTerminal) {
    Write-Host "Configs are ready. To launch MT5 Strategy Tester, rerun with -RunTerminal."
}
