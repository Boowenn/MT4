# MT4 Runtime Archive

This folder is the local preservation area for MT4 research assets.

Purpose:

- keep MT4 historical research samples safe before retiring the MT4 install
- preserve raw runtime exports outside `C:\Program Files (x86)\MetaTrader 4\`
- avoid pushing large private runtime datasets to GitHub by default

Rules:

- snapshot data is stored under `archive/mt4-runtime-snapshots/`
- that snapshot directory is intentionally ignored by Git
- use [tools/archive_mt4_runtime.ps1](C:/Users/OWNER/QuantGod_MT4/tools/archive_mt4_runtime.ps1) to create a new snapshot
- check `LATEST.txt` inside the snapshot root to find the newest local archive

Current scope of each snapshot:

- `QuantGod_Dashboard.json`
- `QuantGod_AdaptiveStateHistory.csv`
- `QuantGod_BalanceHistory.csv`
- `QuantGod_EquitySnapshots.csv`
- `QuantGod_OpportunityLabels.csv`
- `QuantGod_RegimeEvaluationReport.csv`
- `QuantGod_SignalLog.csv`
- `QuantGod_SignalLog_pre_features_20260421_140826.csv`
- `QuantGod_SignalOpportunityQueue.csv`
- `QuantGod_StrategyEvaluationReport.csv`
- `QuantGod_TradeEventLinks.csv`
- `QuantGod_TradeJournal.csv`
- `QuantGod_TradeOutcomeLabels.csv`

Notes:

- this archive preserves MT4 research assets locally; it does not migrate those samples into the MT5 shadow runtime
- the HFM MT5 shadow runtime remains a separate live-account read-only export under `C:\Program Files\HFM Metatrader 5\MQL5\Files\`
